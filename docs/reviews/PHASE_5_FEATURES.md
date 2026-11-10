# Phase 5 independent feature review

Reviewer: `data_engineer`, 2026-11-10. Owned paths are this report and [tests/data/test_phase5_features.py](../../tests/data/test_phase5_features.py). This is a feature/provenance review, independent of model fitting and the separate evaluation-integrity review. No preprocessing, feature, split, raw-data or model implementation was changed.

The user authorized Phase 5 experimentation after Phase 4. The review reads [feature engineering](../FEATURE_ENGINEERING.md), [hypotheses](../ML_HYPOTHESES.md), [split strategy](../SPLIT_STRATEGY.md), [Phase 4 results](../../reports/baseline/README.md), the pipeline source, frozen state and **train/validation rows only**. No actual test feature values, targets or predictions were read. Whole-artifact hashes were verified without decoding test values. Existing published test-support counts are not a new protected-data claim.

## Findings and recommended scope

The frozen 120-column feature representation is usable for the authorized boosted-tree comparison, with substantial coverage and shortcut limitations. Retain it unchanged to compare against the established baselines. There is no feature-integrity blocker in this reviewed scope, but this conclusion does not establish model quality, causal explanations or monitoring reliability.

- The exact 27 upstream sensor names are the only source variables admitted by the pipeline. `class`, auxiliary `state`, source directory, instance/well/group identity, endpoint position and absolute timestamp remain in separate targets/metadata. The nine `ESTADO-*` columns are genuine upstream valve sensors, not the auxiliary `state` label.
- Six statistics per sensor are generated: observed-value mean, population standard deviation, minimum, maximum, first-to-last observed rate and least-squares trend against relative time. Only rows ending at the prediction endpoint enter each window. Missing values are neither backward-filled nor interpolated; source/time-gap boundaries reset the windows.
- The existing state retains 120 of 162 candidate features, representing 20 of 27 sensors. Forty-two train-allmissing columns were dropped from seven sensors: `P-JUS-BS`, `P-JUS-CKP`, `P-MON-CKGL`, `P-MON-SDV-P`, `PT-P`, `QBS`, `T-MON-CKP`. Holdout availability did not choose this schema.
- Median imputation and subsequent normalization were fitted on all 10,134 assigned training endpoints, including unknown-target endpoints, before the supervised model fits. Frozen scalar normalization preserves each feature's ordering; it does not remove well/source confounding or hide the imputed medians from a tree. CatBoost/XGBoost should consume these same numerical columns, without adding categorical IDs or treating target/status metadata as categorical inputs.
- Forty-five retained features are constant over all training windows: five each of mean/min/max, and ten each of std/rate/trend. A tree cannot learn a useful split on such a training-constant column, even when that column varies on holdout. They are not silently removed or selected using validation variation.

The state fingerprint is `5fd7c3a924b1ca7594e458dc88d8a4e575d647bcd9d65766d977ca674ebf4301`; the split fingerprint is `643ecb9867ceaf6daff093f11a2e1b0a2b3066cbe2ce614b4ad1ecf81ff82062`. The dataset remains 3W v2.0.0 at `914af287b1cf3e5207dce0da1e9dc08361c9adeb`, as recorded in the [preprocessing summary](../../reports/preprocessing_summary.json).

## Independently observed train/validation availability

This audit used Pandas Parquet filters for metadata partitions `train` and `validation`, then filtered features, targets and quality by those exact window IDs. The 27,717 decoded endpoints contain no test rows. Counts include both known and unknown endpoint targets; classification eligibility remains a separate mask.

| Diagnostic quantity | Train | Validation |
| --- | ---: | ---: |
| Windows | 10,134 | 17,583 |
| Published real well IDs / instances | 7 / 7 | 3 / 3 |
| Known-target windows | 7,649 | 16,518 |
| Observed retained sensors/window, minimum | 1 | 5 |
| Observed retained sensors/window, median | 11 | 18 |
| Observed retained sensors/window, maximum | 20 | 18 |
| Globally constant normalized columns | 45 | 10 |
| Nonfinite normalized values | 0 | 0 |

Per-sensor availability below counts windows with at least one actual observation of that sensor. The denominator is 10,134 train or 17,583 validation windows; an imputed feature is not counted as observed.

| Retained sensor | Train windows observed | Validation windows observed |
| --- | ---: | ---: |
| ABER-CKGL | 1,588 | 14,717 |
| ABER-CKP | 1,588 | 0 |
| ESTADO-DHSV | 3,740 | 16,861 |
| ESTADO-M1 | 3,740 | 16,861 |
| ESTADO-M2 | 3,740 | 16,861 |
| ESTADO-PXO | 3,740 | 16,861 |
| ESTADO-SDV-GL | 6,220 | 16,861 |
| ESTADO-SDV-P | 7,277 | 16,861 |
| ESTADO-W1 | 3,740 | 16,861 |
| ESTADO-W2 | 3,740 | 16,861 |
| ESTADO-XO | 3,740 | 16,861 |
| P-ANULAR | 6,234 | 17,583 |
| P-JUS-CKGL | 10,134 | 16,861 |
| P-MON-CKP | 8,001 | 16,861 |
| P-PDG | 5,871 | 17,583 |
| P-TPT | 6,943 | 17,583 |
| QGL | 5,871 | 16,861 |
| T-JUS-CKP | 6,234 | 2,144 |
| T-PDG | 6,220 | 17,583 |
| T-TPT | 7,292 | 17,583 |

`ABER-CKP` is retained from training but completely unavailable in validation. `T-JUS-CKP` is observed in only the 2,144 validation windows from WELL-00006. WELL-00008 contributes 2,133 training windows with just one observed retained sensor and 114/120 constant columns. WELL-00011 contributes 722 validation windows with five observed retained sensors and 90/120 constant columns. This is relevant to the baseline's observed 215 false positives on that validation well, but it does **not** establish that missingness caused those errors.

Availability profiles and imputed constants can identify acquisition regimes or wells even when explicit metadata is excluded. Valve-status summaries may correlate strongly with the annotated event definition. Source-specific operating levels, endpoint cadence, overlapping windows and original upstream interpolation remain additional limitations. The Phase 2 value-versus-availability, level-versus-change and sensor-ablation hypotheses are still untested controls; feature importance from a boosted tree would not replace those controls or establish physical causality.

## Calibration, second-stage classification and sequence models

**Multiclass assessment.** Training has normal plus families 3/4/5/7; validation has normal plus families 2/8. Each validation abnormal family has only one supporting source/well. A closed-set event classifier trained on this allocation cannot emit either validation event family. A second-stage multiclass head therefore has no supported family-generalization evaluation here. Do not reassign sources or combine test labels to manufacture support. Retain binary detection and explicitly report family-wise detection recall; a second-stage family model remains blocked by independent class/group support.

**Real versus synthetic.** The frozen manifest excludes seven simulated and two drawn sources from model data. The primary train/validation/test allocations are real-only. Synthetic evaluation or augmentation would require an explicitly frozen separate arm, using the same real holdout and frozen preprocessing, with unknown generator-family relationships disclosed. This review does not decode those excluded source records or report fabricated synthetic metrics. Unsupported origin slices should remain zero-support/null, not a synthetic-generalization claim.

**Calibration assessment.** Validation has only three published well IDs, with each abnormal family on one group. Splitting its windows randomly into calibration and selection folds would leak overlapping source history and inflate support. A same-validation calibration fit cannot supply independent evidence of improved calibration when assessed on the same labels. Training has three normal-only, two event-only and two mixed groups; grouped out-of-fold calibration is mechanically possible for binary support, but rigorous fold validation would require fold-fitted preprocessing. Reusing the frozen all-train preprocessing for held-out train groups would expose their feature statistics. Given the sparse, nonrepresentative support, retaining uncalibrated scores with honest calibration diagnostics/deferment is defensible. Any adopted calibration and thresholds must be frozen before test access.

**LSTM/1D-CNN assessment.** Phase 4 baselines are insufficient for a reliable monitoring claim, satisfying only the first condition in the user's sequence-model gate. The six summaries preserve some changes but compress temporal order: a synthetic test demonstrates two different trajectories with identical summary vectors. That mathematical compression does not show that the lost information improves actual detection. No controlled real-data experiment has yet established the benefit of raw sequence inputs, and only seven training groups cannot support a strong generalization claim. Boosted trees on the existing summaries are an appropriate bounded next comparison. Defer deep models; their empirical benefit and training/inference resource envelope have not been established.

## Verification and handoff

Executed on the existing Windows/Python 3.13.3 environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_phase5_features.py -q -p no:cacheprovider --tb=short
```

Actual result: **6 passed in 3.01 seconds**, zero failed/skipped. All fixtures are synthetic, not additional acquired telemetry or model results. Checks cover:

1. Future perturbations cannot change any earlier feature/count, including more than 512 endpoints and two lookbacks.
2. Summary compression can map different temporal trajectories to identical six-statistic vectors.
3. Changes to `class` and auxiliary `state` do not alter features/quality, while the genuine valve sensor remains available.
4. Finite imputed features and observations only in a train-dropped sensor do not supply retained-feature evidence; model eligibility remains false.
5. Training-constant columns remain retained with fixed unit scale even under large holdout changes; transform does not refit statistics.

Two independent inline Pandas/NumPy audits additionally produced the availability/constant/support counts above and verified all five frozen preprocessing artifact SHA-256 values against the completed summary. No test rows were decoded, no detector was fitted, and no source or frozen pipeline artifact was changed by this reviewer. Passing feature checks does not validate the concurrently implemented inference adapter or one-shot test gate; those require the ML owner's and QA reviewer's checks.

No shared contract change is proposed. The orchestrator retains model-selection protocol, phase records and integration. The ML owner must preserve exact feature order, frozen preprocessing, retained-evidence abstention and binary output semantics when saving/reloading the complete inference artifact. All later reporting must retain the development-exposure and source/group support limitations above.
