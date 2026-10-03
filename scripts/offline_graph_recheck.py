#!/usr/bin/env python3
import os  # Configurable workspace; no machine-specific paths.
"""Materialize a shared local-repository seed and rerun the two graph positives offline."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


CASES = {
    "commons-compress": {
        "repo": "apache/commons-compress",
        "commit": "19278c4f776af4a11e071e34e3b3ceca1ef735ae",
        "snapshot": "final_evidence_v1/snapshots/apache__commons-compress",
        "artifact_targets": ["org.slf4j:jcl-over-slf4j"],
    },
    "spring-data-neo4j": {
        "repo": "spring-projects/spring-data-neo4j",
        "commit": "25ee559847ef5da5202c593f742552c9a169f944",
        "snapshot": "final_evidence_v1/snapshots/spring-projects__spring-data-neo4j",
        "artifact_targets": [
            "io.netty:netty-handler",
            "io.netty:netty-tcnative-classes",
            "io.netty:netty-buffer",
        ],
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_manifest(root):
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rows.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": sha256(path)})
    return rows


def materialize_seed(root, out):
    seed = out / "frozen_repo" / "seed-local-repo"
    source_roots = [root / "paper_fix_v1" / "local_repos" / "m3", root / "paper_fix_v1" / "local_repos" / "m4"]
    seed.mkdir(parents=True, exist_ok=True)
    conflicts = []
    copied = 0
    for source in source_roots:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            target = seed / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                left = sha256(target)
                right = sha256(path)
                if left != right:
                    conflicts.append({"path": relative.as_posix(), "existing_sha256": left, "incoming_sha256": right, "incoming_source": source.name})
                continue
            shutil.copy2(path, target)
            copied += 1
    manifest = file_manifest(seed)
    (out / "frozen_repo" / "repository_sha256_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "frozen_repo" / "repository_sha256_manifest.txt").write_text("\n".join(f"{x['sha256']}  {x['path']}" for x in manifest) + "\n", encoding="utf-8")
    (out / "frozen_repo" / "seed_materialization.json").write_text(json.dumps({"sources": [str(x) for x in source_roots], "copied_files": copied, "seed_files": len(manifest), "conflicts": conflicts}, indent=2), encoding="utf-8")
    return seed, conflicts, len(manifest)


def run_one(root, out, case_name, runtime, repetition, sequence, seed, target):
    paths = json.loads((root / "protocol" / "runtime_paths.json").read_text(encoding="utf-8"))
    runtime_home = Path(paths["m3" if runtime == "m3" else "m4"])
    jdk_home = Path(paths["jdk"])
    case_out = out / case_name / sequence / runtime / f"r{repetition}"
    case_out.mkdir(parents=True, exist_ok=True)
    local_repo = case_out / "local-repo"
    if local_repo.exists():
        shutil.rmtree(local_repo)
    shutil.copytree(seed, local_repo)
    snapshot = root / CASES[case_name]["snapshot"]
    pom = snapshot / target
    tree = case_out / "dependency-tree.json"
    stdout = case_out / "stdout.txt"
    stderr = case_out / "stderr.txt"
    settings = root / "protocol" / "settings.xml"
    mvn = runtime_home / "bin" / "mvn.cmd"
    command = [str(mvn), "-B", "-ntp", "-o", "-e", "-s", str(settings), "-gs", str(settings), f"-Dmaven.repo.local={local_repo}", "-Dstyle.color=never", "-N", "-f", str(pom), "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree", "-DoutputType=json", f"-DoutputFile={tree}"]
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(jdk_home)
    environment["MAVEN_OPTS"] = f"-Dmaven.multiModuleProjectDirectory={snapshot}"
    start = datetime.now(timezone.utc).isoformat()
    began = time.time()
    with stdout.open("wb") as so, stderr.open("wb") as se:
        completed = subprocess.run(command, cwd=str(snapshot), env=environment, stdout=so, stderr=se, stdin=subprocess.DEVNULL)
    record = {
        "case": case_name,
        "runtime": runtime,
        "repetition": repetition,
        "sequence": sequence,
        "repo": CASES[case_name]["repo"],
        "commit": CASES[case_name]["commit"],
        "target_pom": target,
        "command": command,
        "cwd": str(snapshot),
        "java_home": str(jdk_home),
        "maven_home": str(runtime_home),
        "local_repo": str(local_repo),
        "start_utc": start,
        "end_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - began, 3),
        "exit_code": completed.returncode,
        "tree_exists": tree.exists(),
        "tree_parseable": False,
    }
    if tree.exists():
        try:
            json.loads(tree.read_text(encoding="utf-8"))
            record["tree_parseable"] = True
        except (OSError, json.JSONDecodeError) as exc:
            record["parse_error"] = str(exc)
    (case_out / "environment.json").write_text(json.dumps({"java_home": str(jdk_home), "maven_home": str(runtime_home), "os": os.name, "cwd": str(snapshot)}, indent=2), encoding="utf-8")
    (case_out / "command.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def flatten(node, path=()):
    if not isinstance(node, dict):
        return []
    rows = []
    gid = node.get("groupId")
    aid = node.get("artifactId")
    if gid and aid:
        rows.append({"groupId": gid, "artifactId": aid, "version": node.get("version", ""), "type": node.get("type", "jar"), "classifier": node.get("classifier", ""), "scope": node.get("scope", ""), "path": list(path)})
        current = path + (f"{gid}:{aid}:{node.get('version', '')}",)
    else:
        current = path
    for child in node.get("children", []) or []:
        rows.extend(flatten(child, current))
    return rows


def selected(tree_path, targets):
    data = json.loads(tree_path.read_text(encoding="utf-8"))
    rows = flatten(data)
    return [x for x in rows if f"{x['groupId']}:{x['artifactId']}" in targets]


def summarize(root, out, case_name, records):
    targets = set(CASES[case_name]["artifact_targets"])
    by_runtime = {}
    for runtime in ("m3", "m4"):
        reps = []
        for record in records:
            if record["runtime"] != runtime:
                continue
            path = out / case_name / record["sequence"] / runtime / f"r{record['repetition']}" / "dependency-tree.json"
            reps.append({"record": record, "selected": selected(path, targets) if record["tree_parseable"] else []})
        by_runtime[runtime] = reps
    stable = all(len(by_runtime[x]) == 2 and by_runtime[x][0]["record"]["exit_code"] == 0 and by_runtime[x][1]["record"]["exit_code"] == 0 and by_runtime[x][0]["selected"] == by_runtime[x][1]["selected"] for x in ("m3", "m4"))
    m3 = by_runtime["m3"][0]["selected"] if len(by_runtime["m3"]) == 2 else []
    m4 = by_runtime["m4"][0]["selected"] if len(by_runtime["m4"]) == 2 else []
    reproduced = stable and m3 != m4
    classification = "REPRODUCED" if reproduced else ("NOT_REPRODUCED" if stable else "INCONCLUSIVE")
    summary = {"case": case_name, "repo": CASES[case_name]["repo"], "commit": CASES[case_name]["commit"], "target_pom": "pom.xml", "classification": classification, "offline": True, "stable_within_runtime": stable, "m3_selected": m3, "m4_selected": m4, "records": records}
    (out / case_name / "graph_diff.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()))
    parser.add_argument("--out", type=Path, default=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve() / 'artifacts/reviewer_revision/graph'))
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    seed, conflicts, seed_files = materialize_seed(root, out)
    summaries = []
    all_records = []
    for case_name in CASES:
        records = []
        for sequence, order in (("m3-then-m4", ("m3", "m4")), ("m4-then-m3", ("m4", "m3"))):
            for runtime in order:
                for repetition in (1, 2):
                    records.append(run_one(root, out, case_name, runtime, repetition, sequence, seed, "pom.xml"))
        summaries.append(summarize(root, out, case_name, records))
        all_records.extend(records)
    fields = ["case", "repo", "commit", "target_pom", "classification", "offline", "stable_within_runtime"]
    with (out / "offline_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in summaries:
            writer.writerow({key: row.get(key) for key in fields})
    (out / "commands.log").write_text("\n".join(json.dumps(x) for x in all_records) + "\n", encoding="utf-8")
    (out / "offline_recheck_status.json").write_text(json.dumps({"seed_files": seed_files, "seed_conflicts": len(conflicts), "summaries": summaries}, indent=2), encoding="utf-8")
    print(json.dumps({"seed_files": seed_files, "seed_conflicts": len(conflicts), "summaries": [{"case": x["case"], "classification": x["classification"]} for x in summaries]}, indent=2))


if __name__ == "__main__":
    main()
