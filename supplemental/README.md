# Supplementary MavenTwin experiments

This directory contains the supplementary experiment runners and captured-result analyses. The anonymized replication archive at the repository root supplies frozen inputs, result tables, commands and necessary logs.

- `experiments.py`: separate copied artifact repositories and bounded Maven executions.
- `Observer.java` and `ObserverLate.java`: in-memory models and ordered lifecycle plans without executing the planned phase.
- `minimal_graphs.py`, `target_sensitivity.py`, `release_sensitivity.py`: dependency, target and runtime controls.
- `apply_cases.py`: migration application and post-edit comparisons.
- `build_impact.py`, `reactor_tests.py`, `reactor_followup.py`: packaging, reactor and targeted test runs.
- `analysis.py`, `missingness.py`, `serialization_controls.py`, `rq3_refine.py`: model ablation, acquisition characterization, XML controls and deterministic correspondence.
- `reproduce_report.py`: one command to recompute captured-result tables.

After extracting the replication archive, run:

```powershell
python supplemental/reproduce_report.py --workspace . --experiment-root supplementary_results
```

Reanalysis uses captured files and does not execute Maven or access external repositories. Configure the recorded JDK and Maven versions before new measurements. Runtime distributions and binary dependency caches are obtained separately; their versions and artifact hash manifests are included. Independent human annotation was not conducted.
