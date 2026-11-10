# Phase 5 final diagnostic evaluation

**Model selection and its one-shot test evaluation are complete. The selected model failed to transfer its validation false-alarm constraint to test and is not accepted for monitoring.** No model or threshold was changed after test results.

Selected version: `oilwell-binary-phase5-c4e1835a82620306778a`. Candidate: `logistic_regression_retuned`. Frozen threshold: **`1.1881945293311268e-14`**, applied with `score >= threshold`. Preserve the scientific notation; rounding this value to zero changes the policy.

## Comparison on identical validation data

All candidates use 16,518 eligible real validation windows (7,724 normal, 8,794 abnormal), from three sources/published well IDs. All 17,583 available endpoints are predicted; 1,065 unknown endpoints are excluded from classification metrics and retained for alert continuity. Validation selection results are optimistically selected, not independent evaluation.

| Candidate | Precision | Recall | F1 | AP | Trapezoidal PR-AUC | Normal alarm occupancy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| always_normal | undefined | 0.000000000 | 0.000000000 | 0.532388909 | 0.766194455 | 0.000000% |
| isolation_forest | 0.535729516 | 1.000000000 | 0.697687334 | 0.735504085 | 0.735485774 | 98.666839% |
| logistic_regression | 0.956609485 | 0.539003866 | 0.689504691 | 0.935984905 | 0.935969617 | 2.794460% |
| train_majority | 0.532388909 | 1.000000000 | 0.694848293 | 0.532388909 | 0.766194455 | 100.000000% |
| catboost_d3_lr0.05 | 1.000000000 | 0.090971117 | 0.166770898 | 0.517413918 | 0.507458427 | 0.000000% |
| catboost_d3_lr0.1 | 1.000000000 | 0.023197635 | 0.045343410 | 0.447748581 | 0.434672615 | 0.000000% |
| catboost_d6_lr0.05 | 0.898345154 | 0.216056402 | 0.348336236 | 0.687715990 | 0.676855585 | 2.794460% |
| catboost_d6_lr0.1 | 0.804010939 | 0.100295656 | 0.178343949 | 0.652646629 | 0.643077007 | 2.794460% |
| xgboost_d3_lr0.05 | 1.000000000 | 0.150216056 | 0.261196243 | 0.668165937 | 0.661225279 | 0.000000% |
| xgboost_d3_lr0.1 | 0.857142857 | 0.093472822 | 0.168563519 | 0.645853773 | 0.645482558 | 1.773233% |
| xgboost_d6_lr0.05 | 0.481572482 | 0.022287924 | 0.042604065 | 0.515781684 | 0.510420601 | 2.742687% |
| xgboost_d6_lr0.1 | 0.656400385 | 0.077552877 | 0.138716567 | 0.535712631 | 0.534800958 | 4.632410% |
| logistic_regression_retuned | 0.957408653 | 0.971344098 | 0.964326033 | 0.935984905 | 0.935969617 | 4.930106% |
| isolation_forest_retuned | 0.873136915 | 0.286445304 | 0.431372549 | 0.735504085 | 0.735485774 | 4.737251% |

Exact values, confusion counts and timing columns: [model_comparison.csv](model_comparison.csv). Full source/family/phase/well measures: [validation_metrics.json](experiments/validation_metrics.json). AP is non-interpolated average precision; trapezoidal PR-AUC is separately named and can differ substantially for tied scores.

## Selection rule and search evidence

The [prefit protocol](experiments/PROTOCOL.md) fixed eight boosted fits: CatBoost and XGBoost, each with depths 3/6 and learning rates 0.05/0.1, 200 trees, positive class weight 2, seed 42 and one CPU training thread. Saved Phase 4 LR/IF estimators supplied two additional threshold-selection candidates; no incumbent was refitted. Four original fixed baseline operating points are comparison references. Exactly eight boosted fit checkpoints exist; no early stopping, extra seeds or adaptive expansion occurred.

The ten candidates produced 1,481 deduplicated threshold candidates under the bounded quantile rule. Per-candidate thresholds maximize recall subject to exact normal-time alarm occupancy <=5%; ties prefer lower occupancy and higher threshold. Global ranking prefers recall, then AP, lower occupancy and stable candidate ID. The 5% cap is a diagnostic engineering choice, not an operational requirement. Latency is monitored and does not affect ranking. Full [search metadata](experiments/search.json), [threshold grid](experiments/threshold_search.csv) and [normal exposure weights](experiments/normal_exposure_weights.csv) remain auditable.

Logistic Regression was selected without coefficient refitting: changing its threshold raised validation recall from 0.539003866 to 0.971344098 while raising normal alarm occupancy from 2.794460% to 4.930106%. Ranking AP remained 0.935984905. Best boosted recall was CatBoost depth 6 / rate 0.05 at 0.216056402; best XGBoost recall was depth 3 / rate 0.05 at 0.150216056. Neither boosted family outperformed the selected incumbent under this protocol.

## Frozen selected model: validation and once-scored test

Confusions use true rows and predicted columns ordered normal/abnormal: `[[TN,FP],[FN,TP]]`.

| Partition | Eligible windows | Precision | Recall | F1 | AP | Trapezoidal PR-AUC | Confusion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| validation | 16518 | 0.957408653 | 0.971344098 | 0.964326033 | 0.935984905 | 0.935969617 | `[[7344, 380], [252, 8542]]` |
| test | 3060 | 0.567320261 | 1.000000000 | 0.723936614 | 0.452854833 | 0.451901434 | `[[0, 1324], [0, 1736]]` |

Test contains 4,480 predicted endpoints, 3,060 eligible (1,324 normal, 1,736 abnormal) and 1,420 unknown targets, across four sources and two published well IDs. These groups were EDA-exposed; the frozen test is a development diagnostic. No other candidate was scored on test. The [root release](experiments/TEST_RELEASE.json) binds the independently reviewed [selection](experiments/selection.json); the [test access journal](experiments/test_access.json) records COMPLETE with exactly one attempt and output hashes. Full results: [test_metrics.json](experiments/test_metrics.json).

| Partition | Covered replay hours | Normal hours | Normal alarm seconds | Normal occupancy | Confirmed false onsets | Per replay hour | Per normal hour | Censored positive starts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| validation | 48.838333333 | 21.461111111 | 3809 | 4.930106% | 40 | 0.819028768 | 1.863836397 | 1 |
| test | 12.438055556 | 3.680833333 | 13251 | 100.000000% | 0 | 0.000000000 | 0.000000000 | 4 |

**Every eligible normal test window is a false positive.** The test policy is effectively always-alarm, including all unknown endpoints. Its zero confirmed false onsets reflect four censored initial positive episodes, not absence of false alarms. All 13,251 normal source seconds are alarmed. The validation 5% exposure constraint does not transfer to test. Test AP 0.452854833 is below the test positive prevalence 0.567320261, further showing weak ranking in this small different-family mixture. No operational replay service was executed.

## Family, well and source failures

Validation LR detects 145/152 family-2 windows and 8,397/8,642 family-8 windows, missing 7 and 245 respectively. Both families were absent from training. All 215 normal WELL-00011 windows remain false positives; another 165 occur on WELL-00006. Pooled normal exposure hides this complete normal-window failure on one validation well.

Test detects 962/962 family-1, 706/706 family-4 and 68/68 family-6 windows. Families 1/6 were unseen in training. This perfect detection recall is obtained alongside 1,324/1,324 normal false positives: WELL-00002 contributes 1,192 and WELL-00004 contributes 132. Only one well supports each test family; family 1 and 4 share a well. These are binary family slices, not correct predicted event identities. [Validation failure examples](experiments/validation_failure_cases.csv) and [test failure examples](experiments/test_failure_cases.csv) retain actual source coordinates and scores without causal explanations.

All evaluated sources are real. Simulated and drawn sources have zero holdout support and null metrics. No synthetic generalization or augmentation effect was measured. Train abnormal families 3/4/5/7 versus validation 2/8 make a supported closed-set second stage infeasible; multiclass fitting was not performed. LSTM/1D-CNN were considered and deferred because sequence benefit and an adequate independent cohort are unproven.

## Calibration and latency

Calibration was assessed and deferred before test: three validation groups are insufficient for representative independent calibration and selection, and random window folds would leak overlap. Scores remain uncalibrated. The extremely small selected LR threshold must not be interpreted as a calibrated event probability. Validation Brier/log loss are 0.25601139052179556 / 4.718590378541996; test values are 0.3565320010584989 / 1.5756388199775637. No test calibration or threshold adjustment followed these observations.

Selected LR timing on validation: feature-to-score wrapper p50 **3.588300 ms**, p95 **4.230460 ms** for one row; batch 1,024 p50 **3.823200 ms**, p95 **4.346775 ms**, approximately **267,838 rows/s** at the batch median. The wrapper includes feature validation and threadpool context; it excludes preprocessing/model/disk loading. Raw 60-row sensor window through features/imputation/scaling/decision: p50 **6.993650 ms**, p95 **8.761235 ms**. Five warmups precede 50 single/window repetitions or ten batch repetitions. These are local benchmarks, not service latency guarantees.

Environment: Windows AMD64, Python 3.13.3, Intel64 Family 6 Model 154 Stepping 3 (GenuineIntel), 12 logical CPUs; selected LR inference and all estimator fitting were constrained to one thread. XGBoost 3.2.0, CatBoost 1.2.10 and all dependency versions are pinned and recorded.

**Latency protocol deviation:** CatBoost prediction calls retained their native `thread_count=-1` default, so their recorded inference timings cannot be described as strictly single-thread despite single-thread training and the surrounding threadpool context. This was identified after test access began; code and outputs were preserved and no timing/test rerun occurred. Timing did not select the model; selected LR timing is unaffected. CatBoost latency comparisons have this thread-control limitation.

## Verification, artifacts and handoff

- **309 tests passed in 12.31 seconds**, zero failed/skipped: 214 prior tests plus six independent feature, ten implementation and 79 independent Phase 5 evaluation/inference cases. Root command: `.venv/Scripts/python.exe -m pytest tests/data tests/qa tests/ml tests/test_data_pipeline.py tests/test_training.py -q -p no:cacheprovider --basetemp <unique-workspace-temp-path> --tb=short`.
- Independent pre-test QA reconciled all 175,830 validation prediction rows, 17,583 raw-derived normal weights, 1,481 threshold candidates, ties/selection, metrics, temporal accounting and immutable hashes before release.
- All ten saved candidates reproduce same-batch validation scores and decisions exactly. Root raw-sensor inference across all three validation instances reproduces all 17,583 decisions/timestamps; floating score differences are <=3.1086244689504383e-15, within absolute tolerance 1e-14 (relative tolerance zero).
- The original Phase 4 LR scores and new wrapper differed on nine rows by at most 3.1225e-17. A documented numerical compatibility check was corrected before selection; all eight fits were reused from checkpoints, original references stayed unchanged and no search budget/parameters changed.
- Complete bundle: `ml/artifacts/phase5/c4e1835a82620306778a/` contains `model.joblib`, `preprocessor.json`, `split.json`, `manifest.json`. Full predictions/checkpoints remain ignored. [Validation reproduction evidence](experiments/verification.json) and [root integration evidence](model_selection_verification.json) record checks separately from benchmark quality.
- [Independent feature review](../docs/reviews/PHASE_5_FEATURES.md), [evaluation review](../docs/reviews/PHASE_5.md), [model card](../docs/MODEL_CARD.md) and [progress](../docs/PROGRESS.md) document remaining limits and the phase stop.

Load the trusted local bundle with `ml.predict.load_bundle(Path("ml/artifacts/phase5/c4e1835a82620306778a"))`, then call `predict_instance(sensor_only_frame)` for one ordered source. Required inputs and abstention semantics are in the model card. The model is internal binary inference and cannot populate an event-family prediction without a separately approved contract/model scope decision.

The pre-test search command was `.venv/Scripts/python.exe -m ml.training.phase5 search`; it now refuses because the test journal exists. Root ran `.venv/Scripts/python.exe -m ml.training.phase5 test-once` exactly once after release. Do not delete/reset the journal to rerun scoring. Review saved outcomes; a new evaluation claim requires a new approved protocol/cohort. Independent audits may inspect saved test predictions without calling the estimator again.

**Decision:** retain this reproducible selected artifact as a failed diagnostic experiment; do not promote it to monitoring. Further work should establish fresh real groups with adequate event support, investigate availability/regime shortcuts and agree on alert criteria before another selection/calibration experiment. Stop after Phase 5. No additional data acquisition, application integration or deployment was performed.

Attribution: Petrobras and the 3W contributors, 3W v2.0.0, pinned acquisition revision, CC BY 4.0. Benchmark results imply neither endorsement nor production reliability.
