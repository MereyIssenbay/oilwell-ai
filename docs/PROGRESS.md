# Project progress

Updated: 2026-11-10 (Asia/Oral).

## Authorization and status

- **Phase 0: complete.** Architecture, contracts, configuration, scaffolding, static verification and independent review are complete.
- **Phase 1: complete**, authorized and executed on 2026-11-10. Bounded acquisition, inspection, automated validation, provenance documentation and independent integrity review only.
- **Phase 2 EDA: complete**, authorized and executed on 2026-11-10. Actual-data exploration, charts, hypotheses, split recommendation and independent leakage review only. This user request supersedes the original roadmap's Phase 2 model-training schedule. Work stops here; additional acquisition, production preprocessing, training and application implementation require a new approval.
- **Phase 3 preprocessing: complete**, authorized and executed on 2026-11-10. Reusable, deterministic grouped splitting, causal features and train-only preprocessing statistics, with independent leakage review. No model training or additional telemetry acquisition. Current-data partitions remain development diagnostics. Stop here pending the user's next phase approval.
- **Phase 4 baseline: complete**, authorized and executed on 2026-11-10. Naive references, Logistic Regression and Isolation Forest were compared on the unchanged development validation split, with independent experimental review. No test predictions, tuning, additional acquisition or application implementation. The software baseline is reproducible; detector acceptance remains withheld. Stop here pending user approval of further work.

- **Phase 5 model selection: complete** (2026-11-10). Eight boosted fits and two saved incumbents were compared under a frozen validation rule, independently reviewed and followed by exactly one selected-model diagnostic test evaluation. The selected Logistic Regression alarms throughout normal test time and is rejected for monitoring. Complete inference artifacts and honest failure evidence are saved. No post-test tuning, additional acquisition or application work. Stop after Phase 5 pending user approval.

- **Phase 6 backend and ML inference: complete** (2026-11-10). Six local typed endpoints, startup-loaded frozen model, shared preprocessing, PostgreSQL persistence, idempotency, structured errors/logging, OpenAPI and independent contract/integration checks. All 429 tests passed. Model monitoring acceptance remains false; no model changes or test re-inference. Stop after Phase 6 pending user approval.

- **Phase 7 historical replay: complete** (2026-11-10). API controls, causal frozen inference, durable PostgreSQL events/episodes, SSE reconnection, restart/concurrency checks and actual normal-to-transient demo are complete. **511 tests passed**, without failures or skips. Frozen model/threshold and one-attempt test evidence remain immutable; detector acceptance remains rejected. Stop after Phase 7.

## Phase 0 delivered design

- Architecture/MVP scope, component boundaries, replay lifecycle, evidence-only copilot and local deployment plan.
- Persistent engineering rules, disjoint ownership and six Codex agent profiles.
- Multi-agent configuration: enabled, three concurrent subagents maximum, primary orchestrator excluded.
- Pinned 3W v2.0.0 metadata baseline with 27 exact sensor names, class/transient registry, origin/identity/time caveats and license information.
- Canonical prediction JSON Schema and explicitly synthetic abstention example; API routes, versioning, errors, replay/idempotency/SSE and explanation contracts.
- Milestone dependency graph, acceptance gates, architecture decisions, root README, ignore rules and empty-credential environment template.
- At Phase 0 delivery, module ownership directories contained empty placeholders; no runtime implementation was implied.

## Phase 0 verification log (historical)

| Check | Actual result | Scope/limitation |
| --- | --- | --- |
| Workspace inspection | Initial repository contained only `.codex/config.toml` and `.codex/agents/ml_engineer.toml`; no commits yet | Existing ML role intent preserved and expanded |
| Upstream metadata review | Pinned commit `914af287b1cf3e5207dce0da1e9dc08361c9adeb`; dataset version 2.0.0; 27 sensors; 10 base event classes | Read documentation/configuration/loader/Git tree only; no telemetry acquired |
| Codex TOML parsing | All seven TOML files parsed with Python `tomllib`; six unique role names match filenames | Validates syntax and required role structure |
| Codex strict startup configuration | `codex --strict-config app-server --print-startup-config` exited 0 on CLI `0.164.0-alpha.11.1` | User-profile temp/PATH permission warnings; live activation of six roles not tested |
| JSON Schema validation | Draft 2020-12 schema passed `check_schema`; saved abstention fixture and one temporary usable synthetic shape validated with `FormatChecker`; 18 malformed variants rejected | Shape/conditional constraints only; no Pydantic runtime, model predictions or observed sensor values |
| Sensor/event registry shape | 27 unique sensor enum entries; 11 output values (10 source event families plus abstention) | Metadata schema, not class coverage in an acquired training cohort |
| Required files and directory boundaries | 49 files passed the initial integration audit, then the independent review report was added (50 files total); all requested root/docs/config paths present; data/ML/backend/frontend/LLM/tests/scripts contain `.gitkeep` only | No telemetry, model or application code |
| Local documentation links | Final all-document check resolved all 26 local links | External sources were inspected during research; no claim of continuous availability |
| Ignore policy | `git check-ignore --no-index -q` confirmed 8 private/generated paths ignored and 6 intended versioned paths visible | Probe paths were not created; `.env.example`, project agents and placeholders remain versionable |
| Whitespace and credential template | All audited files had valid UTF-8, no trailing whitespace and final newlines when nonempty; credential fields blank; limited private-key/API-token pattern scan clean | Static scan, not a comprehensive secret audit; no credentials were introduced |
| Working-tree review | `git status --short --untracked-files=all` showed requested new/untracked scaffolding; `git diff --check` exited 0 | Git diff does not cover untracked content; separate all-file whitespace audit did. No commit was made |
| Independent review | Reviewer verified both corrections and reported no remaining Phase 0 blockers; [review report](reviews/PHASE_0.md) saved | Read-only component review plus report creation; no runtime validation |
| Final closeout audit | PASS: 50 text/scaffold files, 26 local links, all TOML files, JSON Schema/example, whitespace/newlines, completed phase status and empty module boundaries | Executed with inline Python using pathlib, tomllib and jsonschema; no services or application tests run |

Phase 0 used Python 3.13.3 for static checks without a runtime dependency environment. Those checks do not establish model quality, API behavior or deployment readiness.

## Phase 1 deliverables and verified results

The user explicitly authorized the acquisition/audit phase on 2026-11-10 and prohibited preprocessing and training. The orchestrator updated the phase gate, delegated acquisition/inspection to `data_engineer` and independent integrity review to `qa_reviewer`, and retained the validator, shared documentation, dependencies and final integration. File ownership remained disjoint; no nested delegation was used.

Requested deliverables:

- [scripts/download_data.py](../scripts/download_data.py): deterministic bounded acquisition with original-byte preservation, pinned Git blob and SHA-256 checks, retries, atomic publication, resumable manifest and offline verification.
- [scripts/validate_data.py](../scripts/validate_data.py): offline integrity/schema/label/time/missingness/grouping audit; source files are read-only and JSON output is constrained to `reports/`.
- [data/README.md](../data/README.md): setup, download alternatives, observed schema, provenance, origins, licensing and limitations.
- [docs/DATASET_AUDIT.md](DATASET_AUDIT.md): consolidated measured findings and source discrepancies.
- [reports/data_summary.json](../reports/data_summary.json): per-file and aggregate audit measurements, exact registry, dependency/code hashes and leakage checks.

Supporting artifacts: [subset manifest](../data/manifests/subset.json), [ini-derived metadata registry](../data/manifests/dataset_metadata.json), [pinned dependencies](../requirements-data.txt), downloader/QA tests and [independent review](reviews/PHASE_1.md). Original files are under ignored `data/raw/3w/2.0.0/914af287b1cf3e5207dce0da1e9dc08361c9adeb/`.

| Check / command | Actual result | Scope / limitation |
| --- | --- | --- |
| Official documentation, ini, license and pinned-tree inspection | Dataset v2.0.0 at the existing pin; 27 exact sensors; 10 base events and seven documented transient codes; state 0-8 confirmed from author manuscript | Metadata is distinguished from measured bytes; source timezone remains unverified |
| `.venv/Scripts/python.exe scripts/download_data.py --dry-run` and normal acquisition | Exit 0; 23 Parquets, 10,719,108 bytes; eight original provenance documents, 58,535 bytes | Covers all 19 available directory/origin strata plus four additional real well IDs; size-biased subset, not prevalence sampling |
| `.venv/Scripts/python.exe scripts/download_data.py --offline` | Exit 0; all 31 originals verified without network or writes | Sizes, pinned Git blob SHA-1 and SHA-256 checked; QA also compared with independently retrieved tree metadata |
| Repeat normal acquisition | Exit 0; all original hashes and modification times unchanged | Existing matching originals reused; conflicts are refused |
| `.venv/Scripts/python.exe scripts/validate_data.py` | Final exit 0; 23 readable files, 582,220 rows, zero errors and 74 warnings | Warnings: 23 all-missing-sensor summaries, 14 missing-class, 14 missing-state and 23 unknown-timezone findings; no values repaired |
| Actual schema and footer checks | All files: 27 Arrow double/Pandas float64 sensors; two Arrow int16/Pandas Int16 labels; naive timestamp[ns] index; Brotli compression | Differs from upstream nullable Float64/Int64 prose; raw types preserved |
| Per-origin rows | Real 322,725; simulated 201,894; drawn 57,601 | 14 / 7 / 2 files; 12 distinct real anonymized well identifiers |
| Missing labels and sensors | 50,400 null values in each label; first 3,600 rows in every selected real file; four sensors entirely missing | P-JUS-BS, P-MON-SDV-P, PT-P and QBS are entirely missing in this subset, not necessarily globally |
| Timestamp / duplication / overlap checks | All selected indices monotonic, no duplicate/null timestamps, every interval one second; no duplicate bytes/full-frame fingerprints or overlapping same-well intervals found in subset | Does not exclude near-duplicates, shared subsequences or problems outside the selected files |
| Independent recomputation | Reviewer reread every Parquet and reconciled all row counts, sensor-null counts and class/state distributions with the report | Source hashes unchanged after reads; no validator counting functions reused for the reconciliation |
| Combined pytest suite | **55 passed, zero failed, zero skipped**: 16 downloader tests and 39 independent integrity tests | Synthetic offline fixtures; command and execution details in independent review. No model/application/end-to-end tests |
| `.venv/Scripts/python.exe -m pip check` | No broken requirements found | Isolated `.venv`, pinned dependency versions; executed on Python 3.13.3 only |
| Final source compilation | `py_compile` passed for both scripts and both test modules | A broader compileall invocation encountered inaccessible ignored pytest temp folders; the explicit four-source check completed successfully |
| Final repository / provenance audit | PASS: 61 Git-visible project files, 60 valid local links, strict JSON and whitespace checks, current script/manifest/dependency hashes, all 31 originals ignored by Git | Installed versions match every requirements pin; ML/backend/frontend/LLM and interim/processed directories still contain placeholders only |
| `git diff --check` | Exit 0 | Git emitted LF-to-CRLF conversion notices only; new files were separately whitespace-checked. No commit was made |

Final report provenance includes the base Git revision plus dirty-working-tree status and SHA-256 of the downloader, validator, dependency file and acquisition manifest. The report was regenerated after the reviewed code fixes; the code hashes identify the actual uncommitted implementation, not just its base commit.

QA found and verified four implementation corrections: retry interrupted HTTP responses; reject a raw-root symlink escape; constrain report output and use unique temporary files; handle malformed root manifest types with documented exit codes. No source data was changed to satisfy a test. Initial sandbox network/temp-fixture permission failures were resolved by narrow approved execution escalation; no external access blocker remains. Generated failed-test cache directories were removed after checking their exact workspace paths.

## Phase 2 deliverables and verified results

The orchestrator assigned EDA to `data_engineer`, testable hypotheses to `ml_engineer`, and an independent leakage/integrity review to `qa_reviewer`, with three disjoint assignments. The orchestrator retained the split recommendation, dependencies, shared phase records and integration. All owners returned their files at handoff; no nested delegation was used.

Delivered:

- [Executed notebook](../notebooks/01_eda.ipynb) and [reproducible EDA module](../scripts/data/eda.py).
- [Chart and methods guide](../reports/eda/README.md), eight actual-data PNGs, eight CSV tables and [EDA summary/provenance](../reports/eda/eda_summary.json).
- [Five testable ML hypotheses](ML_HYPOTHESES.md), with controls, falsifying outcomes, metrics and support limitations. These are proposed experiments, not demonstrated model results.
- [Split strategy](SPLIT_STRATEGY.md), including published well-ID evidence, development exposure, class support, future protected-test requirements and leakage controls.
- [Independent review](reviews/PHASE_2.md), three EDA tests, 16 independent QA tests and [pinned EDA dependencies](../requirements-eda.txt). Phase 1 dependency pins remain unchanged.

Measured findings use all 582,220 rows from the same 23 immutable files:

| Question | Observed finding and interpretation |
| --- | --- |
| Class imbalance | Real rows: 125,940 normal, 107,094 transient, 39,291 steady event and 50,400 unknown. Family 8 contributes 86,422 / 146,385 real abnormal rows (59.04%) from one published well ID; row volume is not independent event support |
| Missingness and variation | Four sensors are entirely missing; availability varies by origin and class/well mixture. P-PDG is observed but constant zero in the three selected WELL-00002 files. No zeros were reclassified or missing values filled |
| Normal/event comparison | The event-1 WELL-00002 P-TPT median is 17.09 MPa over 4,754 known-normal rows versus 14.56 MPa over 9,617 abnormal rows. This descriptive association does not establish causality or predictive transfer |
| Correlations and origins | P-PDG/P-TPT within-instance correlation is defined in only 2/14 real files, with median -0.3107; simulated median is 0.9868 across 7/7 files, with a wide range. Pair counts, valid-instance support, constants and undefined values are retained; no causal or independence claim is made |
| Transitions | 61 raw-label runs; 38 within-file changes, comprising 24 known-label changes and 14 unknown boundaries. Four of 14 transient runs are censored. Unknown-to-abnormal boundaries are not verified onsets |
| Grouping and class coverage | The public manuscript documents stable real well IDs across directories. Twelve real IDs are present; most undesirable families have one supporting real ID, family 4 has two and family 9 has none. No undesirable family supports three disjoint real groups in this subset |

`class` and `state` remain labels, never sensor inputs. Only the exact 27-sensor allowlist enters correlations. Statistical summaries use full-resolution observations; only sensor line display is decimated, to at most 1,500 positions per contiguous finite segment, preserving missing/time gaps and full-resolution label shading. Pressure scaling is display-only. Raw timestamps remain in their unknown source timezone basis.

| Verification | Actual result | Scope / limitation |
| --- | --- | --- |
| EDA module and notebook execution | Eight PNGs, eight CSVs and summary produced; notebook has 17 cells, eight executed code cells, zero stored errors | Executed on Windows/Python 3.13.3 in project `.venv`; no training or application execution |
| Notebook/report consistency | All eight embedded PNGs byte-match saved report images; script and dependency provenance hashes match | Reproducible descriptive artifact, not model evaluation |
| Independent raw-derived reconciliation | QA reconciled 52 class records, 837 missingness records, 621 availability records, 8,073 pair records, 1,053 correlation summaries, 158 condition summaries, 61 runs and 38 boundaries | Independent inline audit without EDA aggregation functions; details in review |
| Source integrity | All 23 original Parquet SHA-256 values unchanged after EDA and independent rereads | No additional telemetry acquired; existing original metadata and source selection retained |
| Combined pytest suite | **74 passed in 1.00 seconds, zero failed/skipped**: 55 Phase 1 tests, three EDA tests and 16 independent EDA QA tests | Offline acquisition/integrity/descriptive-analysis checks; no predictive performance, application or deployment claims |
| Dependency check | `.venv/Scripts/python.exe -m pip check`: no broken requirements found | Phase 1 pins preserved; EDA additions pinned separately |
| Visual and independent review | All eight charts inspected during integration; corrected footer spacing and selected final figures rechecked; no unresolved Phase 2 review blocker | Review resolved display-point bounds, timestamp-gap segmentation, axis comparisons, censoring and metric-support wording |
| Final repository/provenance audit | PASS: 87 Git-visible project files, 127 valid local links, seven strict JSON/notebook files, valid notebook schema, 50 installed dependency pins and three changed Python sources compiled | All 23 Parquet hashes match; originals remain ignored; Phase 1 scripts/manifests/report/pins unchanged; application and processed-data directories contain placeholders only |
| `git diff --check` | Exit 0; separate UTF-8/newline/whitespace audit also passed for tracked and new text files | Git emitted LF-to-CRLF conversion notices only; no commit was made |

Combined test command: `.venv/Scripts/python.exe -m pytest tests/data tests/qa -q -p no:cacheprovider --basetemp <unique-workspace-temp-path> --tb=short`. Initial notebook connection-file and pytest fixture ACL restrictions were resolved by narrow execution escalation. The successful notebook kernel was shut down; no services were installed or started.

The five future hypotheses compare values against availability shortcuts, trailing changes against absolute levels, multiple sensors against a single-channel baseline, transient supervision against steady-only supervision, and synthetic augmentation against real-only training. Their effects are untested. All 23 instances and all 12 published real well IDs are recorded as development-exposed, including future files from those same IDs for an unseen-well evaluation.

## Phase 3 deliverables and verified results

The user authorized preprocessing after Phase 2 and explicitly excluded final-model training. The orchestrator assigned `ml/data_pipeline/`, `ml/features/` and `tests/test_data_pipeline.py` to `data_engineer`, and the separate leakage tests/review to `qa_reviewer`. Root retained integration, the CLI, shared docs, dependencies and diagnostic reports/manifests. Both agents returned ownership at handoff. No overlapping writers or nested delegation were used.

Delivered:

- [ml/data_pipeline/](../ml/data_pipeline/): validated source/config/split/state contracts; checksum-verified original-byte Parquet loading; deterministic connected-well splitting; exposure/support guards; separate window features, targets, provenance and quality; train-only feature imputation/normalization; JSON state save/load.
- [ml/features/](../ml/features/): observed-value trailing mean, population standard deviation, min/max, elapsed-time rate of change and least-squares recent trend. Window length, stride and expected cadence are configurable.
- [tests/test_data_pipeline.py](../tests/test_data_pipeline.py): 20 implementation tests, plus [47 independent leakage cases](../tests/qa/test_pipeline_leakage.py) and [review report](reviews/PHASE_3.md).
- [FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md), [pinned pipeline dependencies](../requirements-pipeline.txt), [reproduction command](../scripts/prepare_data.py), [development split](../data/manifests/development_split.json) and [preprocessing summary](../reports/preprocessing_summary.json).
- Ignored local `data/processed/phase3/`: preprocessing JSON and separate feature/target/metadata/quality Parquets. No processed telemetry or model binaries were added to Git.

Pipeline policy: preserve the verified one-second cadence without resampling; reset windows at source/time gaps; never interpolate or backward-fill. Use only the exact sensor allowlist, excluding `class`, auxiliary `state`, timestamps and source identifiers. The registry's actual `ESTADO-*` valve sensors remain candidates. Keep unknown targets nullable. Default endpoint-family targets include only documented transient mappings, while retaining raw code/phase; an explicit exclusion mode changes supervision without moving the windows. Fit feature medians and post-imputation mean/std on every assigned train window, including unknown endpoints; freeze train-allmissing column drops and the fitted schema. Constant observed zeros are retained. Quality is separate and does not itself define a future detector's abstention policy.

The default actual-data run loaded the same 23 originals, 582,220 rows. It included 14 real files, 322,725 rows, excluding nine simulated/drawn sources. With 60 rows/window, stride 10 and seed 42, it produced **32,197 windows**, 162 candidate features and **120 retained features**; 42 columns were entirely missing on training windows and dropped. Seven affected sensor families include four globally absent channels plus three absent from this particular training allocation; holdout availability never informed the drop decision.

| Diagnostic partition | Real well groups | Source instances | Windows | Supervised-eligible windows | Unknown-target windows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 7 | 7 | 10,134 | 7,649 | 2,485 |
| Validation | 3 | 3 | 17,583 | 16,518 | 1,065 |
| Test | 2 | 4 | 4,480 | 3,060 | 1,420 |

Group-count rounding yields 7/3/2, not similar row/window proportions. There are 4,970 unknown endpoints and 10,710 transient endpoints. No output window is entirely missing across all selected sensors. Some families occur only outside train; warnings are retained rather than changing seeds to obtain attractive coverage. All partition names remain **development diagnostics**, not an untouched final evaluation.

| Verification / command | Actual outcome | Scope / limitation |
| --- | --- | --- |
| `.venv/Scripts/python.exe scripts/prepare_data.py` | Exit 0; output counts above; source checks, saved-state round trip and four Parquet round trips exact | Original bytes unchanged, no event detector fitted |
| Repeat identical command | Exit 0; all seven published files byte-identical: split, summary, state and four Parquets | Determinism demonstrated with fixed inputs/configuration/environment/code |
| Protected/invalid CLI guards | `--mode protected` rejected EDA exposure; invalid window, raw-output path and input-manifest overwrite attempts also returned exit 2 without changing completed outputs | Protected future-cohort software path additionally passes independent fresh synthetic-fixture checks; no current well declared fresh |
| Root independent artifact audit | Well/instance partitions disjoint; all 32,197 normalized rows finite; training means zero and population std zero or one; all window spans 59 elapsed seconds | Correlated windows are not independent observations; finite imputations are not sufficient-evidence claims |
| Independent numerical reconciliation | Root and reviewer separately reconstructed first/middle/last windows of all 14 included instances: 42 windows and 5,040 retained feature comparisons matched tolerances | Calculations reread originals; independent trend reference uses NumPy least squares, not implementation aggregation |
| Independent QA test run | **67 passed in 7.09 seconds**, zero failed/skipped: 20 implementation + 47 QA cases | Causality, grouping, missingness, label handling, fit isolation, protected guards, malformed artifacts and public imports |
| Final regression | **141 passed in 7.04 seconds**, zero failed/skipped: prior 74 + new 67 | Data/EDA/preprocessing checks only; no detector quality, application, end-to-end or deployment evaluation |
| Source and artifact provenance | All 23 raw SHA-256s remain unchanged; saved implementation/input/dependency/artifact hashes and split/state fingerprints independently reconciled | Near-duplicate subsequences and undocumented relationships remain wider-cohort limitations |
| Final repository/dependency audit | PASS: 103 Git-visible files, 164 valid local links, nine strict JSON/notebook files, 11 new Python sources compiled and 54 unique installed dependency pins matched | All 31 original files and five generated local artifacts ignored; prior data/EDA sources, reports and pins unchanged; application and detector-training directories remain placeholders |
| Dependency/whitespace checks | `pip check`: no broken requirements; `git diff --check`: exit 0; separate UTF-8/newline/whitespace audit passed for tracked and new text files | LF-to-CRLF Git notices only; no commit was made |

Full regression command: `.venv/Scripts/python.exe -m pytest tests/data tests/qa tests/test_data_pipeline.py -q -p no:cacheprovider --basetemp <unique-workspace-temp-path> --tb=short`. Fixture ACL restrictions in the sandbox were resolved by narrow execution escalation. Pydantic was installed into `.venv` with prior dependency constraints preserved; its resolved additions are pinned separately. No application service was installed or started.

Resolved review findings: derive real well/origin/event/source identity from the pinned original path rather than trust mutable manifest fields; validate persisted split relationships beyond a checksum; remove a circular public import; verify eligible endpoint support in protected mode. The loader parses the same verified bytes to avoid a second unverified read. No unresolved Phase 3 software blocker remains. CLI publication is atomic per file; summary hashes must identify a completed artifact set after any interrupted run.

## Phase 4 deliverables and verified results

The orchestrator delegated model implementation and its tests/artifacts to `ml_engineer`, and independent experimental tests/review to `qa_reviewer`. Root retained the fixed protocol, dependencies, shared documentation and integration. Disjoint ownership was maintained; both agents returned ownership after review. User authorization superseded the earlier no-training gate for this bounded baseline experiment only.

Delivered:

- [Training entry point](../ml/train_baseline.py), [evaluation and temporal alarm accounting](../ml/evaluate.py) and [27 implementation tests](../tests/test_training.py).
- [46 independent experimental tests](../tests/qa/test_baseline_integrity.py) and [review](reviews/PHASE_4.md).
- [Frozen experiment protocol](../reports/baseline/PROTOCOL.md), [results and charts](../reports/baseline/README.md), [exact metrics](../reports/baseline/metrics.json), comparison/minority/failure/PR-point CSVs, [experiment manifest](../reports/baseline/experiment_manifest.json) and [repeat verification](../reports/baseline/verification.json).
- [Pinned baseline dependencies](../requirements-baseline.txt). Trusted local model bundle, copied preprocessing/split and full validation predictions remain ignored under `ml/artifacts/baseline/` and `ml/runs/baseline/`.

Final run: `d8386c526a40f56133b5`. Frozen split fingerprint: `643ecb9867ceaf6daff093f11a2e1b0a2b3066cbe2ce614b4ad1ecf81ff82062`. Dataset pin, source selection, Phase 3 windows, 120 retained features and preprocessing statistics are unchanged. Python 3.13.3, scikit-learn 1.9.1, seed 42 and single-thread fitting were used; all installed versions, code/base revision, input hashes, fitted parameters and split identifiers are recorded in the manifest. Python 3.11 compatibility was considered in dependency selection but that runtime was not executed.

The fixed task is binary normal/undesirable detection. Eligible train support is 7,649 windows (3,541 normal, 4,108 abnormal); validation is the identical 16,518 windows for every model (7,724 normal, 8,794 abnormal), across three real source instances/published well IDs. Training abnormal families are 3/4/5/7; validation families are 2/8, both unseen in training. This is a cross-family development diagnostic, not a supported closed-set event classifier. Simulated/drawn validation support is zero and metrics are explicitly null. No test rows entered fitting, prediction, metrics or selection; whole-file integrity hashes do not constitute test evaluation.

Always-normal is a constant reference; train-majority chooses always-abnormal using training labels only. Logistic Regression uses fixed C=1, liblinear L2, class weights normal:1/abnormal:2, max_iter=2000 and score threshold 0.5. Isolation Forest uses 200 trees, max_samples=256 and contamination=0.05, fitting only the 3,541 known-normal train windows. Its score threshold comes from the fitted training offset. Shared preprocessing was fitted on all train endpoints, including abnormal/unknown labels; the entire Isolation Forest pipeline is not normal-only fitted. There was no hyperparameter search or validation threshold selection. Scores remain uncalibrated.

| Model | Precision | Recall | F1 | Average precision (AP) | Trapezoidal PR-AUC | Confusion matrix `[[TN,FP],[FN,TP]]` |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Always normal | undefined | 0 | 0 | 0.532388909 | 0.766194455 | `[[7724,0],[8794,0]]` |
| Train majority | 0.532388909 | 1 | 0.694848293 | 0.532388909 | 0.766194455 | `[[0,7724],[0,8794]]` |
| Logistic Regression | 0.956609485 | 0.539003866 | 0.689504691 | 0.935984905 | 0.935969617 | `[[7509,215],[4054,4740]]` |
| Isolation Forest | 0.535729516 | 1 | 0.697687334 | 0.735504085 | 0.735485774 | `[[103,7621],[0,8794]]` |

Values above are rounded; the linked JSON contains full-precision values and denominators. AP and trapezoidal area are distinct: constant-score AP equals prevalence, while linear interpolation yields a larger area without ranking ability. Confusion plots use a common count scale; PR plots show step curves and fixed operating points.

Failure analysis: Logistic Regression detects 135/152 minority-family-2 windows (recall 0.888157895) and 4,605/8,642 family-8 windows (0.532862763), with one source/well per family. Its 4,054 misses are dominated by family 8. All 215 false positives occur on WELL-00011 and cover every eligible normal endpoint on that well. Isolation Forest detects all abnormal windows but falsely flags 7,621/7,724 normal windows. Twenty-one deterministic failure examples retain source timestamps/scores; no physical cause is inferred. Other event families have no validation support.

Offline temporal accounting covers 175,818 seconds (48.838333333 hours), including 77,260 normal seconds (21.461111111 hours), 87,935 abnormal and 10,623 unknown. Held decisions are bounded by the next endpoint, source end and raw gaps. Unknown target labels preserve prediction episode continuity; unavailable inputs and coverage boundaries censor onsets.

| Model | Confirmed false onsets | Per covered replay hour | Per normal hour | Normal alarm occupancy |
| --- | ---: | ---: | ---: | ---: |
| Always normal | 0 | 0 | 0 | 0% |
| Train majority | 0 | 0 | 0 | 100% |
| Logistic Regression | 0 | 0 | 0 | 2.794460264% |
| Isolation Forest | 5 | 0.102378596 | 0.232979550 | 98.666839244% |

Zero confirmed new false onsets does not mean zero false alarms: Logistic Regression's initial positive episode is censored, yet it alarms for 2,159 normal seconds. Always-abnormal has three censored initial starts and occupies all normal time. These are offline source-time diagnostics, not an executed application replay.

| Verification | Actual outcome | Scope / limitation |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m ml.train_baseline` | Final fixed run completed; Logistic Regression converged in 10 iterations | No tuning, advanced model, test inference or canonical API prediction produced |
| Two consecutive final runs | **14 report/model/prediction artifacts byte-identical**; recorded hashes independently reconciled | Same pinned inputs, code, parameters and environment; no cross-platform bitwise claim |
| New implementation and independent QA tests | **73 passed in 6.53 seconds**, zero failed/skipped: 27 implementation + 46 QA | Split/fit isolation, target consistency, absent support, ranking metrics, temporal exposure, censoring and abstention |
| Root final regression | **214 passed in 15.19 seconds**, zero failed/skipped | All prior 141 tests plus 73 new cases; no application/end-to-end/deployment tests |
| Independent actual-output audit | All 70,332 prediction rows, exact fit IDs, pooled/source/family metrics, episode counts, exposure and 21 failure examples reconciled | AP independently reconstructed within `1e-15`; no test outcomes read |
| Saved-model and input integrity | Reloaded scores/decisions exact; all 23 original Parquet hashes and frozen processed inputs unchanged | Estimator parameters, 120-feature schema, protocol/code/dependency/artifact hashes verified |
| Visual review | Both final figures inspected by reviewer; final PR also inspected by model owner | No chart-derived threshold selection |
| Root final repository/provenance audit | PASS: 120 Git-visible files, 110 text files, 199 valid local links, 12 strict JSON/notebook files, seven TOML files, four new Python syntax checks and 60 installed dependency pins matched | All 14 final artifact hashes matched; 31 original files and five final model/prediction artifacts remain ignored; prior Phase 1-3 code/data reports/manifests/pins unchanged |
| Dependency and whitespace checks | `pip check`: no broken requirements; `git diff --check`: exit 0; separate UTF-8/newline/whitespace audit passed | Git emitted LF-to-CRLF notices only; no commit made |

Full regression command: `.venv/Scripts/python.exe -m pytest tests/data tests/qa tests/test_data_pipeline.py tests/test_training.py -q -p no:cacheprovider --basetemp <unique-workspace-temp-path> --tb=short`. Root used `.local/pytest-phase4-<UUID>` and narrow execution escalation for the existing Windows fixture ACL restriction. Dependency installation also required narrow network escalation. No services were installed or started.

QA resolved four defects before final delivery: inconsistent target/eligibility context, overlapping decision-hold exposure, missing episode censoring across raw gaps, and estimator calls on entirely unavailable validation inputs. No unresolved software blocker remains. The five Phase 2 hypotheses were not executed as controlled ablations. Binary baseline scores are not drop-in canonical event-family API predictions; no shared API contract changed.

**Readiness:** the reproducible software baseline is complete and suitable for further explicitly approved experiments. Neither fitted detector is accepted for monitoring: Logistic Regression misses about 46.1% of abnormal windows; Isolation Forest is close to always-alarm. Protected data, independent family/group support and a declared recall/false-alarm acceptance policy remain necessary. No post-hoc threshold or performance target was invented to pass this gate.

## Phase 5 deliverables and verified results

The user authorized bounded model experimentation, threshold selection, complete inference artifacts and one selected-model test evaluation. Root assigned ML implementation to `ml_engineer`, independent feature review to `data_engineer`, and evaluation integrity to `qa_reviewer`, with disjoint writable paths. Root retained protocol, dependencies, documentation/integration and the exact-selection test release. All agents returned ownership. Previous Phase 4 no-test restrictions were superseded only for this reviewed one-shot diagnostic evaluation.

Delivered:

- [Bounded search and test gate](../ml/training/phase5.py), [complete binary inference interface](../ml/predict.py), [ten implementation tests](../tests/ml/test_model_selection.py), [six feature tests](../tests/data/test_phase5_features.py) and [79 independent integrity tests](../tests/qa/test_model_selection_integrity.py).
- [Fourteen-row model comparison](../reports/model_comparison.csv), [final evaluation](../reports/final_evaluation.md), [model card](MODEL_CARD.md), [prefit protocol](../reports/experiments/PROTOCOL.md), [search metadata](../reports/experiments/search.json), all candidate thresholds/validation metrics and saved test evidence.
- [Feature review](reviews/PHASE_5_FEATURES.md), [experimental review](reviews/PHASE_5.md), [candidate reload verification](../reports/experiments/verification.json), [root integration evidence](../reports/model_selection_verification.json) and [pinned model dependencies](../requirements-models.txt).
- Ignored `ml/artifacts/phase5/` contains exactly eight fit checkpoints and the selected full bundle; `ml/runs/phase5/` contains candidate models and validation/test predictions. Raw and Phase 3/4 artifacts remain unchanged.

Eight actual boosted fits were fixed before results: CatBoost and XGBoost, depths 3/6 crossed with learning rates 0.05/0.1, 200 trees, positive weight 2, seed 42, one CPU training thread. Four original Phase 4 operating points remain comparison references; saved LR/IF estimators add two validation-retuned candidates without refitting. Search considered 1,481 deduplicated thresholds across ten learned candidates. Each threshold maximizes recall subject to <=5% exact normal-time alarm occupancy, with deterministic occupancy/threshold ties; model ranking uses recall, then AP, lower occupancy and stable ID. The 5% cap is an explicitly exploratory engineering choice, not an operational acceptance requirement. No extra seeds, early stopping, feature changes or adaptive search extension.

Selected version: **`oilwell-binary-phase5-c4e1835a82620306778a`**, saved Logistic Regression with threshold **`1.1881945293311268e-14`** and `>=` comparison. Preserve the exact scientific notation. Frozen selection SHA-256: `dfbe88250db8808d58730ab6f0010da3c548cb4b1c26715ba4a4b78057e7130b`. Preprocessing remains unchanged; the split fingerprint remains `643ecb9867ceaf6daff093f11a2e1b0a2b3066cbe2ce614b4ad1ecf81ff82062`. The original preprocessor fingerprint is separately recorded in the bundle. This is internal binary inference, not a canonical event-family API prediction.

| Candidate / partition | Precision | Recall | F1 | AP | Trapezoidal PR-AUC | Normal alarm occupancy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original LR / validation | 0.956609485 | 0.539003866 | 0.689504691 | 0.935984905 | 0.935969617 | 2.794460% |
| Best-recall CatBoost d6, lr .05 / validation | 0.898345154 | 0.216056402 | 0.348336236 | 0.687715990 | 0.676855585 | 2.794460% |
| Best-recall XGBoost d3, lr .05 / validation | 1 | 0.150216056 | 0.261196243 | 0.668165937 | 0.661225279 | 0% |
| Retuned IF / validation | 0.873136915 | 0.286445304 | 0.431372549 | 0.735504085 | 0.735485774 | 4.737251% |
| Selected LR / validation | 0.957408653 | 0.971344098 | 0.964326033 | 0.935984905 | 0.935969617 | 4.930106% |
| Selected LR / once-scored test | 0.567320261 | 1 | 0.723936614 | 0.452854833 | 0.451901434 | **100%** |

Validation confusion is `[[7344,380],[252,8542]]` over the same 16,518 eligible real endpoints. It detects 145/152 family-2 and 8,397/8,642 family-8 windows. All 215 normal WELL-00011 windows and 165 WELL-00006 windows are false positives. The selected threshold yields 40 confirmed false onsets, 0.819028768 per covered replay hour or 1.863836397 per normal hour. Alarmed normal exposure is 3,809/77,260 seconds. Validation now participated in selection, so its winning result is optimistic and cannot establish acceptance.

After independent pre-test approval and 309 passing tests, root created [TEST_RELEASE.json](../reports/experiments/TEST_RELEASE.json) for that exact selection. The [exclusive test journal](../reports/experiments/test_access.json) started before any test-row read and completed with **one attempt**. Only the selected bundle was scored. Test confusion is `[[0,1324],[0,1736]]` over 3,060 eligible endpoints; another 1,420 unknown endpoints retain predictions for continuity. Four sources belong to two published well IDs. Families 1/4/6 have 962/706/68 detected windows respectively, but every normal window is a false positive. All 13,251 normal seconds are alarmed, within 44,777 covered seconds (12.438055556 hours). Zero confirmed false onsets reflect four censored initial episodes, not absence of false alarms. No model, threshold or feature policy changed after this failure.

The independent feature review found 45 train-constant retained columns, one to 20 observed retained sensors in train windows versus five to 18 in validation, and substantial regime/missingness shortcuts. Multiclass fitting was assessed as unsupported because train families 3/4/5/7 and validation families 2/8 are disjoint. Synthetic/drawn holdout support is zero; metrics remain null. Calibration was deferred because the three validation groups do not support a representative separate calibration assessment; the LR score remains uncalibrated. Validation Brier/log loss are 0.256011391 / 4.718590379; test 0.356532001 / 1.575638820. LSTM/1D-CNN were considered and deferred: sequence benefit and adequate independent support were not established. No Phase 2 controlled ablation was claimed complete.

Selected LR validation latency: single feature-to-score wrapper p50/p95 3.588300/4.230460 ms; batch 1,024 p50/p95 3.823200/4.346775 ms (267,838 rows/s at the median). Raw 60-row sensor window through features, imputation, scaling and prediction: 6.993650/8.761235 ms. Five warmups and 50 single/window or ten batch repetitions were used; loading/network/backend costs are excluded. Hardware: Windows AMD64, Intel64 Family 6 Model 154 Stepping 3, 12 logical CPUs. Python 3.13.3, XGBoost 3.2.0 and CatBoost 1.2.10; 65 pinned package versions matched. XGBoost 3.4.1 was initially installed then replaced before fitting because official metadata requires Python >=3.12; 3.2.0 declares >=3.10. Python 3.11 compatibility was considered but that runtime was not executed.

**Recorded protocol deviation:** CatBoost training used one thread, but its native prediction default `thread_count=-1` was not explicitly overridden. CatBoost inference timings are not a controlled single-thread comparison. This was identified after the test gate began; frozen code/results were preserved. Latency did not select the model, and selected LR timing is unaffected. No post-test rerun was performed to conceal or correct this deviation.

| Verification / command | Actual result | Scope / limitation |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m ml.training.phase5 search` | Eight actual fits saved; ten learned candidates and four fixed references reported | Initial report assembly stopped on tiny LR floating differences; resumed using all eight checkpoints, with no extra fits |
| Numerical compatibility correction | Nine saved-baseline LR scores differed by <=3.1225e-17 under new wrapper; explicit atol=1e-14, rtol=0 accepted before selection | Canonical wrapper scores used for retuned LR; original baseline metrics untouched; no parameter/criterion change |
| Independent feature checks | **6 passed in 3.01 seconds**; train/validation-only audit of 27,717 endpoints and frozen hashes | No test rows inspected in feature review |
| Owner + QA pre-test checks | **89 passed in 4.16 seconds**: ten implementation and 79 independent cases | Thresholds, exposure, score boundary, causal inference, artifact tampering, exact cohort and fail-closed journal behavior |
| Root full regression | **309 passed in 12.31 seconds**, zero failed/skipped | Prior 214 plus new 95; no application/end-to-end/deployment tests |
| Pre-test actual QA | All 175,830 prediction rows, 17,583 normal weights and 1,481 thresholds independently reconciled; selection, confusion/AP/area, temporal metrics and hashes match | Reviewer approved exact selection before root release |
| Reload and raw-input equivalence | All ten same-batch candidate reload scores/decisions exact; root raw-input inference decisions/timestamps exact on all 17,583 validation endpoints | Raw score arithmetic drift <=3.1086244689504383e-15, within atol 1e-14, rtol 0; not claimed bitwise identical across batch layouts |
| `.venv/Scripts/python.exe -m ml.training.phase5 test-once` | Root command exit 0; journal COMPLETE, attempts=1; 4,480 saved predictions | No other model test prediction, test tuning, benchmark rerun or second inference |
| Independent saved-test audit | All 4,480 rows, 3,060 eligible labels, all metrics/slices, exposure and three failure examples reconciled; all 23 raw hashes and locked code/bundle hashes unchanged | Zero estimator calls in this audit; model remains rejected for monitoring |
| Final repository/provenance audit | PASS: 144 Git-visible files, 134 text files, 262 local links, 20 strict JSON/notebook files, seven TOML files, five new Python syntax checks and 65 installed dependency pins | Frozen selection/code/bundle/test hashes match; all 31 originals and 32 Phase 5 local artifacts ignored; prior phase artifacts/pins unchanged; backend/frontend/LLM remain placeholders |
| Dependency and text checks | `pip check`: no broken requirements; `git diff --check`: exit 0; UTF-8/newlines/whitespace passed on tracked and new text | Git emitted line-ending notices only; no commit made |

Root full-suite command: `.venv/Scripts/python.exe -m pytest tests/data tests/qa tests/ml tests/test_data_pipeline.py tests/test_training.py -q -p no:cacheprovider --basetemp <workspace>/.local/pytest-phase5-<UUID> --tb=short`. Narrow execution escalation addressed the known fixture ACL restriction; dependency resolution/installation used narrow network escalation. No application service started. No commit made.

**Outcome:** selection and reproducible inference deliverables are complete; monitoring acceptance is rejected. The validation-selected threshold fails its false-alarm constraint on diagnostic test. Existing EDA exposure and sparse group support further prevent protected generalization claims. Preserve this failed experiment; future work requires a new approved scope and suitable independent cohort, not another choice based on these test outcomes.

## Phase 6 deliverables and verified results

The user authorized backend implementation around the selected artifact. Root assigned API/Pydantic/persistence and component tests to `backend_engineer`, independent API/contract/real-PostgreSQL review to `qa_reviewer`, and retained `backend/app/inference.py`, `backend/app/registry.py`, real-artifact integration tests, dependencies, contract decisions and local service orchestration. Ownership was disjoint and returned at handoff. No later component was started.

Delivered:

- [FastAPI application](../backend/app/main.py), [typed schemas](../backend/app/schemas.py), bounded settings/pagination, structured errors and JSON logging.
- [Frozen inference adapter](../backend/app/inference.py) and [immutable sensor-only registry](../backend/app/registry.py). The exact selected artifact is loaded once at lifespan startup; request handlers call the existing frozen `ml.predict` pipeline without retraining, recalibration or threshold changes.
- [PostgreSQL repository](../backend/app/repository.py) and [versioned migration](../backend/migrations/001_diagnostic_predictions.sql). Prediction, idempotency identity and optional diagnostic alert commit atomically; same-key concurrency creates one result, conflicts return 409, and failures roll back.
- [Diagnostic JSON Schema](contracts/diagnostic_prediction.schema.json), [OpenAPI export](openapi.json), updated [API contract](API_CONTRACT.md), [startup/examples](BACKEND.md), [pinned backend dependencies](../requirements-backend.txt) and local launcher/database helpers.
- Component/contract/independent tests plus [four real-model/PostgreSQL integration tests](../tests/integration/test_frozen_api.py), [independent review](reviews/PHASE_6.md), [live HTTP smoke](../reports/backend_smoke.json) and [verification record](../reports/backend_verification.json).

The six implemented routes are `GET /health`, `GET /wells`, `GET /wells/{id}/telemetry`, `POST /predict`, `GET /alerts` and `GET /models/info`. `/docs` and `/openapi.json` are available. They use the additive **diagnostic-1.0.0** contract: binary `normal`/`undesirable_event`/`unknown`, selected-class confidence separately from uncalibrated abnormal score, exact model version/threshold, causal evidence, data/model hashes and separate source/processing times. Every result declares diagnostic status and rejected monitoring acceptance. Canonical event-family v1.0 schema/example bytes remain unchanged; no event-family label, replay session or episode lifecycle is invented.

Serving includes exactly ten approved real train/validation instances/well IDs. Source startup verifies original byte hashes, registry and preprocessing and decodes only 27 sensor columns. All four test sources and nine excluded synthetic sources are unregistered; no test window was inferred. Endpoints align to the frozen 60-row window/10-row stride; short prefixes abstain. Optional client samples must exactly match the registered original window; altered values, nulls, timestamps, unknown sensors or label fields cannot obtain original provenance. Missing retained evidence abstains without calling the estimator. Source timezone remains unverified and explicitly identified.

The selected version remains `oilwell-binary-phase5-c4e1835a82620306778a`, threshold `1.1881945293311268e-14`. Alert rows are per-prediction **diagnostic detections**, not ongoing operational episodes. Input body bytes, telemetry pages and inference concurrency are bounded. Errors are sanitized, include request IDs and never expose stack traces/database URLs/raw sensor payloads. Missing model/data/database leaves docs/health inspectable and affected operations return 503; production never substitutes in-memory persistence or a fake model.

PostgreSQL **18.3** was already installed. Root initialized an isolated workspace cluster under ignored `.local/phase6/postgres`, listening only at `127.0.0.1:55436`, with generated local credentials and separate app, backend-test, QA and root-integration databases. No existing system database was used. The API acceptance process remains available at **http://127.0.0.1:8000**, with Swagger at **http://127.0.0.1:8000/docs**. Launch/stop instructions and credential handling are in BACKEND.md; local runtime configuration/logs/data are ignored. No public deployment or authentication rollout was performed.

| Verification / command | Actual outcome | Scope / limitation |
| --- | --- | --- |
| Backend-owner tests | **30 passed in 3.27 seconds**, zero failed/skipped, including five real PostgreSQL cases | Typed API fixtures, caps/errors/logs/idempotency, normal/abstention behavior, transaction rollback and persistence |
| Independent QA/contract tests | **86 passed in 6.36 seconds**, zero failed/skipped: 51 contract and 35 API/registry/database cases | Schema/OpenAPI drift, adversarial inputs/errors, no-fit guard, test-source exclusion, actual PostgreSQL concurrent requests/repository restart/rollback/SQL parameter handling |
| Root frozen-artifact integration | **4 passed in 5.13 seconds**, zero failed/skipped | Real selected-model API output matches saved first-window predictions of all three validation sources within atol 1e-14; decisions exact; original samples validated, PostgreSQL payload/alert linkage and new app startup retain exact idempotent response |
| Root full regression | **429 passed in 29.51 seconds**, zero failed/skipped | Prior 309 plus 120 Phase 6 cases; all three dedicated test DSNs and frozen QA flag enabled; no hidden database skips |
| Dependency warning | One upstream Starlette TestClient/httpx deprecation warning | No failed assertion; versions remain pinned, no compatibility change made solely to hide the warning |
| Actual loopback HTTP acceptance | All six endpoints and `/docs` returned 200; invalid Boolean endpoint input returned structured 422 | HTTP over a real Uvicorn listener, not only ASGI fixtures; Swagger HTML contains its UI bundle |
| Actual inference/persistence smoke | Registered validation endpoint 59 produced `undesirable_event`, abnormal score/confidence `0.9999803020883076`; one linked PostgreSQL alert; repeated same key returned exactly equal JSON payload | Actual model score, not detection-quality evidence; original selected model remains rejected for monitoring |
| SQL/log reconciliation | Stored JSON payload equals HTTP response; one alert linked; prediction/alert/idempotent-replay JSON log events observed without raw samples or credentials | Diagnostic persistence only; no claim of durable replay worker or operational episode handling |
| Immutable source/model/test audit | All 31 originals and selected code/bundle/preprocessor hashes match; Phase 5 journal COMPLETE with one attempt; saved test hashes unchanged | Source IDs/byte hashes may be inspected, but no test sensor/label records were inferred for serving checks |
| Final repository/contract audit | PASS: 169 Git-visible files, 159 text files, 292 local links, 24 strict JSON/notebook files, seven TOML files and 17 new Python syntax checks | Pydantic JSON Schema and complete runtime OpenAPI match exports; all 79 dependency pins match; prior model/data artifacts unchanged; credentials/DB/logs ignored; frontend/LLM remain placeholders |
| Dependency/text checks | `pip check`: no broken requirements; `git diff --check`: exit 0; UTF-8/newline/whitespace checks passed | Git emitted a line-ending notice only; no commit made |

The full-suite command and environment setup are documented in BACKEND.md: load the three isolated DSNs from ignored local configuration, enable `OILWELL_RUN_FROZEN_QA=1`, then run `pytest tests -q -p no:cacheprovider --tb=short --basetemp <unique-workspace-temp-path>`. Narrow execution escalation resolved the known Windows pytest fixture ACL and PostgreSQL restricted-token startup constraints; dependency installation also used narrow network escalation. A first local-helper status probe could not inspect the elevated server process and attempted a redundant start, which failed without changing the running cluster. The helper now verifies the authenticated server data directory before deciding to start; its successful repeat is recorded. No database/source cleanup outside owned fixture rows occurred.

Integrated review fixes enforce full-window/evidence/source-time consistency and strict probability/Boolean response fields, revalidate copied Pydantic instances before persistence, and enable structured INFO logs under normal Uvicorn logging. No unresolved API/contract/inference integrity blocker remains. Backend dependencies are pinned separately, preserving all 65 previous pins; 79 installed package pins match in total. Python 3.13.3 was executed; the Python 3.11+ target was not separately runtime-tested.

**Outcome:** all Phase 6 acceptance criteria are met for the local diagnostic service. This does not reverse the model's failed monitoring acceptance. Continuous replay/pause/resume/SSE, ongoing alert episodes, frontend, copilot, public deployment and fresh-model/data work remain outside this phase. No retraining or test reevaluation was performed; stop after Phase 6.

## Phase 7 deliverables and verified results

The user explicitly authorized historical replay. Root delegated backend implementation to `backend_engineer`, frozen offline/replay consistency tests to `ml_engineer`, and independent replay/contract correctness review to `qa_reviewer`. Root retained ML-backend integration, contracts/exports, demo and final regression. Ownership remained disjoint, including explicitly transferred narrow compatibility assertions; all agents returned ownership at handoff. No frontend/copilot/model research was started.

Delivered:

- [Replay service/worker/API](../backend/app/replay.py), [PostgreSQL replay repository](../backend/app/replay_repository.py), [typed replay schemas](../backend/app/replay_schemas.py), [migration 002](../backend/migrations/002_historical_replay.sql), and application lifespan integration.
- [Replay guide](REPLAY.md), additive contract/OpenAPI exports, [prediction envelope schema](contracts/replay_prediction.schema.json), [snapshot schema](contracts/replay_snapshot.schema.json), [event schema](contracts/replay_event.schema.json) and ADR-044..048.
- [Reproducible HTTP demo](../scripts/replay_demo.py), [chart generator](../scripts/plot_replay_demo.py), [actual demo report/chart](../reports/replay/README.md), [JSON evidence](../reports/replay/demo.json), [restart/stop smoke](../reports/replay/restart_smoke.json) and [verification record](../reports/replay/verification.json).
- Backend, ML and independent QA tests, [ML review](reviews/PHASE_7_ML.md), and [QA review](reviews/PHASE_7.md).

The additive `/replays` API supports choosing a registered source/range, start/pause/resume/stop, speed 0.1..20, snapshots, bounded history/predictions/alerts and SSE. The `diagnostic-replay-1.0.0` envelope marks simulated historical playback while preserving real source origin and the unchanged diagnostic inner prediction. The original diagnostic and canonical event-family schemas remain byte-identical. No event-family output or operational reliability is implied.

One transaction commits an original sensor row, any prediction, episode update, cursor and ordered events. PostgreSQL locks and idempotent commands prevent concurrent advancement/duplicate episode openings; rollback preserves the last committed cursor. Resume and worker restart reuse persisted progress. A dedicated application-lifespan worker thread adapts the earlier separate-process plan for this local MVP. REST controls plus unidirectional SSE avoid unnecessary WebSocket commands. Clients reconnect with durable IDs and deduplicate at-least-once delivery; terminal streams drain then close.

Causal replay starts with empty history and requires 60 replayed observations on the original `59+10*k` endpoint grid. The unchanged adapter sees only trailing sensor rows through the current timestamp. Registered sources remain train/validation only. No `class`, auxiliary `state`, future data or test source enters inference. The separate demo reads original labels only after completion, checks source bytes and joins retrospective results locally.

The fixed episode rule opens once on a usable positive, updates ongoing positives, resolves on usable normal and preserves an open episode on abstention. This is diagnostic no-dwell deduplication at the exact selected threshold, not improved model quality. Episode state is captured at each prediction; later outcomes do not rewrite evidence. Replay alerts are scoped under `/replays/{id}/alerts`; Phase 6 `/alerts` retains its original synchronous meaning.

| Verification | Actual result | Scope / limitation |
| --- | --- | --- |
| Backend owner | 31 passed in 7.17 s: six new replay cases plus 25 prior API cases | Includes actual PostgreSQL rollback, concurrent processing and repository restart |
| Independent ML | 11 passed in 7.75 s | All 21 demo scores/decisions at three configured speeds; all 260 rows ordered; future perturbation, sensor-only inputs, unaligned-start warmup and abstention; deterministic fixture scheduling, not throughput benchmark |
| Independent QA | 63 combined cases passed in 11.77 s, followed by expanded 52-case contract file in 1.10 s | 65 new QA/contract cases total plus one previous compatibility case; actual PostgreSQL 18.3 thread restart, partial event rollback, competing workers, SSE/reconnect/error sanitization, strict flags and immutable evidence |
| Root full regression | **511 passed in 65.46 s**, zero failed/skipped | Previous 429 + 82 new cases; all three dedicated test databases and frozen QA checks enabled; one pre-existing Starlette/httpx deprecation warning |
| Actual HTTP/PostgreSQL demo | Completed 260 rows, 21 predictions, 306 events | Pause stayed fixed; speed changes/resume completed; create retry exact; SSE reconnected to exact persisted suffix |
| Offline agreement | All 21 live scores within absolute 1e-14 of frozen saved validation; every decision identical | No fitting, threshold changes, test re-inference or new benchmark claim |
| Actual process restart and stop | Prior snapshot and all 21 prediction IDs unchanged after restarting owned API; separate replay stopped at source position 5603 and stayed fixed | Health/docs 200; ahead SSE cursor structured 400 |
| Source/model integrity | All 130 pre-phase frozen data/model/evaluation/canonical files unchanged; QA separately checks 31 originals and one-attempt test journal | No original Parquet or model/preprocessor/inference binary/code edits |
| Contract integration | Current runtime OpenAPI equals exported OpenAPI and actual HTTP OpenAPI; three replay JSON Schemas equal Pydantic exports | Separate additive version; prior schemas preserved |
| Final static audit | 190 Git-visible files, 179 text files, 326 local links, 53 Python AST checks, 30 strict JSON/notebook files and seven TOML files passed; `git diff --check` exit 0 | Credentials/runtime/model binaries ignored; no dependency changes; Git emitted only a line-ending notice |

Actual validation demonstration: WELL-00011 rows 5600..5859, original timestamps 2014-05-30 10:05:23..10:09:42 (timezone unverified). Normal class 0 changes to transient 102 at position 5759 / 10:08:02. First alert opens at 5659 / 10:06:22 while normal; it resolves at 5809 / 10:08:52 despite the event, then reopens at 5849 / 10:09:32. There are two openings, fifteen updates and one resolution, not eighteen new alerts. Ten normal prediction endpoints are all false positives; four of eleven transient endpoints are false negatives. This intentionally shows the rejected model's failures.

The root full-suite command is the same documented setup as BACKEND.md: load the three ignored dedicated test DSNs, enable `OILWELL_RUN_FROZEN_QA=1`, then `pytest tests -q -p no:cacheprovider --tb=short --basetemp <unique-workspace-directory>`. The initial restricted-token attempt encountered Windows `WinError 5` in temporary pytest fixtures and cleanup; a narrow approved execution escalation reran it successfully. This was an execution-environment issue, not a claim that the initial run passed. No dependency changes or commit were made.

Root launched the Phase 7 API on **http://127.0.0.1:8001**, restarted that owned process with final code, and retained the completed demo in the workspace PostgreSQL on loopback 55436. The previous Phase 6 process on 8000 was not stopped. Local credentials, logs and PostgreSQL files remain ignored. No public exposure was added.

Remaining local limitations: persisted UTC deadlines provide best-effort pacing; clock changes and per-row PostgreSQL/inference overhead affect achieved speed. The observed run took 67.342806 seconds including controls despite requested 20x. Source ordering/features are unaffected. Each session caps at one million rows and stream/pages use bounded batches, but completed-session count/disk history have no automatic pruning or expiry. No 410 expired-history behavior is implemented. The selected detector remains rejected; no protected cohort, accepted model, frontend, copilot or deployment is implied.

**Outcome:** Phase 7 acceptance is met for historical diagnostic replay. Stop here; later work requires explicit user authorization.

## Blockers and unresolved evidence

No selected-model or diagnostic-API integrity blocker remains for the completed Phases 1-7; CatBoost inference timing has the explicitly recorded thread-control deviation. The original roadmap's broader M1 modeling-cohort/evaluation acceptance remains unresolved: most selected undesirable families occur in only one real well group, and no selected real row contains family 9. The executable split, preprocessing and selected binary artifact support development diagnostics; the selected artifact failed its test false-alarm behavior and remains unaccepted. In addition, the inspected subset cannot supply a pristine, class-supported three-way multiclass evaluation. No protected final-test cohort or accepted monitoring detector exists. Further approved data work must establish sufficient independent real groups and usable label/sensor coverage before generalization claims.

Residual limitations: unknown source timezone and physical-identity equivalence; structural/origin-dependent sensor missingness; initial null target/status labels; absent steady code 7; documentation-versus-file dtype discrepancy; 40 real filename IDs in pinned inventory versus 42 wells in release notes; possible wider-corpus overlaps/near-duplicates and upstream interpolation. Phase 4 measured fixed diagnostic operating points; Phase 5 performed bounded validation selection and one diagnostic test, which failed normal-exposure control. Operational threshold selection, calibration, protected-cohort performance and provider selection remain future decisions.

The independent review prompted two integrated corrections: snapshots and events now expose ongoing alert episodes independently of abstaining predictions, and provider packets explicitly exclude class-bearing source paths/IDs/manifests. Explanation episode evidence is captured at prediction time to exclude future outcomes. See ADR-018/019 and the API contract.

## Next action

**Stop after Phase 7 and wait for user approval.** The local replay API and persisted historical demonstration are available for inspection. Preserve the rejected model's failure disclosure, immutable artifacts and one-attempt test journal. No frontend, copilot, fresh model/data work or public deployment is authorized by this completed phase.
