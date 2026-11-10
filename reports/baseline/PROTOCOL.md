# Phase 4 baseline experiment protocol

Declared by the orchestrator on 2026-11-10 **before fitting or inspecting baseline validation predictions**. This protocol is fixed for the first baseline comparison. Any later revision must state its reason and whether results had already been seen; do not silently tune or replace the original experiment. No additional telemetry is acquired.

## Question and limits

Evaluate a diagnostic binary detector of normal (`0`) versus any documented undesirable family (`1..9`), including the explicit transient mappings in Phase 3. Unknown endpoint targets remain unknown and are excluded from supervised metrics. The output does not identify an event family and does not claim reliable detection of every unseen event.

The frozen development split is `643ecb9867ceaf6daff093f11a2e1b0a2b3066cbe2ce614b4ad1ecf81ff82062`, in [development_split.json](../../data/manifests/development_split.json). Preprocessing uses 60-row causal windows, stride 10, one-second cadence, seed 42 and 120 frozen retained features. No regrouping, new split search, feature selection or preprocessing refit is allowed in this comparison.

Known training event families are 3, 4, 5 and 7; validation events are 2 and 8, both absent as families from training. This makes a closed-set multiclass comparison unsupported. The binary comparison measures a limited cross-family development diagnostic. All selected published real well IDs were exposed during EDA; none is a pristine final evaluation group. Training authorization does not remove that limitation.

Only `train` windows fit estimators. Only `validation` windows receive predictions and reported metrics. No `test` window may enter estimator fitting, prediction, threshold selection, hyperparameter selection or metric calculation. Integrity checks may hash a complete existing processed artifact containing test rows; that is not model access to those rows. The training API must drop test rows at the dataset boundary.

## Common inputs and eligibility

Reuse the Phase 3 preprocessing JSON and aligned feature, target, metadata and quality Parquets. Verify them against the preprocessing summary and frozen split. Preserve exact feature order; never concatenate labels, identifiers, source origin or timestamps into the predictor matrix. Saved preprocessing statistics were fitted on training windows only, including unknown-target training windows; Phase 4 does not learn them again.

An input-evidence flag requires at least one observed value from a sensor represented in the retained feature schema. Supervised eligibility additionally requires a known mapped endpoint target. Apply exactly the same validation eligibility mask to every model. Score validation windows with sufficient input even when their target is unknown, so alert continuity does not depend on unavailable ground truth. Report all exclusions, unknown endpoints and evidence coverage. This minimal evidence rule is an explicit baseline rule, not a validated operational abstention policy.

The primary cohort is real-only. Simulated and drawn files remain excluded by the frozen split. Source-specific output must list all three origins; absent origins have zero evaluated support, null metrics and an explicit not-evaluated reason. No fictitious synthetic performance is reported.

## Models and fixed operating points

| Model | Fit data and parameters | Positive score / decision |
| --- | --- | --- |
| Always normal | No fitted parameters; negative reference | Constant score 0, predict normal |
| Training majority | Majority of eligible binary training targets; ties resolve to normal | Constant chosen label as score and prediction; label selection never uses validation |
| Logistic Regression | Eligible labeled train windows; L2 (`l1_ratio=0.0`), `C=1.0`, `solver=liblinear`, `class_weight={0: 1, 1: 2}`, `max_iter=2000`, `tol=1e-4`, `random_state=42`; intercept enabled with default scaling | Positive-class probability score, abnormal when score >= 0.5; probabilities are uncalibrated |
| Isolation Forest | Eligible **known-normal train windows only**; `n_estimators=200`, `max_samples=256`, `contamination=0.05`, `max_features=1.0`, `bootstrap=False`, `random_state=42`, `n_jobs=1` | `-score_samples`, abnormal when score > `-offset_`; threshold comes from training, not validation |

The positive Logistic Regression weight expresses the requested preference for event recall; it is a declared cost choice, not a tuned optimum. Isolation Forest's 5% contamination is a training operating-point parameter, not an estimated event prevalence or a guarantee of deployment false-alarm rate. Its fit uses normal labels to define the reference distribution, so describe it as a normal-trained novelty/anomaly baseline rather than a completely label-free experiment.

There is no hyperparameter sweep, threshold tuning, calibration or test scoring. Use one execution thread where supported and record actual solver convergence. A convergence failure must be reported; do not silently treat a partial fit as success. Model persistence and reload must reproduce validation scores and decisions.

Official API references: [Logistic Regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html) documents class weighting and L2 configuration; [Isolation Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html) documents the training-derived `offset_` and score orientation.

## Classification metrics

Report abnormal as the positive class. Save integer TP, FP, TN and FN alongside precision, recall and F1; the confusion matrix has true `[normal, abnormal]` rows and predicted `[normal, abnormal]` columns. Undefined precision with no positive predictions is null with a reason. Recall is null if there are no positives; absent-class metrics must not become fabricated zeros. F1 is `2TP / (2TP + FP + FN)` when its denominator is nonzero.

Report both **average precision (AP)** and **trapezoidal area under the precision-recall curve**, using the continuous positive scores rather than binary decisions. They are different statistics; retain explicit names in tables/JSON. Constant scores have no ranking information even when AP equals the positive prevalence. [Scikit-learn's AP definition](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html) distinguishes it from trapezoidal interpolation, which may be optimistic.

Use pooled window metrics for the primary model comparison, then show per-source, per-well and per-phase support and performance to expose domination by a long instance. For each undesirable family, report validation windows, contributing instances/wells, detection recall, and whether training contained that family. These are binary detection slices, not event-family classification scores. Families absent from validation are not estimable. In particular, family 2 is the minority validation event and must remain visible beside family 8.

Window counts are serially dependent; overlapping windows do not establish independent replication. Do not invent confidence intervals from their nominal sample size. No operational false-alarm budget or statistical acceptance target was supplied; report observations and limitations instead of declaring a post-hoc passing threshold.

## False-alarm and historical-time accounting

This is an offline sampled-decision reconstruction, not a running backend replay service. Define one predicted alert episode from contiguous positive decisions for one source instance. Continuity uses **predictions, input availability and timestamp cadence only**. Unknown target labels do not reset an episode. A source boundary, timestamp gap or unavailable-input interval censors continuity; a positive decision at the beginning of such coverage is left-censored rather than an observed new onset.

Count an observed false-alert onset only for a contiguous negative-to-positive transition whose endpoint raw label is normal. Positive episode starts with unknown labels are tracked separately. An episode originating during abnormal operation can overlap later normal time; do not invent a new onset at a target transition.

Hold each available decision over `[endpoint, min(endpoint + stride duration, next decision, source end))`, treating source end as its last observation plus one cadence interval. Never carry a decision through a gap. Use the original, checksum-verified validation label rows to measure exact covered normal seconds, covered total seconds and normal seconds with an active positive decision. Labels classify exposure only; they never define model inputs or reset the prediction state.

Report observed false-alert onsets per covered normal hour and per covered replay hour, with counts and denominators. Also report **normal-time alarm occupancy**, false-positive decision fraction and censored/unknown-onset episode counts. An always-positive baseline can have zero observed new false onsets while alarming throughout normal time; the occupancy measure prevents interpreting that artifact as good behavior. Zero covered time yields null rates. These rates apply only to the declared sampled reconstruction, not an implemented dwell/recovery alert policy or an operational deployment.

## Artifacts, reproducibility and disposition

Save full validation predictions and fitted model binaries under ignored `ml/runs/baseline/` and `ml/artifacts/baseline/`. Version compact metrics, comparison/support/failure tables, PR curves, confusion figures and an experiment manifest under `reports/baseline/`. Record code revision plus actual code hashes, package versions, all parameters/seeds, source/split/preprocessing fingerprints, protocol hash, exact fit/evaluation row IDs or their digests, artifact checksums and estimator convergence.

Repeat the same fixed run to verify predictions and metrics; do not use repetition to select a favorable result. Independently check metric arithmetic, temporal accounting, exclusion of test rows, model reload and minority failures. Failure examples must reference observed predictions and source coordinates without inventing physical causes.

The engineering baseline is complete only when reproducible runs and independent checks pass. Promotion as a reliable event detector additionally requires adequate independent class/group support, a protected evaluation cohort and an agreed recall/false-alarm criterion. Those requirements are currently unresolved. Phase 4 must state whether its measured operating behavior warrants further development, and must stop without starting the next phase.
