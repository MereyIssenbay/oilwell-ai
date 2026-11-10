# Phase 2 exploratory data analysis

Actual-data EDA for the 23 acquired 3W v2.0.0 instances at commit `914af287b1cf3e5207dce0da1e9dc08361c9adeb`. The executed [notebook](../../notebooks/01_eda.ipynb) rebuilds these outputs using [eda.py](../../scripts/data/eda.py). All 582,220 observations were included in statistics. No additional telemetry was acquired, original bytes were verified before/after reads, and no model, production preprocessing, features or partition was created.

The source selection is purposive and size-biased, not a prevalence sample. Every inspected source and all 12 published real well IDs are recorded as **development-exposed** in [eda_summary.json](eda_summary.json). An untouched final test set cannot be declared retroactively from these data.

## Reproduce

From the repository root, install `requirements-eda.txt` in the project `.venv`, then run:

```powershell
.\.venv\Scripts\python.exe scripts/data/eda.py
```

Run the notebook with that same environment to display the tables and eight charts. The notebook uses repository-relative paths. The summary records input manifest/registry hashes, every source SHA-256, analysis-script and dependency-file hashes, package versions and exposure identities. The data source is Petrobras and the 3W contributors; original dataset license is CC BY 4.0. Charts and summaries retain that attribution and imply no endorsement.

## Charts and observations

| Chart | Question and measured interpretation |
| --- | --- |
| [01: Class balance](01_class_balance.png) | Row counts and real well support tell different stories. Real rows include 125,940 normal, 107,094 transient, 39,291 event and 50,400 unknown labels. Family 8 supplies 86,422 of 146,385 real abnormal rows (59.04%), from one well ID. Most other real undesirable families have one supporting well; family 9 has none. |
| [02: Missingness by source](02_missing_by_source.png) | Structural source differences are large. P-JUS-BS, P-MON-SDV-P, PT-P and QBS are entirely missing in all selected files. Missingness can reveal source/well identity rather than event dynamics. |
| [03: Missingness by real event family](03_missing_by_real_family.png) | Sensor availability varies with observed labels and their supporting wells. Gray cells mean no observations, not complete availability. Family 9 has no real row support. The raw-class/source table retains denominators and file/well counts. |
| [04: Sensor correlations](04_sensor_correlations.png) | Within-instance correlations differ by source and can reverse sign. P-PDG/P-TPT has defined correlations in only 2/14 real instances (median -0.3107; range -0.8812 to 0.2599), versus 7/7 simulated (median 0.9868; range -0.9707 to 1.0000). The two drawn instances have opposite signs (-0.9855 and 0.9926), so their near-zero median is not evidence of independence. |
| [05: Same-ID normal/event traces](05_real_normal_vs_event.png) | Separate normal and event-1 instances from WELL-00002 show observed P-PDG, P-TPT and T-TPT with shared y-ranges per sensor. Full-resolution labels provide phase shading. Dates differ; this is not a controlled experiment. |
| [06: Event-1 examples by source](06_source_timeseries.png) | Real, simulated and hand-drawn examples differ in duration, annotation schedule and numerical scale. Y-ranges are independent. Source-documented pressure units are used without attempting unverified corrections. One example per source is not a population comparison. |
| [07: Transitions and transient runs](07_label_transitions.png) | There are 61 contiguous raw-label runs and 38 changes within files: 24 known-label changes plus 14 unknown-label boundaries. Four of 14 transient runs are censored. These are observed annotations, not verified physical onset/duration measurements. |
| [08: Normal/abnormal sensor levels](08_normal_abnormal.png) | Per-instance medians avoid treating every correlated row as an independent replicate. Lines join the two conditions only within an instance; isolated dots have one condition. Between-instance differences, source availability and class composition confound any pooled causal comparison. |

The complete raw class, family and phase distributions retain unknown values separately. Selected real event-2/5/7 instances lack the corresponding steady label, while the selected real event-9 file has only normal/unknown rows. Directory names do not assign row labels. `class` and `state` are never sensor inputs; source identifiers are metadata only.

## Tables and methods

- [class_balance.csv](class_balance.csv): raw/family row counts, instances and supporting published real well IDs by origin. Real well counts are not claimed physical-asset verification.
- [missing_by_source_class.csv](missing_by_source_class.csv): source/raw-label/sensor counts, missing fractions, row denominators, supporting instances/wells and instances/wells with observed values. Family is a documented label-derived grouping for EDA only.
- [sensor_availability.csv](sensor_availability.csv): per-instance availability and distinct observed values. Present but constant channels are identified; zero values are not silently converted to missing. In particular, some selected P-PDG series are constant zero despite full availability.
- [correlations_within_instance.csv](correlations_within_instance.csv): all sensor pairs per source instance, pairwise-complete counts and Pearson correlation. At least 120 jointly observed rows are required; constants and undefined correlations are missing. Only the exact 27-sensor allowlist enters these calculations.
- [correlation_summary.csv](correlation_summary.csv): equal-instance medians/ranges of defined correlations by source. `valid_instance_count` is the support of the median. `pair_count_total` counts all jointly observed rows, including instances with undefined/constant correlations; it is not the median's statistical sample size.
- [label_runs.csv](label_runs.csv): source-local contiguous raw-label runs, phase/family, positions, source timestamps, one-second support duration and left/right censoring.
- [transitions.csv](transitions.csv): adjacent one-second label changes within an instance. Unknown boundaries remain separate diagnostics. No transition is counted across files or timestamp gaps.
- [normal_abnormal_summary.csv](normal_abnormal_summary.csv): per-instance medians and quartiles using row label 0 versus documented nonzero labels, with row and sensor-availability denominators. Unknown labels are excluded from this conditional comparison, never inferred normal.

Correlation is descriptive, not causal evidence or a feature-selection result. Pairwise-complete support varies by sensor, instance and source; all observations are autocorrelated. No independence-based significance tests or confidence intervals are asserted. An equal-instance median can still obscure heterogeneity; consult its range and per-instance table.

Run duration is observed support at the verified one-second cadence: one observation contributes one second, while its last-minus-first elapsed duration is zero. A run is censored when it touches an instance edge, a missing-label interval or a timestamp gap. Unknown-to-known annotation boundaries must not be evaluated as confirmed event onset.

Only line-plot display is decimated: deterministic evenly spaced row positions, at most 1,500 points per contiguous finite segment. Missing values and timestamp gaps split line segments. Label shading uses all original labels and source timestamps. Plot scaling from Pa to MPa is a display unit conversion, not a modified data product. No source timestamp is localized to UTC.

## Risks and next modeling decision

The plots show patterns to test, not detections already demonstrated. Main risks are source/missingness shortcuts, constant channels, filename/directory/target leakage, repeated well identity, label schedules aligned to source elapsed time, synthetic-domain differences, upstream interpolation and windows crossing source/partition boundaries. All source labels and future context remain prohibited prediction inputs.

Published real well IDs are a useful grouping key across event directories, but private physical asset identity is not independently verified. Whole related instances and their published well groups must stay together before any windows. The current subset cannot support a well-disjoint three-way evaluation for the intended multiclass MVP; more independently approved data would be needed. See [split strategy](../../docs/SPLIT_STRATEGY.md), [testable hypotheses](../../docs/ML_HYPOTHESES.md), and [independent review](../../docs/reviews/PHASE_2.md).
