# Independent Phase 2 EDA review

Review date: 2026-11-10. **Complete for Phase 2:** no unresolved blocking defect in the reviewed EDA artifacts. The subset is inadequate for an independent, fully supported three-way multiclass well-grouped evaluation. This review does not authorize acquisition, preprocessing or model training.

## Scope and independence

The reviewer owns this report and `tests/qa/test_eda_integrity.py` only. The EDA notebook/module/figures, ML hypotheses and split strategy are owned by other agents. Existing raw files are read-only; no additional telemetry is acquired. The review distinguishes descriptive exploration from model validation, and documented pseudonymous grouping from independently verified physical identity.

## Grouping evidence and split limits

The primary author manuscript's [dataset structure section](https://arxiv.org/html/2507.01048v1#S3.SS2) assigns a persistent ID to each real well across event directories, while timestamps distinguish its individual instances. It also describes event-local numbering for simulated and hand-drawn files. This supports grouping real files by published `WELL-xxxxx` identifier across directories. No public physical-asset crosswalk was verified; claims should refer to held-out published well IDs rather than independently verified physical assets.

The acquired subset has 12 real well IDs. Observed normal rows occur in ten IDs; undesirable families 1, 2, 3, 5, 6, 7 and 8 each occur in one ID, family 4 in two, and family 9 in none. Thus a three-way real grouped partition containing every selected undesirable family in train, validation and test is not supported by this subset. Row counts do not remedy this lack of group support. An instance split would additionally leak `WELL-00002`, which has selected normal/event-1/event-4 files.

All 23 files have been inspected during EDA and hypothesis formation. They cannot later be called an untouched final test set. For an unseen-well evaluation, their 12 published well IDs should remain development-exposed even if new files from those same IDs are subsequently acquired. A future protected test cohort requires new disjoint groups and duplicate/overlap checks against development data. If only instance grouping is possible in a future source, explicitly limit claims to held-out instances with possible same-well leakage; do not present it as equivalent to well-disjoint evaluation.

## Independent raw-data checks

A separate inline Python script read the 23 original files, checked SHA-256 against the acquisition manifest, recomputed label runs and within-file changes, and calculated selected pairwise-complete correlations without importing the EDA module.

| Check | Observed result |
| --- | --- |
| Total rows | 582,220 |
| Raw-label runs, including unknown | 61: 37 real, 19 simulated, five drawn |
| Within-file label-change boundaries | 38: 24 changes between known labels, 14 unknown-to-known boundaries |
| All original file hashes after reads | Matched the manifest and remained unchanged |
| P-PDG/P-TPT, pooled within real sources | 279,894 paired rows; Pearson r = 0.8094369182 |
| P-PDG/P-TPT, pooled within simulated sources | 201,894 paired rows; Pearson r = 0.1152155525 |
| P-PDG/P-TPT, pooled within hand-drawn sources | 57,601 paired rows; Pearson r = 0.9704929240 |

These pooled correlations were an independent diagnostic, **not** the statistic reported in the final EDA heatmap. The EDA computes each correlation within an instance, then summarizes the valid coefficients with an equal-instance median. Independently reconciled P-PDG/P-TPT summaries are:

| Origin | Valid instances / selected instances | Median within-instance r | Range of valid r |
| --- | --- | --- | --- |
| Real | 2 / 14 | -0.310667 | -0.881231 to 0.259898 |
| Simulated | 7 / 7 | 0.986770 | -0.970710 to 0.999992 |
| Drawn | 2 / 2 | 0.003558 | -0.985493 to 0.992609 |

The substantial difference from pooled coefficients illustrates aggregation sensitivity. Pair counts are paired observations, not independent sample sizes; the summary's total pair count includes instances whose coefficient is undefined. Correlations require at least 120 paired, nonconstant observations, and undefined values are retained as missing. Neither aggregation establishes physical causality or justifies selecting a feature without later train-only validation.

## Risks communicated to owners

- Treat `class` and `state` as labels, never sensor inputs or ordinary numeric correlation variables. Directory labels are not labels for every row.
- Do not count a transition between concatenated files, across a timestamp gap, or through an unknown label interval. Unknown boundaries are useful diagnostics but not verified event onsets.
- A run after unknown time/labels is left-censored; a run before unknown time/labels or a file end is right-censored. Selected event-7 data has no observed transition to steady label 7. Some real steady events start after unknown labels, so their true onset cannot be measured.
- Missingness and availability reveal origin/well/class mixtures. Source-separated correlations and pairwise support are required; source-pooled matrices can still be confounded by instances.
- Keep plots tied to actual full-resolution labels, disclose any sensor decimation, preserve missing gaps and avoid interpreting decimated curves as high-frequency behavior.
- The subset was chosen for inexpensive inspection coverage, not prevalence estimation or independent model evaluation. All modeling hypotheses remain untested.

## Artifact verification and disposition

The reviewer independently read the raw Parquets and reconciled the following against the final [EDA tables](../../reports/eda/README.md), without importing the EDA aggregation implementation:

| Reconciliation | Actual outcome |
| --- | --- |
| 52 class-balance records | Label counts and instance/well support matched |
| 837 source/class/sensor missingness records | Counts, fractions and support denominators matched |
| 621 instance/sensor availability records | Observation counts, distinct values and constant flags matched |
| 8,073 within-instance sensor-pair records | Pair counts matched; NumPy pairwise-complete Pearson values matched within `rtol=1e-7, atol=1e-9`; undefined cases matched |
| 1,053 origin/sensor-pair summary records | Median, extrema, valid-instance count and total pair support matched |
| 158 instance/condition/sensor records | Labeled and observed counts, median and quartiles matched |
| 61 runs and 38 transitions | Labels, positions, lengths, support durations and within-file changes matched |
| Original Parquet hashes | All 23 matched the acquisition manifest before and after independent reads |

These checks used inline Python commands under the project `.venv`; they are independent one-time artifact audits, not additional persisted automated tests. Counts describe this selected subset and do not estimate dataset-wide or operational prevalence.

The following persisted offline test command was executed by the reviewer:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/qa/test_eda_integrity.py -q -p no:cacheprovider --tb=short
```

**Actual result: 16 passed in 0.78 seconds, no failures or skips.** The tests exercise unknown-label censoring, timestamp gaps, separate-instance boundaries, single-observation support duration, invalid time order, pairwise missingness, large pair counts, constant/empty correlations and exclusion of `class`, `state` and timestamps from sensor inputs. They do not test training, inference, application behavior or deployment.

The orchestrator separately reported the final combined `tests/data tests/qa` run: **74 passed in 1.00 seconds, zero failures or skips**, with `pip check` clean. This combined result was reported by integration, not independently rerun by the reviewer.

The reviewer inspected the executed [notebook](../../notebooks/01_eda.ipynb): eight code cells have execution counts 1 through 8, there are no stored error outputs, and SHA-256 comparison confirms all eight embedded PNGs exactly match the current report images. The notebook was executed by the EDA owner; the reviewer inspected its executed artifact rather than running a second kernel. Selected figures were visually inspected, including the final normal/event comparison, origin comparison and transition plots. Parent integration separately inspected all eight figures.

Review feedback resolved by the owners included a possible 1,501st plotted point despite a declared 1,500-point cap, missing timestamp-gap segmentation, footer/axis overlap, comparable y-limits for the normal/event figure, and explicit independent y-ranges in the origin figure. Sensor traces now use at most 1,500 positions per contiguous finite segment, preserve finite/time-gap breaks, and retain full-resolution timestamp-based label shading. This display decimation cannot establish high-frequency dynamics. The visibly different drawn pressure scale is disclosed; undocumented unit corrections were not applied.

The [five hypotheses](../ML_HYPOTHESES.md) and [split recommendation](../SPLIT_STRATEGY.md) were reviewed read-only. Their measured examples reconcile with the EDA tables: the event-1 WELL-00002 P-TPT median is approximately 17.09 MPa across 4,754 known-normal rows and 14.56 MPa across 9,617 known-abnormal rows; six real normal-to-transient boundaries are observed. These examples motivate tests, not established predictive benefit. Undefined per-well class metrics require explicit support handling. The split document now places uncertainty at the well-cluster level, preserving within-well episode dependence.

**Remaining limitations, not Phase 2 artifact defects:** size-biased selection; autocorrelated one-second observations; only 12 real published well IDs; event/origin/well confounding; unknown labels and censored onsets; constant/zero channels and suspicious cross-origin scale differences; unresolved physical-asset identity; and insufficient independent groups for class-supported validation and test. All acquired files and their real well IDs remain development-exposed. No split, fitted preprocessing, trained model, evaluation metric or generalization claim was produced. A separately approved later phase must resolve event scope, obtain adequate new groups if needed, freeze a protected test policy, and evaluate the stated hypotheses using training/validation data only.
