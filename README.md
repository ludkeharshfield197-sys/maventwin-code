# MavenTwin code

MavenTwin compares selected project outputs under two Maven runtimes at a fixed
project revision. This repository contains implementation source, synthetic
control source, tests, and configuration examples.

The measurement scripts use Maven Help Plugin 3.5.1 and Maven Dependency Plugin
3.8.1. The final workflow repeats each runtime twice and compares dependency
graphs after successful, parseable, within-runtime-stable executions.

## Requirements

- Python 3.10 or later and Git.
- JDK 21 and Maven 3.9.16 / Maven 4.0.0-rc-7 for runtime measurements.
- Windows for scripts invoking `mvn.cmd` and `taskkill`.
- `matplotlib` for optional result-figure generation by the experiment runner.

Most analysis code uses the Python standard library. Maven measurements require
network access to the selected projects and artifact repositories.

## Configure a workspace

By default, the repository root is the experiment workspace. To use another
directory, set `MAVENTWIN_WORKSPACE` before configuring and running the scripts.

```powershell
python scripts/configure_runtime.py --jdk "C:/tools/jdk-21" --maven3 "C:/tools/apache-maven-3.9.16" --maven4 "C:/tools/apache-maven-4.0.0-rc-7"
```

This creates the local `protocol/runtime_paths.json`, workspace directories, and
minimal Maven settings. Local runtime paths and generated outputs are ignored
by Git. An example configuration is provided in `protocol/`.

## Run offline control tests

```powershell
python -m unittest discover -s tests -v
```

These tests use temporary configuration and synthetic XML/graph values. They
run without installed Maven distributions or research datasets.

## Source layout

- `scripts/final_evidence_runner.py`: final acquisition, target selection,
  repeated measurement, comparison and result aggregation workflow.
- `scripts/harness.py`: runtime environment, command execution and provenance
  recording helpers.
- `scripts/differential.py` and `scripts/mediation.py`: selected model/graph
  normalization, structured comparison and verbose mediation parsing.
- `scripts/model_delta_provenance.py`: source/default provenance classification.
- `scripts/analyze_signatures.py`: recurring structural/value signatures and layer correspondence grouping.
- `scripts/offline_graph_recheck.py`: common-cache graph recheck implementation.
- Other `scripts/`: acquisition, earlier measurement stages, synthetic controls,
  case interpretation and statistical analysis.
- `synthetic/`: marker plugin, lifecycle extension and control-project source.
- `maventwin.py`: legacy one-pair convenience command; the repeated final
  measurement workflow is `scripts/final_evidence_runner.py`.

Experiment runners consume workspace inputs such as `samples/scale_samples.csv`,
frozen project snapshots and earlier-stage metadata. The anonymized replication archive at the repository root supplies those inputs. Analysis scripts expect their documented
result-file schemas; some scripts encode study-specific case classifications.
The release supports source inspection, offline control tests and captured-result reanalysis; new measurements additionally require runtime configuration and artifact materialization.

`plan_from_model` extracts effective-model execution declarations; it does not
capture an actual lifecycle execution plan. Root `-N validate` records concern
the root model. The synthetic controls provide separate execution observations.

## Release contents

The committed source includes measurement and analysis code, synthetic projects, tests,
runtime configuration examples and documentation. `CODE_MANIFEST.json` records
SHA-256 hashes for the source files. The anonymized replication archives ([part 1](maventwin-replication-part1-20261003.zip), [part 2](maventwin-replication-part2-20261003.zip), [part 3](maventwin-replication-part3-20261003.zip)) at the repository root includes empirical CSVs, frozen revision lists and POM snapshots, captured models
and graphs, command records, necessary logs, artifact hash manifests and generated
supplementary tables. Manuscript files, runtime distributions, complete third-party
source checkouts and binary dependency caches are obtained separately.

## Supplementary experiments

`supplemental/` contains common-seed offline graph probes, JDK and target sensitivity,
minimal-POM controls, full-checkout validation, lifecycle model observers, package
plan capture, bounded packaging, full-reactor/targeted tests, migration application,
acquisition characterization, XML controls, and observation-level correspondence.
`ObserverLate.java` calculates ordered lifecycle plans after lifecycle participants
and the measurement goal; it does not execute the requested planned phase.

Configure the workspace with `scripts/configure_runtime.py`, then set
`MAVENTWIN_WORKSPACE_ROOT` and `MAVENTWIN_EXPERIMENT_ROOT` to prepared input and output
directories. Measurement scripts require the recorded input schemas, frozen commits,
artifact materialization and selected-case records. Supplementary runners use Windows
Java launchers, bounded process execution, separate copied repositories and source copies.

With a prepared replication workspace, regenerate captured-result tables using:

```powershell
python supplemental/reproduce_report.py --workspace C:/replication/workspace --experiment-root C:/replication/workspace/supplementary_results
```

Add `--figures` with matplotlib installed to regenerate the layer-count figure.
This command analyzes captured results without contacting external repositories.
The study uses deterministic observation correspondence and post-migration measurements.

Download all three replication parts and extract them into the same directory. Enter
`maventwin-replication/`, then run the captured-result command above. SHA-256
checksums for all three archives are in `maventwin-replication-20261003.sha256.txt`.

## Cohort recheck and comparison baselines

The release includes a common-seed offline ABBA recheck of all 61 acquired
snapshots, including root validation for the fourteen originally unrun entries.
reviewer_followup_analysis.py details summarizes original layer exclusions,
configuration-field ablation, real same-runtime repeat controls, missing-outcome
ranges and capture durations. summarize_reviewer_followup.py recomputes cohort,
applied OpenRewrite recipe and selected-library API results from captured files.
These analyses are included in reproduce_report.py.

reviewer_followup_analysis.py benchmark runs the raw-byte and structured
comparison timing experiment. Timing is specific to the executing host; recorded
five-pass results and the separate Python allocation measurements are retained.
cohort_offline_recheck.py, selected_dependency_execution.py,
openrewrite_full_checkouts.py and openrewrite_frozen_validation.py execute new
measurements with configured runtimes, source inputs and artifact repositories.
The OpenRewrite baseline uses plugin 6.46.1 and rewrite-maven 8.90.4 on full
checkouts; common-repository validation captures compare POMs before and after
the recipe. OpenRewrite downloads use the official
Maven Central registry through the supplied loopback relay; TLS verification
remains enabled on the upstream requests.

## Final lifecycle and mechanism experiments — 2026-10-04

The final supplement ([part 1](maventwin-final-supplement-part1-20261004.zip), [part 2](maventwin-final-supplement-part2-20261004.zip)) adds the offline ABBA lifecycle-plan captures for
all 50 primary model-comparable frozen revisions. Calculated plan differences are
5/50 for package,
12/50 for install and
25/50 for deploy.
The requested phases are calculated, never executed. Central Publishing 0.11.0
minimal counterfactuals and model-mutation probes localize the recurring omission
to participant model mutation through a retained plugin wrapper. Stage traces
refine the 27 initially unmapped rows in twelve repositories.

Extract all three primary replication archives and all final-supplement parts into
one directory, then enter `maventwin-replication/`. Recompute the new summaries:

```powershell
python supplemental/final_round_20261004/reproduce_final.py .
```

The command first expands compact shared/per-project artifact manifests into
byte-identical captured JSON, then reanalyzes captured plans and stage models.
No Maven execution or network access is required. The original reanalysis command
above recomputes the primary and earlier supplementary tables. Each new experiment
contains README.md, commands.json, results.csv, raw_outputs/ and sha256.txt.
Archive checksums are in `maventwin-final-supplement-20261004.sha256.txt`. Original primary populations remain
unchanged; this supplement is a follow-up on the 50 primary model pairs. Manuscript
files and binary dependency caches are distributed separately.
