# Independent Phase 3 preprocessing review

Review date: 2026-11-10. **Complete: no unresolved blocking leakage defect in the reviewed preprocessing artifacts.** The orchestrator owns actual-data CLI execution and final integration records; the reviewer independently reconciled the resulting artifacts against original data. This review covers reusable preprocessing, causal features, grouped partitioning and train-only fitted statistics. It does not evaluate a detector or authorize model training.

## Ownership and independence

The reviewer owns this report and `tests/qa/test_pipeline_leakage.py` only. The data engineer owns the implementation and its unit tests; the orchestrator owns integration, dependencies, shared documentation and actual-data diagnostic artifacts. Findings are sent to the owner for correction without editing their files.

## Data evidence checked independently

The reviewer read the acquisition manifest, verified SHA-256 for all 23 original Parquet files, and read their timestamp indices with Pandas/PyArrow. The 582,220 selected rows have naive, unique, strictly increasing indices; every within-instance interval is one second. No resampling is justified for this acquired subset. Source timezone remains unverified. This check changed no source files and used no implementation aggregation functions.

All current instances and their 12 published real well IDs were exposed during Phase 2 EDA. A diagnostic allocation can verify software boundaries; it cannot produce a pristine final-test cohort or establish class-supported generalization. The protected-evaluation path must fail closed on exposure and insufficient declared group/class support.

## Independent adversarial verification

The reviewer created [test_pipeline_leakage.py](../../tests/qa/test_pipeline_leakage.py), using independently constructed synthetic DataFrames and original-like Parquet fixtures. No telemetry was downloaded and no model was fitted. The positive protected-mode fixture is a software-path test, not evidence that any current 3W well is unexposed.

The following command was executed after the implementation owner confirmed stable source files:

```powershell
$qaPipelineTemp = Join-Path (Get-Location) ('.local\pytest-phase3-qa-final-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_data_pipeline.py tests/qa/test_pipeline_leakage.py -q -p no:cacheprovider --basetemp $qaPipelineTemp --tb=short
```

**Actual result: 67 passed in 7.09 seconds, zero failures or skips.** This comprises 20 implementation tests and 47 independent QA cases. Initial sandbox attempts could not access pytest temporary fixtures, including a workspace-local base directory; the complete command passed using narrow execution escalation. The final result is not a model evaluation, application test or deployment check.

| Reviewed invariant | Executed independent evidence |
| --- | --- |
| Temporal causality | Mutating future holdout readings leaves earlier raw features and frozen-normalized values unchanged; no backward fill into an all-missing earlier window |
| Labels and metadata excluded | Changing valid `class`/`state` values preserves feature values and endpoint schedule; explicit selection of labels/time/source identifiers as sensors is rejected |
| Feature meanings | Analytic examples verify population standard deviation, extrema, rate with missing samples and elapsed time, and a trend that differs from endpoint rate |
| Instance and gap isolation | Short instances borrow no preceding history; timestamp gaps reset complete windows |
| Train-only statistics | Mixed and holdout fit batches are rejected; normalization matches independently calculated training mean/std; transforming holdout data does not mutate state |
| Missing and constant inputs | Training-all-missing columns remain dropped even when holdout values are available; constant observed zeros remain finite; unknown-label training windows can fit unsupervised statistics |
| Group separation | Repeated published well IDs and transitive duplicate-byte links remain together; allocation is independent of input order for a fixed seed |
| Source policy | Simulated/drawn instances are excluded by default and training-only when enabled |
| Target policy | Unknown endpoints retain nullable targets; documented transient family/phase survives; transient exclusion changes supervision without dropping feature windows; undocumented label codes are rejected |
| Protected support | Missing exposure ledger, exposed real well IDs, absent required classes and raw labels that never become eligible endpoints are rejected; an explicitly fresh, adequately supported fixture succeeds |
| Persisted invariants | Save/load produces exactly identical normalized outputs; unexpected state fields and mismatched frozen splits are rejected; mutating a batch cannot forge training membership |
| Manifest semantics | Recomputed checksums do not permit same-well/duplicate sources to be divided, synthetic sources moved into holdout, or protected exposure provenance removed |
| Loader identity | Matching source bytes cannot hide forged well/origin/event/instance metadata; valid fixture loading preserves original bytes and source identity |
| Public imports | Both package import orders succeed in fresh Python processes |

## Resolved findings and implementation inspection

The reviewer inspected `ml/data_pipeline/`, `ml/features/`, the implementation tests, and the [feature specification](../FEATURE_ENGINEERING.md), read-only. No cross-owner files were edited.

- **High, resolved — grouping identity trusted from a malformed manifest.** Original checksums alone did not prove that manifest well/origin/instance metadata matched the published path. The loader now derives and validates identity from pinned revision plus source path, enforces the original local-path mapping and rejects duplicate source paths. It parses the already verified bytes, avoiding a second unverified read.
- **High, resolved — persisted split semantics.** The initial validator checked a checksum and partition consistency within a group ID, but not that related identities shared that group. Root independently identified the same gap. Validation now enforces same-well/hash/related-family membership, canonical group identity, real partition presence, synthetic policy and protected support/provenance. Checksums detect corruption; they are not authorization against arbitrary malicious Python.
- **Medium, resolved — public import order.** Root identified a circular-import risk. Moving feature constants into an independent leaf module permits both public import orders; the reviewer verified both in separate processes.
- **Coverage guard verified.** Raw class support is insufficient when a class occurs only before the first complete window or is skipped by endpoint selection. Protected construction checks actual eligible endpoint/group support after window generation. It never searches a new seed to manufacture favorable coverage.

The implementation preserves the exact sensor allowlist and source units, uses no raw interpolation/imputation, computes summaries from observed samples inside each trailing window, and freezes feature medians/scaling from assigned training windows only. Unknown training labels do not select features or fitted statistics. Transient-family mapping is an explicit target policy, with raw labels and phase retained outside the feature matrix.

The reviewer read [prepare_data.py](../../scripts/prepare_data.py) without editing it. It fits only `batch.subset('train')`, writes features/targets/provenance/quality separately, checks originals and input hashes before publication, and records code/dependency/split/state provenance. Per-file writes are atomic; publication of the entire artifact set is not a transactional operation. The summary's recorded hashes and successful round trips identify a completed generation. Actual-data execution and broader regression results are reported by the orchestrator separately.

## Independent actual-artifact reconciliation

After the orchestrator executed the CLI, the reviewer read the [preprocessing summary](../../reports/preprocessing_summary.json), [development split](../../data/manifests/development_split.json), saved preprocessing JSON and four output Parquets. The reviewer did not rerun the CLI or claim its repeatability check as an independent execution.

| Check | Independently observed result |
| --- | --- |
| Artifact and provenance hashes | All recorded artifact, implementation-code and dependency-file hashes match current files; split/state fingerprints agree and saved state loads successfully |
| Partition isolation | Every source instance, published well ID and connected group appears in exactly one included partition; every included window is real-source |
| Window construction | Source-derived endpoint positions independently reconstruct exactly 32,197 windows; every window spans 59 elapsed seconds for 60 one-second observations |
| Partition window counts | Train 10,134; validation 17,583; test 4,480; group-based ratios do not imply similar row/window counts |
| Targets | Every endpoint raw label matches its source row; independently mapped family labels match; 4,970 unknown endpoints and 10,710 transient endpoints remain explicit |
| Feature values | Three windows per included source, 42 windows total, independently reconstructed from raw values; all 5,040 retained normalized-feature comparisons agree within `rtol=2e-7, atol=2e-7` |
| Fitted normalization | The 120 retained normalized training columns have mean zero within `1e-9`, and population standard deviation zero or one within `1e-9`; 162 raw columns yield 42 train-all-missing drops |
| Quality | No output window is entirely missing across the selected sensors; this does not establish a sufficient-evidence policy for a future detector |
| Final original hashes | All 23 source Parquet SHA-256 values still match the acquisition manifest after integration and independent rereads |

These are independent inline Python/Pandas/NumPy artifact audits, not additional persisted test cases or predictive metrics. Per-window calculations did not call the implementation's feature-aggregation function. The validation/test names remain explicitly **development diagnostics**; all involved well IDs were already EDA-exposed.

## Remaining limitations and next dependencies

The development partition is not a pristine final holdout. Event-family support is insufficient for the intended real-well-disjoint multiclass evaluation. Near-duplicate subsequences, private physical-well aliases, undocumented synthetic-generator relationships and upstream interpolation remain wider-cohort limitations. The grouping checks do not prove their absence.

Finite imputed features do not prove adequate observed evidence. Quality counts remain separate, and a later detector must define its minimum evidence/abstention policy using retained inputs. Default window/stride and median standardization are reproducible choices, not validated optima. No predictive metric, hypothesis improvement, calibration or operational claim follows from these tests.

No model training, further acquisition or application implementation occurred in this review. Those activities require a later explicit authorization and the cohort/evaluation gates in the [split strategy](../SPLIT_STRATEGY.md).
