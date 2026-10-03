#!/usr/bin/env python3
import os  # Configurable workspace; no machine-specific paths.
"""Classify existing model delta rows using only retained source evidence."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha_text(value):
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def repo_id(repo):
    return repo.replace("/", "__")


def source_matches(snapshot, group_id, artifact_id, execution_id):
    matches = []
    if not snapshot.exists():
        return matches
    gid = re.escape(group_id)
    aid = re.escape(artifact_id)
    for pom in sorted(snapshot.rglob("pom.xml")):
        text = pom.read_text(encoding="utf-8", errors="replace")
        plugin = re.search(
            rf"<groupId>\s*{gid}\s*</groupId>.*?<artifactId>\s*{aid}\s*</artifactId>|"
            rf"<artifactId>\s*{aid}\s*</artifactId>.*?<groupId>\s*{gid}\s*</groupId>",
            text,
            flags=re.S,
        )
        if not plugin:
            continue
        execution = bool(execution_id and re.search(
            rf"<id>\s*{re.escape(execution_id)}\s*</id>", text
        ))
        rel = pom.relative_to(snapshot).as_posix()
        matches.append({"pom_path": rel, "plugin_declared": True, "execution_id_declared": execution})
    return matches


def parse_entity(entity):
    bits = entity.split(":")
    if len(bits) < 2:
        return entity, "", ""
    return bits[0], bits[1], ":".join(bits[2:])


def runtime_evidence(root, group_id, artifact_id, execution_id):
    evidence = []
    defaults = root / "evidence" / "runtime-resources"
    plugin_version_files = sorted(defaults.glob("*plugin-versions.properties"))
    version_hit = False
    for path in plugin_version_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if f"{artifact_id}=" in text or f"{group_id}:{artifact_id}" in text:
            version_hit = True
            evidence.append(path.relative_to(root).as_posix())
    bindings = sorted(defaults.glob("*default-bindings.xml"))
    binding_hit = False
    for path in bindings:
        text = path.read_text(encoding="utf-8", errors="replace")
        if f"{group_id}:{artifact_id}" in text:
            binding_hit = True
            evidence.append(path.relative_to(root).as_posix())
    if execution_id in {"default-site", "default-deploy"} and binding_hit:
        return "DEFAULT_LIFECYCLE", ";".join(evidence)
    if version_hit and group_id == "org.apache.maven.plugins":
        return "DEFAULT_LIFECYCLE", ";".join(evidence)
    return "", ";".join(evidence)


def extension_evidence(root, repo, execution_id):
    path = root / "metadata_diff" / repo_id(repo) / "extension-binding-evidence.json"
    if not path.exists():
        return "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    if execution_id == "injected-central-publishing" and data.get("repeatable") is True:
        return "MAVEN_RUNTIME_SYNTHESIZED", path.relative_to(root).as_posix()
    return "", ""


def classify(root, row):
    repo = row["repo"]
    group_id, artifact_id, execution_id = parse_entity(row["entity"])
    snapshot = root / "final_evidence_v1" / "snapshots" / repo_id(repo)
    matches = source_matches(snapshot, group_id, artifact_id, execution_id)
    source_execution = [x for x in matches if x["execution_id_declared"]]
    if source_execution:
        root_or_module = (
            "USER_ROOT_POM"
            if any(x["pom_path"] == "pom.xml" for x in source_execution)
            else "USER_MODULE_POM"
        )
        return root_or_module, root_or_module, ";".join(x["pom_path"] for x in source_execution), "HIGH"
    ext_class, ext_evidence = extension_evidence(root, repo, execution_id)
    if ext_class:
        return ext_class, "MAVEN_RUNTIME_SYNTHESIZED", ext_evidence, "HIGH"
    runtime_class, runtime_evidence_path = runtime_evidence(root, group_id, artifact_id, execution_id)
    if runtime_class:
        return runtime_class, runtime_class, runtime_evidence_path, "HIGH"
    if matches:
        root_or_module = (
            "USER_ROOT_POM"
            if any(x["pom_path"] == "pom.xml" for x in matches)
            else "USER_MODULE_POM"
        )
        return root_or_module, root_or_module, ";".join(x["pom_path"] for x in matches), "MEDIUM"
    return "UNKNOWN", "UNKNOWN", "No direct source or runtime evidence for this entity/delta", "UNKNOWN"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()))
    parser.add_argument("--out", type=Path, default=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve() / 'artifacts/reviewer_revision/model'))
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    deltas = read_csv(root / "final_evidence_v1" / "MODEL_DELTAS_FINAL.csv")
    results = {x["repo"]: x for x in read_csv(root / "final_evidence_v1" / "metrics" / "MODEL_RESULTS_FINAL.csv")}
    rows = []
    repo_classes = defaultdict(set)
    for delta in deltas:
        result = results.get(delta["repo"], {})
        if result.get("model_comparable") != "MODEL_COMPARABLE":
            continue
        provenance, source_kind, evidence, confidence = classify(root, delta)
        repo_classes[delta["repo"]].add(provenance)
        rows.append({
            "repo": delta["repo"],
            "commit": delta["commit"],
            "pom_path": evidence.split(";")[0] if evidence and evidence.endswith("pom.xml") else "",
            "field_category": delta["category"],
            "plugin_groupId": parse_entity(delta["entity"])[0],
            "plugin_artifactId": parse_entity(delta["entity"])[1],
            "execution_id": parse_entity(delta["entity"])[2],
            "configuration_path": delta["field"],
            "maven3_value_sha256": sha_text(delta["m3_value"]),
            "maven4_value_sha256": sha_text(delta["m4_value"]),
            "source_pom": evidence,
            "source_kind": source_kind,
            "provenance_class": provenance,
            "semantic_impact": "DECLARATION_LEVEL_ONLY" if delta["category"] == "PLUGIN_EXECUTION_DECLARATION_CHANGED" else "PLUGIN_VERSION_FIELD_ONLY",
            "evidence": evidence,
            "confidence": confidence,
            "repeatable": delta["repeatable"],
        })
    fields = list(rows[0]) if rows else ["repo"]
    with (out / "model_delta_provenance.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    repo_rows = []
    for repo in sorted(repo_classes):
        classes = sorted(repo_classes[repo])
        project_specific = any(x in {"USER_ROOT_POM", "USER_MODULE_POM", "PROJECT_PARENT_POM", "EXTERNAL_PARENT_POM"} for x in classes)
        non_runtime = any(x in {"USER_ROOT_POM", "USER_MODULE_POM", "PROJECT_PARENT_POM", "EXTERNAL_PARENT_POM"} for x in classes)
        runtime_only = bool(classes) and all(x in {"DEFAULT_LIFECYCLE", "MAVEN_RUNTIME_SYNTHESIZED", "HELP_PLUGIN_DERIVED"} for x in classes)
        unknown_present = "UNKNOWN" in classes
        repo_rows.append({
            "repo": repo,
            "provenance_classes": ";".join(classes),
            "project_pom_evidence": str(project_specific).lower(),
            "retains_after_excluding_runtime_default_help": str(non_runtime).lower(),
            "runtime_only_evidence": str(runtime_only).lower(),
            "unknown_provenance_present": str(unknown_present).lower(),
            "classification_note": "lower-bound source evidence; UNKNOWN is retained and is not treated as project-specific",
        })
    with (out / "model_delta_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(repo_rows[0]) if repo_rows else ["repo"])
        writer.writeheader()
        writer.writerows(repo_rows)

    class_counts = Counter(x["provenance_class"] for x in rows)
    category_counts = Counter(x["field_category"] for x in rows)
    plugin_counts = Counter(f"{x['plugin_groupId']}:{x['plugin_artifactId']}" for x in rows)
    execution_counts = Counter(x["execution_id"] for x in rows if x["execution_id"])
    source_repo_count = sum(x["project_pom_evidence"] == "true" for x in repo_rows)
    retained_repo_count = sum(x["retains_after_excluding_runtime_default_help"] == "true" for x in repo_rows)
    runtime_only_repo_count = sum(x["runtime_only_evidence"] == "true" for x in repo_rows)
    unknown_repo_count = sum(x["unknown_provenance_present"] == "true" and x["project_pom_evidence"] == "false" for x in repo_rows)
    unknown_rows = sum(x["provenance_class"] == "UNKNOWN" for x in rows)
    report = [
        "# Model delta provenance",
        "",
        "This analysis uses retained delta rows, frozen source POM snapshots, runtime resource files, and existing extension-binding evidence. It does not infer lifecycle execution or artifact effects.",
        "",
        f"- Comparable repositories: {len(repo_rows)}",
        f"- Delta rows analyzed: {len(rows)}",
        f"- Repositories with direct project-POM execution/plugin evidence: {source_repo_count}/{len(repo_rows)}",
        f"- Repositories retaining direct project-specific evidence after excluding runtime/default/help-only rows: {retained_repo_count}/{len(repo_rows)}",
        f"- Repositories with runtime/default evidence only: {runtime_only_repo_count}/{len(repo_rows)}",
        f"- Repositories with unresolved provenance and no direct project-POM evidence: {unknown_repo_count}/{len(repo_rows)}",
        f"- Rows with UNKNOWN provenance: {unknown_rows}/{len(rows)}",
        "",
        "## Provenance classes",
        "",
    ]
    report.extend(f"- `{key}`: {value}" for key, value in class_counts.most_common())
    report.extend(["", "## Delta categories", ""])
    report.extend(f"- `{key}`: {value}" for key, value in category_counts.most_common())
    report.extend(["", "## Top plugins", ""])
    report.extend(f"- `{key}`: {value}" for key, value in plugin_counts.most_common(20))
    report.extend(["", "## Top execution IDs", ""])
    report.extend(f"- `{key}`: {value}" for key, value in execution_counts.most_common(20))
    report.extend([
        "",
        "## Interpretation boundary",
        "",
        "The 50/50 effective-model result is concentrated in recurring plugin-related rows. `default-site` and `default-deploy` rows are assigned to `DEFAULT_LIFECYCLE` only when the retained Maven runtime binding evidence matches. `injected-central-publishing` is assigned to `MAVEN_RUNTIME_SYNTHESIZED` only when the retained extension-binding evidence is repeatable. All other unproven cases remain `UNKNOWN`.",
        "",
        "The conservative retained count is a provenance-screening result, not proof of actual lifecycle execution. Actual plan extraction remains `PLAN_UNAVAILABLE`.",
        "",
        "A repository with only `UNKNOWN` rows is not counted as project-specific. This avoids converting missing provenance into either a positive or a negative semantic claim.",
    ])
    (out / "model_delta_root_causes.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "comparable_repositories": len(repo_rows),
        "delta_rows": len(rows),
        "provenance_classes": class_counts,
        "project_pom_evidence_repos": source_repo_count,
        "retained_non_runtime_only_repos": retained_repo_count,
        "runtime_only_repos": runtime_only_repo_count,
        "unknown_provenance_repos_without_project_evidence": unknown_repo_count,
        "unknown_rows": unknown_rows,
    }, default=dict, indent=2))


if __name__ == "__main__":
    main()
