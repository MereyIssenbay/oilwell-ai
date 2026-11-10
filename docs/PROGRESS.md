# Project progress

Updated: 2026-11-10 (Asia/Oral).

## Authorization and status

- **Phase 0: complete.** Architecture, contracts, configuration, scaffolding, static verification and independent review are complete.
- **Phase 1: complete**, authorized and executed on 2026-11-10. Bounded acquisition, inspection, automated validation, provenance documentation and independent integrity review only.
- **Phase 2 EDA: complete**, authorized and executed on 2026-11-10. Actual-data exploration, charts, hypotheses, split recommendation and independent leakage review only. This user request supersedes the original roadmap's Phase 2 model-training schedule. Work stops here; additional acquisition, production preprocessing, training and application implementation require a new approval.

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

## Blockers and unresolved evidence

No blocker remains for the requested Phase 1 acquisition/audit or Phase 2 EDA. The original roadmap's broader M1 modeling-cohort/split acceptance remains unresolved: most selected undesirable families occur in only one real well group, and no selected real row contains family 9. The inspected subset cannot supply a pristine, class-supported three-way multiclass evaluation. No split manifest, final model scope, preprocessing or training was created. Further approved data work must establish sufficient independent real groups and usable label/sensor coverage before model work.

Residual limitations: unknown source timezone and physical-identity equivalence; structural/origin-dependent sensor missingness; initial null target/status labels; absent steady code 7; documentation-versus-file dtype discrepancy; 40 real filename IDs in pinned inventory versus 42 wells in release notes; possible wider-corpus overlaps/near-duplicates and upstream interpolation. Thresholds, calibration, model performance and provider selection remain future decisions.

The independent review prompted two integrated corrections: snapshots and events now expose ongoing alert episodes independently of abstaining predictions, and provider packets explicitly exclude class-bearing source paths/IDs/manifests. Explanation episode evidence is captured at prediction time to exclude future outcomes. See ADR-018/019 and the API contract.

## Next action

**Stop: Phase 2 is complete. Await the user's next phase approval.** The recommended next scope is cohort/split readiness: select a supportable task, obtain adequate independent real groups if authorized, and freeze disjoint published-well groups plus duplicate/overlap relationships before windows. Reserve fresh real groups for final testing before exploratory access; keep synthetic sources out of primary real validation/test. Only after that gate should a separately authorized modeling phase test small scikit-learn baselines and the five hypotheses before considering XGBoost. No training is authorized by this handoff.
