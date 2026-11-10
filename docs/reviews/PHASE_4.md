# Independent Phase 4 baseline experiment review

Review date: 2026-11-10. **Complete: no unresolved blocking software finding; detector acceptance withheld.** This review covers diagnostic binary baselines on the frozen Phase 3 development split. It does not establish a protected final-test result or validate a multiclass event detector.

## Scope and ownership

The reviewer owns this report and `tests/qa/test_baseline_integrity.py` only. The ML engineer owns baseline training/evaluation code, implementation tests and experiment artifacts. The orchestrator owns the protocol, dependencies and shared project records. Findings are sent to the responsible owner; no implementation or shared-document files are edited by this reviewer.

The approved comparison uses always-normal and train-majority references, Logistic Regression and Isolation Forest. Hyperparameters and operating thresholds are fixed before validation results. No test rows may enter fitting, prediction, metrics or tuning. Validation abnormal families 2 and 8 are absent from the training abnormal families 3, 4, 5 and 7; results therefore describe a limited binary transfer diagnostic and cannot establish supported family classification or general unknown-event detection.

## Independently verified input boundary

The reviewer checked SHA-256 of all five Phase 3 processed/state artifacts against `reports/preprocessing_summary.json`, then selected train/validation metadata before inspecting their labels and quality. No test predictions or test metrics were calculated.

| Partition | All endpoints | Eligible known-label endpoints | Normal | Abnormal | Unknown labels | No retained-sensor evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | 10,134 | 7,649 | 3,541 | 4,108 | 2,485 | 0 |
| Validation | 17,583 | 16,518 | 7,724 | 8,794 | 1,065 | 0 |

Eligibility in this independent check requires a known endpoint family and at least one observed retained sensor value. The seven training published well IDs and three validation IDs are disjoint. The frozen preprocessor SHA-256 is `9c42996b13b84c010e6c9ebb8d25a8e0b83330f899f8a3ad70c9401ba2e74dcd`; its statistics remain train-only. All validation families, source types, unknown labels and quality exclusions must be reported without changing the split.

## Independent automated verification

Executed after the owner corrected the findings below:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/qa/test_baseline_integrity.py -q -p no:cacheprovider --tb=short
```

**Actual result: 46 passed in 3.36 seconds, zero failures or skips.** These are synthetic software fixtures, not dataset performance metrics. The suite executes real small Logistic Regression/Isolation Forest fits where necessary, with the fixed seed and parameters. A deliberately poisoned test partition contains infinite features, invalid labels and negative quality counts; it is discarded before numeric validation, and the selected training/validation data plus resulting validation predictions remain exactly identical. No actual dataset test prediction is produced by this check.

| Invariant | Independently executed evidence |
| --- | --- |
| Metric arithmetic | Hand-calculated confusion counts, precision/recall/F1, AP `5/6` and distinct trapezoidal area `19/24`; tied-score AP equals prevalence; undefined ratios remain null |
| Denominator honesty | Empty/single-class slices have unsupported ranking metrics; absent source types/families retain zero support and explicit not-evaluated status |
| Temporal alarm accounting | Unknown labels and event recovery do not reset alert episodes; file/gap/abstention starts are censored; partial final intervals and next-decision clipping prevent excess time |
| Always-positive interpretation | It can have zero confirmed false onsets but 100% normal alarm occupancy, which is explicitly exposed |
| Shared evaluation cohort | Models must share every endpoint and context, including unknown-label windows, not only the eligible subset |
| Estimator boundary | Fit rejects validation; prediction rejects test; labels/state/source metadata cannot enter feature columns |
| Isolation Forest reference | A wrapper around the actual estimator fit observes exactly the independently selected eligible raw-normal training row IDs |
| Targets and evidence | Raw label/family/phase consistency and actual retained-sensor counts govern eligibility; fabricated masks or mappings are rejected |
| Availability and label independence | An all-unavailable validation batch produces abstentions without calling estimators; unknown targets still receive available predictions; changing valid target/status values does not change scores |
| Operating point | Logistic Regression uses inclusive `>= 0.5`; Isolation Forest uses strict `> -offset_`; threshold ties are exercised explicitly |

The initial evaluator test run produced 22 passes and eight failures, making the chronology/contract defects reproducible. All were corrected by the ML owner. A later test-row poisoning fixture initially changed a whole Boolean column's dtype while assigning invalid values; the reviewer corrected the fixture to preserve column types, so the final test isolates row values rather than a global schema change.

## Resolved findings

- **High, resolved: inconsistent targets or eligibility could alter metric denominators.** Initial prediction checks permitted `event_family`/phase inconsistent with `raw_class`, silently excluded known available rows, and checked only shared eligible IDs across models. [Evaluation validation](../../ml/evaluate.py) now enforces documented mapping, strict Boolean masks, exact eligibility and identical full endpoint context. Training checks also reject forged mapping/evidence before fitting.
- **Medium, resolved: held-decision exposure could overlap.** `false_alert_metrics` initially held every decision for its full stride even when a next decision arrived earlier. It now caps exposure at that next endpoint; the independent 15-second fixture no longer reports 20 seconds.
- **Medium, resolved: a raw gap could escape episode censoring.** Equal prediction-endpoint spacing alone did not prove continuous raw observations. A gap inside the preceding interval now censors the positive start; it is not counted as a confirmed false onset.
- **Medium, resolved: all-unavailable input could reach an estimator.** [Prediction generation](../../ml/train_baseline.py) now returns unavailable rows as explicit abstentions without invoking sklearn on an empty feature array.

The normal-only statement applies to the **Isolation Forest estimator fit**. It shares the frozen Phase 3 preprocessing statistics fitted on all training endpoints, including abnormal and unknown-target windows. This is allowed by the fixed comparison protocol and must not be described as a wholly normal-only preprocessing/model pipeline. Neither validation nor test contributes to those preprocessing statistics.

The source-time denominator was independently reconstructed from original validation labels before model predictions: 175,818 covered seconds, comprising 77,260 normal seconds (21.4611111111 hours), 87,935 abnormal seconds and 10,623 unknown seconds. All 23 original source hashes still matched at this check.

## Independent final artifact reconciliation

Audited final run `d8386c526a40f56133b5`, recorded in [experiment_manifest.json](../../reports/baseline/experiment_manifest.json). Two independent Python here-string audits were executed through `.\.venv\Scripts\python.exe -`; both completed successfully (exit code 0). These checks read saved outputs and the frozen train/validation inputs, without calling the training or evaluation implementation to calculate metrics and without reading test outcomes.

- Recomputed all final model/prediction/preprocessor artifact SHA-256 values, both baseline source-file hashes, protocol/dependency-file hashes, frozen split/report hashes and all five prior processed/state hashes. All matched their manifests. All 23 original raw-file byte hashes still matched; only the three validation sources were decoded for endpoint and exposure reconciliation.
- Verified all 70,332 saved prediction rows: exactly 17,583 endpoints per model, 16,518 eligible per model, validation partition only, identical window IDs and source metadata, exact endpoint class/family/phase correspondence to frozen targets, and exact raw validation endpoint labels.
- Independently reconstructed every pooled confusion count, precision/recall/F1, average precision from tied score groups and trapezoidal PR area. AP matched within `1e-15` arithmetic tolerance; all counts and ratios matched exactly. Per-well confusion counts, per-family detections/support, phase support/detections and absent-origin null metrics also matched.
- After verifying the trusted local joblib hash, reloaded its estimators independently. Logistic Regression and train-majority fit IDs equal the 7,649 eligible training IDs; Isolation Forest fit IDs equal the 3,541 known-normal training IDs; always-normal has no fit IDs. No validation/test ID appears in a fit set. Saved estimator settings match the fixed protocol. Logistic Regression has 10 iterations, finite coefficients/intercept and 120 features; Isolation Forest has 200 trees and effective sample size 256. Its threshold equals the negative fitted offset.
- Every reloaded model score and binary decision exactly reproduces its saved validation output. Feature names/order match all 120 frozen columns. The copied preprocessor hash equals the original frozen state.
- Reconstructed held decisions as independent Boolean coverage/alarm arrays over each original validation timeline. All monitored/normal/abnormal/unknown/normal-alarm seconds and every onset/censor count match. Raw validation cadence and ten-row endpoint spacing were checked explicitly before using this array reconstruction.
- All 21 saved failure examples match actual incorrect eligible predictions, exact scores, instance IDs, source paths and timestamps. Both rendered figures were visually inspected; axes, legends and confusion counts are readable. The PR plot identifies step curves, fixed operating points and overlapping naive references.

The complete exact metrics remain in [metrics.json](../../reports/baseline/metrics.json); the following independently reconciled counts summarize the operating-point consequences. Confusion matrices use true rows and predicted columns, ordered normal/abnormal.

| Model | Confusion matrix | AP | Confirmed false onsets | Normal alarm seconds / 77,260 | Censored positive starts |
| --- | --- | ---: | ---: | ---: | ---: |
| Always normal | `[[7724,0],[8794,0]]` | 0.5323889090688946 | 0 | 0 | 0 |
| Train majority (always abnormal) | `[[0,7724],[0,8794]]` | 0.5323889090688946 | 0 | 77,260 | 3 |
| Logistic Regression | `[[7509,215],[4054,4740]]` | 0.9359849049767661 | 0 | 2,159 | 1 |
| Isolation Forest | `[[103,7621],[0,8794]]` | 0.7355040853902104 | 5 | 76,230 | 2 |

Logistic Regression detects 135/152 family-2 endpoints and 4,605/8,642 family-8 endpoints. It misses 4,054 abnormal endpoints overall. All 215 false-positive endpoints occur on WELL-00011: every evaluable normal endpoint on that well is alarmed. Its initial episode is censored, explaining zero confirmed false onsets despite 2,159 normal alarm seconds. Isolation Forest detects every abnormal endpoint while alarming for 98.666839% of covered normal time. Its five confirmed false onsets correspond to 0.2329795496 per normal hour and 0.1023785960 per total covered replay hour. Always-abnormal occupies 100% of normal time even with zero confirmed onsets. These are offline source-time diagnostics; no application replay worker was executed.

## Integration evidence and remaining limits

The ML owner separately reported **73 passed in 6.53 seconds** for the 27 implementation tests plus these 46 independent cases on final source. The orchestrator separately reported its final whole-project regression completed with **214 passed in 15.19 seconds**, zero failures or skips. These results are attributed to their executing agents; the independent 46-case command above was executed by this reviewer.

Orchestrator handoff command: `.venv/Scripts/python.exe -m pytest tests/data tests/qa tests/test_data_pipeline.py tests/test_training.py -q -p no:cacheprovider --basetemp <workspace>/.local/pytest-phase4-<UUID> --tb=short`. A unique workspace temporary directory and narrow execution escalation addressed the existing Windows fixture ACL restriction.

The ML owner executed two consecutive final runs and recorded 14 byte-identical report/model/prediction artifacts in [verification.json](../../reports/baseline/verification.json). The reviewer independently recomputed all 14 final hashes and matched that record after the repeat completed. The repeat execution itself belongs to the ML owner's evidence; exact saved-model score reproduction was also checked independently above. Review Markdown links resolve, and `git diff --check` completed with no whitespace errors (Git emitted line-ending notices for other owners' shared files).

The software baseline is suitable as a reproducible starting point for a separately approved next experiment. **No detector is accepted for operational monitoring.** The validation cohort contains three published well IDs; each abnormal family has only one supporting source/well and neither was present in training. All existing groups were exposed in prior EDA. The published IDs are not independently verified physical wells, related/duplicate physical cases remain uncertain, and overlapping windows do not supply independent sample counts. Real-only validation says nothing measured about simulated/drawn performance. Undefined metrics and unsupported families remain explicitly null.

No threshold or hyperparameter was selected using validation outcomes, and no test prediction or metric was produced. High Logistic Regression AP does not justify retrospectively accepting its fixed threshold, which misses about 46.1% of abnormal endpoints; Isolation Forest's perfect recall does not compensate for near-continuous false alarm exposure. Sensor correlations/status channels do not establish physical causation; the existing phase/source/availability shortcut risks remain. A future phase needs a protected cohort with adequate family/group support and an approved recall/false-alarm criterion before further model acceptance claims.

Handoff: only `tests/qa/test_baseline_integrity.py` and this report were changed by the reviewer. No API or prediction-contract change is proposed. No unresolved software blocker was found in the reviewed scope. Root integration/progress updates and the explicit Phase 4 stop remain with the orchestrator; later-phase work requires user approval.
