"""Derive manuscript summaries from frozen records; execute no Maven commands."""
import os
from pathlib import Path
from collections import defaultdict, Counter
import csv
import hashlib
import json
import re

ROOT = Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()
OUT = ROOT / "analysis_outputs"
DERIVED = OUT / "signatures"
DERIVED.mkdir(parents=True, exist_ok=True)

def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write(name, rows):
    with (DERIVED / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def normalize(value):
    # Replace the repository-local snapshot prefix, preserving its relative suffix.
    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            return re.sub(r"^(?:[A-Za-z]:)?/.*?/(?:final_evidence_v1|paper_fix_v1)/snapshots/[^/]+", "<SNAPSHOT>", v.replace("\\", "/"))
        return v
    try:
        return json.dumps(walk(json.loads(value)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except json.JSONDecodeError:
        return walk(value)

def main():
    deltas = read(ROOT / "final_evidence_v1/MODEL_DELTAS_FINAL.csv")
    provenance = read(ROOT / "artifacts/reviewer_revision/model/model_delta_summary.csv")
    classes = {r["repo"]: ("project_pom" if r["project_pom_evidence"] == "true" else "runtime_default" if r["runtime_only_evidence"] == "true" else "unresolved") for r in provenance}
    structural = defaultdict(set)
    exact = defaultdict(set)
    labels = defaultdict(set)
    memberships = []
    for r in deltas:
        key = (r["category"], r["entity"], r["field"])
        structural[key].add(r["repo"])
        value_key = key + (normalize(r["m3_value"]), normalize(r["m4_value"]))
        exact[value_key].add(r["repo"])
        memberships.append(dict(repo=r["repo"], category=key[0], entity=key[1], field=key[2], signature_sha256=hashlib.sha256(json.dumps(value_key, ensure_ascii=False).encode()).hexdigest()))
        labels[r["category"]].add(r["repo"])
        if r["field"] == "configuration":
            labels["PLUGIN_CONFIGURATION"].add(r["repo"])
    assert len(deltas) == 269 and Counter(classes.values()) == {"project_pom": 20, "runtime_default": 18, "unresolved": 12}
    structural_rows = [dict(category=k[0], entity=k[1], field=k[2], repositories=len(v), project_pom=sum(classes[r] == "project_pom" for r in v), runtime_default=sum(classes[r] == "runtime_default" for r in v), unresolved=sum(classes[r] == "unresolved" for r in v)) for k,v in sorted(structural.items(), key=lambda kv:(-len(kv[1]),kv[0]))]
    exact_rows = [dict(signature_sha256=hashlib.sha256(json.dumps(k, ensure_ascii=False).encode()).hexdigest(), category=k[0], entity=k[1], field=k[2], repositories=len(v), repository_ids=";".join(sorted(v)), normalized_m3=k[3], normalized_m4=k[4]) for k,v in sorted(exact.items(), key=lambda kv:(-len(kv[1]),kv[0]))]
    field_rows = [dict(field_category=k, repositories=len(v), project_pom=sum(classes[r] == "project_pom" for r in v), runtime_default=sum(classes[r] == "runtime_default" for r in v), unresolved=sum(classes[r] == "unresolved" for r in v)) for k,v in labels.items()]
    write("MODEL_STRUCTURAL_SIGNATURES.csv", structural_rows)
    write("MODEL_VALUE_SIGNATURES.csv", exact_rows)
    write("MODEL_SIGNATURE_MEMBERSHIP.csv", memberships)
    write("MODEL_FIELD_PROVENANCE.csv", field_rows)
    paper = read(ROOT / "final_evidence_v1/FINAL_PAPER_RESULTS.csv")
    layer_rows = []
    for layer, key in [("model", "model_semantic_divergence"), ("graph", "resolution_divergence"), ("validation", "confirmed_validation_regression")]:
        selected = [r for r in paper if r[key] == "true"]
        counts = Counter(r["mvnup_relation"] for r in selected)
        layer_rows.append(dict(layer=layer, observations=len(selected), direct=counts["DIRECTLY_SIGNALED"], related=counts["RELATED_BUT_NOT_SPECIFIC"], not_applicable=counts["NOT_APPLICABLE"], unavailable=counts["MVNUP_UNAVAILABLE"]))
    write("MVNUP_LAYER_MAPPING.csv", layer_rows)
    summary = dict(delta_rows=len(deltas), structural_signatures=len(structural), structural_recurring=sum(len(v)>1 for v in structural.values()), structural_single_repository=sum(len(v)==1 for v in structural.values()), normalized_value_signatures=len(exact), value_recurring=sum(len(v)>1 for v in exact.values()), value_single_repository=sum(len(v)==1 for v in exact.values()), provenance=dict(Counter(classes.values())), field_provenance=field_rows, mvnup_layers=layer_rows)
    (DERIVED / "EVIDENCE_SUMMARY.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
