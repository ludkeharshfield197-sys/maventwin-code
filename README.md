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
frozen project snapshots and earlier-stage metadata. Those inputs are not part
of this code release. Analysis and adjudication scripts expect their documented
result-file schemas; some scripts encode study-specific case classifications.
The code release therefore supports source inspection and offline control tests;
reproducing a study run also requires preparing its input workspace.

`plan_from_model` extracts effective-model execution declarations; it does not
capture an actual lifecycle execution plan. Root `-N validate` records concern
the root model. The synthetic controls provide separate execution observations.

## Release contents

The committed files comprise source code, source build descriptors, runtime
configuration examples and usage documentation. The release excludes manuscript
sources/PDFs, empirical CSVs, raw logs, project checkouts, downloaded third-party
source, Maven/JDK binaries and dependency caches. `CODE_MANIFEST.json` lists the
released files and their SHA-256 hashes.
