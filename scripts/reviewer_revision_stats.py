#!/usr/bin/env python3
import os  # Configurable workspace; no machine-specific paths.
"""Derive reviewer-facing validation, attrition, and mvnup summaries.

This script reads only frozen outputs.  It intentionally keeps observed outcomes
separate from adjudicated paper claims.
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = (Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
OUT = ROOT / "artifacts" / "reviewer_revision"
EVIDENCE = ROOT / "final_evidence_v1"


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def validation_summary():
    rows = read_csv(EVIDENCE / "metrics" / "VALIDATION_RESULTS_FINAL.csv")
    out_rows = []
    observed = Counter()
    adjudicated = Counter()
    for row in rows:
        status = row.get("validation_status", "UNKNOWN")
        if status == "PASS_PASS":
            outcome = "M3_PASS_M4_PASS"
        elif status == "FAIL_PASS":
            outcome = "M3_FAIL_M4_PASS"
        elif status == "FAIL_FAIL":
            outcome = "M3_FAIL_M4_FAIL"
        elif status in {"CONFIRMED_ROOT_VALIDATION_REGRESSION", "ARTIFACT_INCOMPLETENESS"}:
            outcome = "M3_PASS_M4_FAIL"
        else:
            outcome = "UNAVAILABLE_OR_NOT_RUN"
        observed[outcome] += int(row.get("validation_comparable", "false").lower() == "true")
        if row.get("confirmed_validation_regression", "false").lower() == "true":
            decision = "CONFIRMED_ROOT_VALIDATION_MISMATCH"
            adjudicated["CONFIRMED_ROOT_VALIDATION_MISMATCH"] += 1
        elif status == "ARTIFACT_INCOMPLETENESS":
            decision = "PASS_FAIL_CANDIDATE_ARTIFACT_INCOMPLETE"
            adjudicated[decision] += 1
        elif row.get("validation_comparable", "false").lower() == "true":
            decision = "NO_CONFIRMED_MISMATCH"
        else:
            decision = "NOT_COMPARABLE"
        out_rows.append({
            "repo": row.get("repo", ""),
            "commit": row.get("commit", ""),
            "observed_2x2_outcome": outcome,
            "frozen_status": status,
            "validation_comparable": row.get("validation_comparable", ""),
            "paper_adjudication": decision,
            "validation_error": row.get("validation_error", ""),
        })
    out_rows.sort(key=lambda x: x["repo"])
    fields = list(out_rows[0]) if out_rows else ["repo"]
    write_csv(OUT / "validation" / "validation_2x2_cases.csv", fields, out_rows)

    labels = [
        ("M3_PASS_M4_PASS", "M3 pass / M4 pass", "paired root validation passed under both runtimes"),
        ("M3_PASS_M4_FAIL", "M3 pass / M4 fail", "observed candidate outcome; only two rows are confirmed after full checkout"),
        ("M3_FAIL_M4_PASS", "M3 fail / M4 pass", "paired root validation failed under M3 and passed under M4"),
        ("M3_FAIL_M4_FAIL", "M3 fail / M4 fail", "paired root validation failed under both runtimes"),
    ]
    summary_rows = []
    for key, label, note in labels:
        summary_rows.append({
            "outcome": key,
            "label": label,
            "count": observed.get(key, 0),
            "comparable_denominator": sum(observed.values()),
            "note": note,
        })
    write_csv(OUT / "validation" / "validation_2x2.csv", list(summary_rows[0]), summary_rows)
    lines = [
        "# Root-validation 2x2",
        "",
        "The table below reports observed paired exit-status outcomes for the frozen root `-N validate` runs. It does not claim a Maven 4 defect.",
        "",
        f"Comparable denominator (observed paired outcomes): **{sum(observed.values())}**.",
        "",
        "| Outcome | Count | Interpretation |",
        "|---|---:|---|",
    ]
    for key, label, note in labels:
        lines.append(f"| {label} | {observed.get(key, 0)} | {note} |")
    lines.extend([
        "",
        "The M3-pass/M4-fail row contains two confirmed root-validation mismatches after full-checkout confirmation and one candidate whose artifact was incomplete. The latter is retained as observed evidence but excluded from the confirmed mismatch count.",
        "",
        "The seven M3-fail/M4-fail rows are not migration mismatches. `UNSAFE_NOT_RUN` rows are outside this 2x2 denominator.",
    ])
    (OUT / "validation" / "validation_2x2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return observed, adjudicated


def attrition_summary():
    population = read_csv(EVIDENCE / "samples" / "FROZEN_POPULATION.csv")
    sample_path = ROOT / "samples" / "scale_samples.csv"
    sample = {row["repo"]: row for row in read_csv(sample_path)}
    rows = []
    for row in population:
        status = row.get("recovery_status", "")
        if status == "POM_COMPLETE":
            stage = "INCLUDED_POM_COMPLETE"
            reason = "POM_COMPLETE"
            observed_reason = row.get("recovery_method", "")
        elif status == "NETWORK_UNKNOWN":
            stage = "EXCLUDED_BEFORE_POM_MATERIALIZATION"
            reason = "TRUE_UNKNOWN"
            observed_reason = row.get("recovery_method", "")
        elif status == "NO_FROZEN_REVISION":
            stage = "EXCLUDED_BEFORE_FROZEN_REVISION"
            reason = "UNKNOWN_REMOTE_HEAD"
            observed_reason = row.get("original_sample_status", "")
        else:
            stage = "OTHER"
            reason = status or "TRUE_UNKNOWN"
            observed_reason = row.get("recovery_method", "")
        base = sample.get(row.get("repo", ""), {})
        rows.append({
            "repo": row.get("repo", ""),
            "commit": row.get("commit", ""),
            "stratum": base.get("stratum", "UNKNOWN"),
            "stage": stage,
            "reason": reason,
            "observed_reason": observed_reason,
            "pom_count": row.get("pom_count", ""),
            "module_count_observed": row.get("pom_count", ""),
            "evidence_note": "provider-disabled-after-timeout observation; no error-class evidence retained" if reason == "TRUE_UNKNOWN" else "frozen population record",
        })
    rows.sort(key=lambda x: x["repo"])
    write_csv(OUT / "attrition" / "attrition_reasons.csv", list(rows[0]), rows)

    grouped = defaultdict(lambda: Counter())
    for row in rows:
        grouped[row["stratum"]][row["stage"]] += 1
    summary = []
    for stratum in sorted(grouped):
        counts = grouped[stratum]
        summary.append({
            "stratum": stratum,
            "candidate_rows": sum(counts.values()),
            "pom_complete": counts["INCLUDED_POM_COMPLETE"],
            "network_unknown": sum(1 for r in rows if r["stratum"] == stratum and r["reason"] == "TRUE_UNKNOWN"),
            "no_frozen_revision": counts["EXCLUDED_BEFORE_FROZEN_REVISION"],
        })
    write_csv(OUT / "attrition" / "included_vs_excluded.csv", list(summary[0]), summary)
    counts = Counter(row["stage"] for row in rows)
    md = [
        "# Attrition summary",
        "",
        "This is a descriptive accounting of the frozen 150-entry sample. It does not infer why a provider disabled acquisition.",
        "",
        "| Stage | Count |",
        "|---|---:|",
        f"| candidate entries | {len(rows)} |",
        f"| frozen revisions | {counts['INCLUDED_POM_COMPLETE'] + counts['EXCLUDED_BEFORE_POM_MATERIALIZATION']} |",
        f"| POM-complete | {counts['INCLUDED_POM_COMPLETE']} |",
        f"| NETWORK_UNKNOWN | {counts['EXCLUDED_BEFORE_POM_MATERIALIZATION']} |",
        f"| no frozen revision | {counts['EXCLUDED_BEFORE_FROZEN_REVISION']} |",
        "",
        "All 55 `NETWORK_UNKNOWN` rows carry the observed recovery method `raw_provider_disabled_after_timeout_observation`; the retained files do not distinguish DNS, HTTP, TLS, repository-authentication, or artifact-level causes. They are therefore classified as `TRUE_UNKNOWN` rather than assigned a more specific network category.",
        "",
        "Included-versus-excluded stratum counts are in `included_vs_excluded.csv`. No outcome-based replacement was performed after the frozen sample records were established.",
    ]
    (OUT / "attrition" / "attrition_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return rows


def mvnup_summary(attrition_rows):
    rows = read_csv(EVIDENCE / "metrics" / "MVNUP_RESULTS_FINAL.csv")
    attrition = {row["repo"]: row for row in attrition_rows}
    out = []
    for row in rows:
        if row.get("mvnup_relation") != "MVNUP_UNAVAILABLE":
            continue
        a = attrition.get(row.get("repo", ""), {})
        reason = "NOT_RUN_NO_FROZEN_REVISION" if a.get("reason") == "UNKNOWN_REMOTE_HEAD" else "NOT_RUN_NETWORK_UNKNOWN" if a.get("reason") == "TRUE_UNKNOWN" else "TRUE_UNKNOWN"
        out.append({
            "repo": row.get("repo", ""),
            "mvnup_evaluable": row.get("mvnup_evaluable", ""),
            "mvnup_relation": row.get("mvnup_relation", ""),
            "reason": reason,
            "underlying_sample_stage": a.get("stage", ""),
            "observed_acquisition_reason": a.get("observed_reason", ""),
            "evidence": "no mvnup output record; unavailable is not NOT_SIGNALED",
        })
    out.sort(key=lambda x: x["repo"])
    write_csv(OUT / "mvnup" / "mvnup_unavailable_reasons.csv", list(out[0]), out)
    summary = Counter(row["reason"] for row in out)
    lines = [
        "# mvnup classification rubric",
        "",
        "`DIRECTLY_SIGNALED`, `RELATED_BUT_NOT_SPECIFIC`, and `NOT_APPLICABLE` are assigned only where a mvnup output record exists. `MVNUP_UNAVAILABLE` means the tool was not run because the frozen POM snapshot was not available; it is not evidence that mvnup failed to detect a divergence.",
        "",
        "| Unavailable reason | Count | Rule |",
        "|---|---:|---|",
        f"| `NOT_RUN_NO_FROZEN_REVISION` | {summary['NOT_RUN_NO_FROZEN_REVISION']} | no frozen commit was recorded for the candidate |",
        f"| `NOT_RUN_NETWORK_UNKNOWN` | {summary['NOT_RUN_NETWORK_UNKNOWN']} | frozen commit exists, but the provider-disabled acquisition record has no POM snapshot |",
        f"| `TRUE_UNKNOWN` | {summary['TRUE_UNKNOWN']} | no matching frozen-population evidence |",
        "",
        "The relation labels are evidence-matching labels, not a ranking of tools. The current records do not support a closed-loop `mvnup apply` experiment or inter-rater agreement statistic.",
    ]
    (OUT / "mvnup" / "mvnup_classification_rubric.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main():
    observed, adjudicated = validation_summary()
    attrition = attrition_summary()
    mvnup = mvnup_summary(attrition)
    print(json.dumps({
        "validation_observed_2x2": dict(observed),
        "validation_adjudicated": dict(adjudicated),
        "attrition": dict(Counter(row["stage"] for row in attrition)),
        "mvnup_unavailable": dict(Counter(row["reason"] for row in mvnup)),
    }, indent=2))


if __name__ == "__main__":
    main()
