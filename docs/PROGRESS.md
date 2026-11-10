# Project progress

Updated: 2026-11-10 (Asia/Oral).

## Authorization and status

- **Phase 0: complete.** Architecture, contracts, configuration, scaffolding, static verification and independent review are complete.
- **Phase 1: complete**, authorized and executed on 2026-11-10. Bounded acquisition, inspection, automated validation, provenance documentation and independent integrity review only.
- **Phase 2 EDA: complete**, authorized and executed on 2026-11-10. Actual-data exploration, charts, hypotheses, split recommendation and independent leakage review only. This user request supersedes the original roadmap's Phase 2 model-training schedule. Work stops here; additional acquisition, production preprocessing, training and application implementation require a new approval.
- **Phase 3 preprocessing: complete**, authorized and executed on 2026-11-10. Reusable, deterministic grouped splitting, causal features and train-only preprocessing statistics, with independent leakage review. No model training or additional telemetry acquisition. Current-data partitions remain development diagnostics. Stop here pending the user's next phase approval.
- **Phase 4 baseline: complete**, authorized and executed on 2026-11-10. Naive references, Logistic Regression and Isolation Forest were compared on the unchanged development validation split, with independent experimental review. No test predictions, tuning, additional acquisition or application implementation. The software baseline is reproducible; detector acceptance remains withheld. Stop here pending user approval of further work.

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

## Blockers and unresolved evidence

No software blocker remains for the completed Phases 1-4. The original roadmap's broader M1 modeling-cohort/evaluation acceptance remains unresolved: most selected undesirable families occur in only one real well group, and no selected real row contains family 9. The executable split, preprocessing and fitted binary baselines support development diagnostics; the inspected subset cannot supply a pristine, class-supported three-way multiclass evaluation. No protected final-test cohort or accepted monitoring detector exists. Further approved data work must establish sufficient independent real groups and usable label/sensor coverage before generalization claims.

Residual limitations: unknown source timezone and physical-identity equivalence; structural/origin-dependent sensor missingness; initial null target/status labels; absent steady code 7; documentation-versus-file dtype discrepancy; 40 real filename IDs in pinned inventory versus 42 wells in release notes; possible wider-corpus overlaps/near-duplicates and upstream interpolation. Phase 4 measured fixed diagnostic operating points only. Operational threshold selection, calibration, protected-cohort performance and provider selection remain future decisions.

The independent review prompted two integrated corrections: snapshots and events now expose ongoing alert episodes independently of abstaining predictions, and provider packets explicitly exclude class-bearing source paths/IDs/manifests. Explanation episode evidence is captured at prediction time to exclude future outcomes. See ADR-018/019 and the API contract.

## Next action

**Stop after Phase 4 and wait for the user's approval.** Recommended next scope: establish adequate fresh real groups and event coverage, agree on detection scope and recall/false-alarm criteria, then authorize a separate experiment/calibration plan. Preserve existing split/preprocessing/results and test restrictions. No additional acquisition, XGBoost, application or deployment work is authorized by the completed phase.
