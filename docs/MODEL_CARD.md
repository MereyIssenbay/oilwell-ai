# OilWell AI model card

Status: **Phase 5 complete; selected diagnostic model rejected for monitoring.** The one-time test predicts abnormal for every normal window. No test-driven model or threshold change followed.

## Selected version and observed performance

- Model version: `oilwell-binary-phase5-c4e1835a82620306778a`; estimator: saved Phase 4 weighted Logistic Regression, with no coefficient refit.
- Threshold: **`1.1881945293311268e-14`**, positive when score is greater than or equal to it. Preserve full scientific notation. This extremely low threshold and the observed probability losses make probability interpretation unreliable.
- Bundle: `ml/artifacts/phase5/c4e1835a82620306778a/`, containing model, frozen preprocessing, split and manifest. Selection SHA-256: `dfbe88250db8808d58730ab6f0010da3c548cb4b1c26715ba4a4b78057e7130b`.

| Measure | Selected validation | Once-scored diagnostic test |
| --- | ---: | ---: |
| Eligible windows | 16,518 | 3,060 |
| Precision | 0.957408653 | 0.567320261 |
| Recall | 0.971344098 | 1.000000000 |
| F1 | 0.964326033 | 0.723936614 |
| AP | 0.935984905 | 0.452854833 |
| Trapezoidal PR-AUC | 0.935969617 | 0.451901434 |
| Normal alarm occupancy | 4.930106% | 100% |
| Confusion `[[TN,FP],[FN,TP]]` | `[[7344,380],[252,8542]]` | `[[0,1324],[0,1736]]` |

Test support is four sources/two published well IDs, with 1,420 additional unknown-target endpoints. All 1,324 normal test windows are false positives. Every test family (1/4/6) is detected only alongside an always-alarm policy. The zero confirmed new false-onset count reflects four censored initial episodes; all 13,251 normal seconds are alarmed. The validation occupancy constraint did not transfer. Test AP is below its positive prevalence of 0.567320261. See [full evaluation](../reports/final_evaluation.md) for exact metrics, denominators and failures.

## Intended task and interface

Detect binary normal versus documented undesirable-event endpoints in historical Petrobras 3W telemetry. The internal [inference interface](../ml/predict.py) returns a score, binary decision or explicit unavailable-evidence abstention, with a model version and score meaning. It does not identify which event family occurred, infer physical causes, prescribe interventions or control equipment. It is not a direct implementation of the canonical event-family API prediction.

The caller supplies one source instance at a time with the exact 27 sensor columns and an ordered unique timestamp index. Labels, source paths, identifiers and auxiliary `state` are excluded. The documented `ESTADO-*` valve channels are genuine sensors. A missing channel is represented by an all-null sensor column, not an invented reading. Insufficient history yields no complete window with an explicit insufficient-history indication; entirely unavailable retained-sensor evidence abstains. Original timezone semantics are preserved; no verified UTC claim is introduced.

## Data provenance and preprocessing

Dataset: Petrobras 3W v2.0.0, revision `914af287b1cf3e5207dce0da1e9dc08361c9adeb`, licensed CC BY 4.0. Attribution belongs to Petrobras and the 3W contributors; derived results imply no endorsement. The [acquisition manifest](../data/manifests/subset.json) fixes original source selection and checksums. This size-biased subset contains 23 instances, 14 real plus nine simulated/drawn. Model data uses the real-only frozen allocation; excluded synthetic instances are not converted into a new evaluation cohort.

Split fingerprint: `643ecb9867ceaf6daff093f11a2e1b0a2b3066cbe2ce614b4ad1ecf81ff82062`. Whole published real well IDs remain disjoint: seven train, three validation and two test groups. Published IDs rely on the author's identity convention and are not privately verified physical assets. All existing groups were inspected during EDA. The one-time test comparison is therefore a **development diagnostic**, not a pristine estimate of unseen-well generalization.

The frozen [Phase 3 pipeline](FEATURE_ENGINEERING.md) uses trailing 60-row windows at 1 Hz, stride 10, with gaps resetting history. Per-sensor mean, population standard deviation, min/max, elapsed rate of change and recent trend use observed values within the window only. No interpolation or backward fill occurs. Training medians and scaling are retained; 42 train-allmissing candidate columns were dropped, leaving 120 features. No Phase 5 preprocessing refit or feature selection occurs. Unknown labels remain unknown; documented transients map to their event family for binary supervision, retaining phase in evaluation only.

## Selection and probability semantics

The [prefit protocol](../reports/experiments/PROTOCOL.md) bounds the search to eight CatBoost/XGBoost configurations and saved Logistic Regression/Isolation Forest incumbents. Validation chooses thresholds to maximize recall under a 5% exact normal-time alarm-occupancy cap. Model ranking then uses recall, AP, lower occupancy and stable ID. This cap is an exploratory engineering choice, not an approved operational requirement. Validation is reused for selection; its reported winning metrics are optimistically selected.

Calibration is deferred because three validation groups and disjoint train/validation abnormal families cannot support a representative separate calibration evaluation. Probability outputs remain uncalibrated scores. Isolation Forest, if selected, emits an anomaly score rather than a probability. Brier/log loss are reported only for probability classifiers; no score is certainty.

## Known limitations and failure modes

- Train abnormal families 3/4/5/7 and validation families 2/8 do not overlap. Closed-set multiclass evaluation is unsupported, and binary detection cannot supply an event identity. A second-stage event classifier requires adequate independent group support.
- The independent [feature review](reviews/PHASE_5_FEATURES.md) found 45 of 120 retained columns constant in training. Train windows have one to 20 observed retained sensors; validation has five to 18. Finite imputed features do not establish strong evidence.
- Missingness, operating levels and valve channels may encode acquisition regimes or wells. ABER-CKP is retained from training but completely unavailable in validation. No controlled availability-only, level/change or sensor ablation has eliminated shortcut-learning concerns.
- Overlapping windows are correlated observations, not independent episodes. Small well/family counts do not justify window-based confidence intervals or production reliability claims.
- Unknown first-hour labels and censored episode starts complicate onset metrics. Zero confirmed false onsets can coexist with substantial normal time under alarm; occupancy must accompany onset rates.
- No synthetic-domain generalization is measured by the real-only holdouts. Generator-family relationships and broader-corpus near-duplicates remain unresolved.
- LSTM/1D-CNN were considered and deferred: baseline quality is insufficient, but benefit from additional sequence information and an acceptable resource envelope have not been demonstrated.

## Reproducibility and use boundary

Pinned dependencies are in [requirements-models.txt](../requirements-models.txt). The executed environment is Windows/Python 3.13.3; XGBoost 3.2.0 was chosen before fitting to retain declared Python 3.11 compatibility, but Python 3.11 itself was not executed. CPU fitting uses seed 42 and one thread. Model-only timing includes the score wrapper; full sensor-to-result timing is reported separately and excludes service/network/database behavior.

The local bundle contains the estimator, frozen preprocessing, split and manifest. Joblib is executable serialization; load only the locally generated trusted artifact after its recorded hashes match. The bundle binds inference code, dependencies, feature order, target policy and threshold. Raw telemetry, model binaries and full per-window predictions remain ignored by Git. Reproduction uses pinned inputs and saved fit checkpoints; an existing test access journal prevents repeated test inference. Final scores, provenance and the completed one-attempt test-access history are linked in the [evaluation report](../reports/final_evaluation.md). All 309 tests passed; same-batch validation reload is exact, and raw-sensor decisions match all validation endpoints with score tolerance 1e-14. Test was not re-inferred for verification.

Further deployment, API integration, calibration, data acquisition or result-driven model changes require a separately approved phase. Model selection alone does not establish operational readiness.

Selected LR latency: feature-to-score wrapper p50/p95 3.588300/4.230460 ms; raw 60-row window through inference 6.993650/8.761235 ms. These exclude disk/model loading and are local validation measurements. CatBoost prediction latency has a recorded protocol deviation: native `thread_count=-1` was not explicitly overridden, so its timing is not a strict single-thread comparison. Training used one thread and latency did not affect selection. No frozen code/artifact was changed after this late finding.
