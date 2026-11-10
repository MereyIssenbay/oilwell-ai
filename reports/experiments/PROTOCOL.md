# Phase 5 fixed experimentation protocol

Frozen before candidate fits, 2026-11-10. The user authorized model selection and one selected-model test evaluation. Root owns this protocol; implementation must record its SHA-256. Any pre-test implementation correction is recorded; results must never be used to expand this search. After the test journal starts, no tuning, selection changes or second test inference is permitted.

## Scope and unchanged inputs

Use dataset 3W v2.0.0 at `914af287b1cf3e5207dce0da1e9dc08361c9adeb`, the existing acquired subset, and frozen Phase 3 preprocessing/split. Split fingerprint: `643ecb9867ceaf6daff093f11a2e1b0a2b3066cbe2ce614b4ad1ecf81ff82062`. Preserve original bytes, source identities, 60-row causal windows, stride 10, 120 retained features, median/scaling statistics and endpoint/transient policy. No new telemetry, feature selection or preprocessing refit.

The task remains binary normal versus documented undesirable event. Known endpoints with at least one observed retained sensor value are eligible. Unknown labels are excluded from classification metrics but available predictions preserve alarm continuity. No class/state, source IDs, paths, times or quality counters enter estimator inputs. Original `ESTADO-*` sensors remain legitimate allowlisted measurements.

All candidates use the same train and validation groups/rows. Test arrays, outcomes and predictions remain inaccessible until selection is locked and root releases the gate. Hashing original/processed files for integrity is allowed. Current groups were exposed during EDA; even the once-scored test is a development diagnostic and cannot satisfy the protected-cohort requirement in [SPLIT_STRATEGY.md](../../docs/SPLIT_STRATEGY.md).

## Bounded search

Exactly eight boosted classifiers: each of XGBoost and CatBoost uses depth in `{3,6}` crossed with learning rate in `{0.05,0.1}`, 200 trees/iterations, positive class weight 2, seed 42 and one CPU thread. XGBoost uses binary logistic objective and histogram trees on CPU; CatBoost uses binary Logloss on CPU with auxiliary file writing disabled. Other installed-version defaults are recorded in model metadata. No early stopping, adaptive extension, GPU, randomized search, window search or additional seeds. Dependency versions are pinned in [requirements-models.txt](../../requirements-models.txt).

Reuse the saved Phase 4 Logistic Regression and Isolation Forest estimators as two additional threshold-selection candidates; do not refit them. Preserve all four original baseline operating points as comparison-only rows. Their original metrics must match [Phase 4](../baseline/README.md). Isolation Forest's normal-only statement applies to its estimator, not the shared all-training-endpoint preprocessing. No candidate is presumed superior.

## Validation threshold and model selection

For each of ten learned candidates, generate at most 201 equally spaced quantiles of finite scores at available validation endpoints, deduplicate them, and add finite thresholds immediately below the minimum and above the maximum. Thus at most 203 thresholds per candidate. Quantiles use validation scores without test access. Positive decisions use `score >= threshold`; the untouched original Isolation Forest reference retains its original strict comparison.

Choose the threshold with maximum eligible-window abnormal recall subject to **normal-time alarm occupancy <= 0.05**. Break ties by lower normal occupancy, then higher threshold. Occupancy uses exact normal raw seconds under bounded held predictions, not normal window fraction. Precomputed per-endpoint normal exposure weights may accelerate this calculation, but independent QA must reconcile them against the existing temporal evaluator. An all-normal threshold provides a feasible fallback; absence of normal exposure makes constraint evaluation unsupported and must fail explicitly.

Select among the ten candidates by descending recall, then descending average precision (AP), then ascending normal occupancy, then lexicographic stable candidate ID. This explicitly favors recall while controlling false-alarm exposure and using PR ranking quality as a secondary criterion. The 5% cap is a declared **diagnostic engineering choice**, not a user-specified operational acceptance budget. Do not present selection under this cap as production reliability. Publish every candidate and threshold considered, including failures; do not silently drop failed fits.

Validation now participates in hyperparameter/threshold/model selection, so its winning metrics are optimistically selected diagnostics. The small number of independent groups precludes reliable uncertainty estimates from windows. No refit on train+validation after selection: the selected estimator and frozen preprocessing remain the ones compared.

## Calibration, domains and second stage

Calibration is assessed and **deferred**: only three validation well IDs, with one source for each of two abnormal families and neither family in training, do not support a separate representative calibration/selection split. Random window folds would leak episode structure. No claim of calibrated probabilities is permitted. Report Brier score/log loss for actual probability classifiers as descriptive diagnostics; Isolation Forest anomaly scores are not probabilities and those metrics remain null. No calibration fit on test or opportunistic use of test reliability plots to change the model.

Primary validation/test contain only real sources. Report zero-support simulated/drawn slices as null/unsupported; no real-versus-synthetic generalization is measured by this experiment. Do not put excluded synthetic instances into a new holdout or fit an augmentation arm inside this budget.

Assess multiclass event classification from already known training/validation support. Train abnormal families 3/4/5/7 and validation 2/8 are disjoint, so a supported closed-set second-stage evaluation is infeasible. Do not invent multiclass scores or label binary abnormal output with an event identity.

LSTM/1D-CNN are deferred: Phase 4 quality is insufficient, but controlled evidence for additional sequence benefit is absent and independent group support is inadequate. Existing trailing statistics already capture limited temporal information. No deep-learning dependency or training is authorized by this fixed experiment budget.

## Evaluation and latency

Report precision, recall, F1, AP and separately named trapezoidal PR-AUC, confusion counts, family/phase/source/well support, unknown/unavailable counts, normal-time occupancy, false-positive window fraction and confirmed false onsets per normal and covered replay hour. Retain the Phase 4 label-independent episode continuity/censoring policy. Zero confirmed onsets can coexist with a permanently active alarm; occupancy is mandatory. Selected-model test receives the same measures, with explicit `test` provenance.

Benchmark inference on validation inputs only: five warmups and 50 timed single-feature-row calls, plus ten timed batches of up to 1,024 rows after warmup; report p50/p95, batch size and throughput. Use a monotonic high-resolution timer and single-thread configuration; record environment/hardware. Benchmark the selected raw-sensor-to-result path separately on a validation source, including feature creation and frozen preprocessing. Distinguish model-only versus full-pipeline timing, and exclude disk/model load unless explicitly stated. Timing is monitored, not a noisy tie-break or an operational latency claim. Do not repeat test prediction for timing.

## Bundle, review and one-shot test

Save complete frozen preprocessing, exact feature names/order, selected estimator, score meaning, threshold policy, label policy, source/split/input hashes, dependencies, seeds, base revision and current code hashes. A stable model version identifies the locked configuration/content. The inference interface must accept sensor-only per-instance input, preserve boundaries/time semantics, reject unsupported features and abstain for insufficient history/unavailable evidence. It returns an internal binary result, not the canonical event-family API prediction; the API contract remains unchanged.

Before test access: meaningful synthetic-fixture tests pass; independent feature/evaluation reviews complete; root verifies validation selection and artifact hashes. Freeze an immutable selection manifest binding protocol, code, dataset/split/preprocessor, model, threshold, feature and dependency hashes. Persist an exclusive STARTED journal **before reading any test rows**. Refuse an existing STARTED, failed or completed journal, including partial failures; do not silently retry. Hash/precondition errors before test reads may be fixed and rechecked without accessing test. A root-authorized command runs only the selected saved bundle on test once, saves predictions and metrics, then marks completion. Audit saved outputs without additional estimator calls on test.

After test results, no result-driven edits to estimator, threshold, feature policy or selection are allowed. Report poor outcomes plainly. Persist failure state if publication is interrupted; a resumable report-only operation may read saved predictions but cannot re-infer test. Reproducibility checks on train/validation and artifact reload occur before test; later users are instructed to inspect the saved test report rather than rerun its scoring command.

## Official API references

- [XGBoost Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html): CPU/thread and classifier interfaces.
- [CatBoostClassifier](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier) and [prediction probabilities](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_predict_proba): training configuration and feature-order requirements.

The current software versions and actual executed parameters, rather than assumptions about historical APIs, govern the saved artifacts. No causal explanation or production reliability follows from these benchmark results.
