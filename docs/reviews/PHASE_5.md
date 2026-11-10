# Phase 5 independent experimental integrity review

Status: pre-test selection audit and post-test saved-output audit complete. The one-shot test exposes unacceptable false-alarm behavior. Detector acceptance is withheld; a CatBoost latency protocol deviation remains explicitly documented.

## Assignment and evidence boundary

The reviewer owns this file and `tests/qa/test_model_selection_integrity.py` only. Model code, protocol, dependencies, model card, consolidated results and progress belong to other owners. Earlier Phase 4 no-test restrictions are superseded only by the user's bounded Phase 5 request and the orchestrator's explicit post-selection test release. No raw or processed test rows have been inspected by this reviewer during protocol review.

Read: engineering rules, architecture, API contract, progress, decisions, frozen split strategy, Phase 4 protocol, baseline training/evaluation interfaces and earlier QA tests. The existing cohort was exposed during EDA; an evaluation of its frozen test partition remains a development diagnostic, not a protected final generalization estimate.

## Pre-experiment concerns

- Freeze the finite candidate search, validation objective/tie rules, threshold candidates and false-alarm constraint before fitting. Record every candidate, including unsuccessful ones; test outcomes cannot revise the rule.
- Keep all validation comparisons on exactly the same source instances, endpoint IDs, eligibility and input schema. Unknown targets must not reset predicted alert episodes. Normal-time alarm occupancy must accompany false-onset rates.
- Three validation well groups and two abnormal families, each absent from train, provide inadequate support for an accepted closed-set multiclass task. Window-random calibration folds would reuse overlapping temporal samples. Any calibration must justify group separation and disclose shared-preprocessor limitations; otherwise defer calibration explicitly.
- Bind the selected artifact, preprocessing, threshold/calibration, split, protocol, dependencies and inference/evaluation code before test access. An exclusive persistent STARTED marker must precede test-row reads. Successful and interrupted attempts must refuse a fresh prediction pass; saved predictions may be audited without test re-inference.
- Timing is a hardware/environment-specific measurement, not an operational service guarantee. Measure a defined warm-up, batch shape, repetitions and whether feature computation/deserialization are included; do not select a model on nondeterministic timing ties.
- Preserve true partition provenance in saved test outputs. Prior baseline metric functions accept validation only; any internal metric adapter must validate and retain the real external evaluation scope.

## Protocol disposition

The fixed [Phase 5 protocol](../../reports/experiments/PROTOCOL.md) resolves the pre-experiment concerns: exactly eight boosted fits plus two saved baseline candidates; at most 203 thresholds per candidate; maximum recall under a declared diagnostic 5% normal-time alarm cap; AP, occupancy and stable-ID model tie rules; no calibration fit; explicit real-only and unsupported multiclass/deep-model scope; no post-selection refit. Protocol review found no blocking ambiguity. The cap is an engineering experiment choice, not an approved operational reliability target.

## Executed synthetic verification

Independent suite: **79 passed in 3.65 seconds**, zero failures/skips, using synthetic fixtures only. Command:

```powershell
$qaTmp = Join-Path (Get-Location) ('.local\pytest-phase5-qa-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/qa/test_model_selection_integrity.py -q -p no:cacheprovider --basetemp $qaTmp --tb=short
```

The initial sandbox execution encountered the known Windows temporary-fixture ACL restriction; a narrowly escalated execution of the same bounded test scope succeeded. This was an environment failure, not a passing test result. Earlier incremental runs had 24 and then 60 passing cases; the 79-case run supersedes those subset counts.

Coverage includes exact bounded candidate parameters; threshold ties/all-normal fallback; normal exposure during intervals whose endpoint label is unknown; strict metric denominators; recall/AP/occupancy/ID model ordering independent of latency; raw inference causality, gap resets, frozen imputation and unavailable-input abstention; rejection of labels/metadata/nonfinite values/invalid time/schema/masks; probability class orientation and bounds; validation/test scope preservation; exact-selection release; exclusive STARTED journal; fail-closed repeat and post-test search rejection; saved predictions after metric failure; 12 changed-selection-evidence cases; and six missing/inconsistent synthetic test-cohort cases.

Pre-fit review corrections verified in implementation/tests: reject invalid or finer-than-configured cadence before normal-time weighting, validate raw endpoint labels, bind current split/preprocessing summary and threshold/weight evidence, check runtime model dependencies before deserialization, flush/fsync STARTED before test reads, enforce complete frozen test source/group/window support, and persist the single test prediction output before later metric/report operations. Root and model owner also hardened fit checkpoints and recorded actual estimator parameters; independent actual-artifact checks remain pending.

No actual test outcome was read during these pre-test checks. A synthetic test invoking the one-shot function is not access to the project's test partition.

## Independent pre-test actual-artifact audit

An inline Python audit executed through `.\.venv\Scripts\python.exe -` completed successfully before any `test_access.json` existed. It used saved validation predictions and independently decoded only the three validation raw label sources; it did not invoke model training, prediction or evaluation functions to calculate the reported audit quantities.

- Verified all **175,830** saved candidate prediction rows: ten candidates, exactly 17,583 shared endpoints and 16,518 eligible windows each; exact frozen source/well/origin/partition/timestamp/endpoint metadata and raw-family/phase targets.
- Independently reconstructed all **17,583 normal exposure weights** from raw one-second labels and bounded intervals. Total exposure reconciled to 77,260 normal seconds, 87,935 abnormal seconds and 10,623 unknown seconds. Unknown endpoints' later normal exposure remains included.
- Independently regenerated every quantile/boundary threshold and reconciled all **1,481 deduplicated threshold rows** across ten candidates, including confusion counts, recall, occupancy, feasibility and threshold tie rules. Independently selected each model's threshold and then the overall candidate using the frozen recall/AP/occupancy/ID order.
- Recomputed all candidate pooled confusion matrices and precision/recall/F1. Reconstructed AP directly from cumulative positives at tied-score boundaries and trapezoidal area separately; both matched saved metrics within `1e-15` arithmetic tolerance. Family detections/support, unsupported synthetic/drawn slices, episode onset/censor counts and exact normal-alarm exposure matched.
- Verified protocol and implementation/dependency-file hashes, frozen split/preprocessing report and all processed artifact hashes, validation prediction hashes, threshold/weight evidence, selected bundle manifest and three contained artifacts. Eight actual fit-budget entries correspond to eight complete checkpoint model hashes; no ninth fit was performed.

Approved selection identity: SHA-256 `dfbe88250db8808d58730ab6f0010da3c548cb4b1c26715ba4a4b78057e7130b`; run `c4e1835a82620306778a`; selected `logistic_regression_retuned`; threshold `1.1881945293311268e-14`. Independently reproduced validation recall is `0.971344098248806`, AP is `0.9359849049767661` to saved precision, and normal-time occupancy is `0.049301061351281386`. Confusion matrix: `[[7344,380],[252,8542]]`. This very small probability cutoff emphasizes that these are uncalibrated cross-domain scores, not an operational probability threshold.

The first search attempt stopped before selection because nine recomputed Logistic Regression validation scores differed from the preserved Phase 4 outputs by at most `3.1225e-17`. Root approved a pre-test `atol=1e-14, rtol=0` consistency check and use of the canonical inference wrapper's scores for the retuned candidate. Original fixed baseline outputs were unchanged. All eight fitted candidates were reused from hash-checked checkpoints; the correction changed no search parameters, objective or test-access policy. The independent threshold audit used the resulting exact persisted Phase 5 scores. Same-batch selected-bundle reload still requires exact scores/decisions.

Root separately reported **309 total tests passed in 12.31 seconds**, comprising prior 214, six independent feature-review tests, ten model-owner tests and these 79 QA cases. Root also checked raw-sensor inference on all three validation instances: all 17,583 decisions and timestamps matched frozen-feature predictions; score differences were bounded by `3.1086244689504383e-15`. These are attributed to root execution, distinct from the reviewer's synthetic and manual metric audit. The model owner additionally recorded exact same-batch reload reproduction for all ten candidates in [verification.json](../../reports/experiments/verification.json).

Pre-test disposition communicated to root: **approve one-shot diagnostic test for this exact immutable selection**, contingent on no code, selection or bundle changes. Root retains release-file ownership and the actual invocation. Test results cannot trigger model, feature, calibration or threshold changes.

## Independent saved-test audit

Root wrote the exact-selection [release](../../reports/experiments/TEST_RELEASE.json), executed the one-shot command and then authorized the reviewer to inspect saved test outputs and original labels. The [test journal](../../reports/experiments/test_access.json) records one attempt, STARTED `2026-11-10T08:50:26.679964+00:00` and COMPLETE `2026-11-10T08:50:29.376679+00:00`. Its selection hash is identical to the approved pre-test value. The reviewer made **zero estimator calls on test** and did not alter code, model, calibration, threshold or selection.

A second independent inline Python audit through `.\.venv\Scripts\python.exe -` completed successfully:

- All **4,480** saved test endpoints match the exact frozen metadata, raw/family/phase targets and retained-sensor quality mask. There are **3,060 eligible windows**, four source instances and two published well IDs. Available scores and fixed-threshold decisions agree; unknown labels remain excluded from classification metrics.
- Independently recomputed pooled and per-well confusion counts, precision/recall/F1, tied-score AP, trapezoidal PR-AUC, family/phase counts and unavailable-origin support. Recomputed Brier score and log loss from saved probabilities. All match saved values within the declared floating arithmetic tolerances.
- Independently decoded the four original test label timelines and checked every endpoint label/timestamp. Coverage comprises **13,251 normal**, **17,362 abnormal** and **14,164 unknown seconds**, totaling **44,777 seconds**. All 13,251 normal seconds are under alarm. Four positive starts are censored at source boundaries; there are no confirmed new false/abnormal/unknown onsets. Zero new false onsets therefore does not indicate good behavior.
- Verified all three stored failure examples against actual incorrect eligible endpoints, exact scores, source instance and timestamps. All **23 original Parquet hashes** still match; only the four test sources were decoded in this post-test audit. Saved predictions, metrics, selection, protocol, implementation/dependency files and selected bundle hashes remain consistent with the release/journal.

| Diagnostic test measure | Independently verified value |
| --- | ---: |
| Precision | 0.5673202614379085 |
| Recall | 1.0 |
| F1 | 0.7239366138448707 |
| Average precision | 0.45285483310534924 |
| Trapezoidal PR-AUC | 0.4519014344467603 |
| Confusion matrix `[[TN,FP],[FN,TP]]` | `[[0,1324],[0,1736]]` |
| Normal-time alarm occupancy | 1.0 |
| Brier score | 0.3565320010584989 |
| Log loss | 1.5756388199775637 |

All 962 family-1, 706 family-4 and 68 family-6 windows are flagged, alongside every normal window. Family 4 was present in training; families 1 and 6 were not. Perfect binary recall here results from always-positive decisions and does not demonstrate useful event discrimination. Test AP is below positive prevalence `0.5673202614379085`. The selected validation threshold does not transfer its 5% normal-time occupancy cap to these held-out development groups.

## Remaining finding and final disposition

**Medium, documented benchmark deviation:** the CatBoost probability wrapper does not pass an explicit inference `thread_count`. A read-only check of the installed `CatBoostClassifier.predict_proba` signature confirmed `thread_count=-1`; its installed docstring states that this uses the number of CPU cores. Training was configured with one thread, and the wrapper limits supported native thread pools, but this does not establish single-thread CatBoost inference. Consequently the reported CatBoost latency cannot be described as a controlled single-thread comparison. The finding was discovered after the locked test; code and measurements remain preserved. Latency was not a selection tie-break, and the selected model is Logistic Regression, so this does not change the chosen model or its test evaluation. A separately authorized benchmark correction can address it later.

The model selection software, audit trail and one-shot evaluation are complete within the declared diagnostic scope. **No model is accepted for reliable monitoring.** On test, the chosen threshold alarms throughout known-normal time; low independent group/family support, prior EDA exposure, structural missingness, uncalibrated scores and unsupported synthetic domains remain limitations. There is no supported multiclass, causal, unseen-physical-well or production-reliability claim. Poor test results are retained unchanged; no second model or threshold was tried on test.

## Handoff status

Returned ownership of `tests/qa/test_model_selection_integrity.py` and this review to the orchestrator. No shared API contract change is proposed. Root owns consolidated results, model card, progress and the Phase 5 stop. Further tuning, acquisition, calibration, benchmark correction or deployment requires a separately approved scope.
