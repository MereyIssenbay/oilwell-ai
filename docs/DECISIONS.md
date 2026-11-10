# Architecture decision record

Recorded 2026-11-09. These are design decisions, not implementation claims. Revisit decisions with new evidence through the orchestrator; retain the rationale and compatibility implications.

| ID | Decision | Reason and consequence | Status |
| --- | --- | --- | --- |
| ADR-001 | Phase 0 is documentation, contracts, agent configuration and empty scaffolding only | Dataset acquisition and application/ML work require later explicit approval | Accepted |
| ADR-002 | Pin 3W dataset v2.0.0 at `914af287b1cf3e5207dce0da1e9dc08361c9adeb` | Metadata is Parquet with 27 sensors plus `class`/`state`; historical CSV assumptions would produce the wrong adapter. Phase 1 audited 23 byte-preserved files and recorded actual dtype/missingness differences | Accepted; bounded audit complete |
| ADR-003 | Use a modular monolith: FastAPI API plus separate replay-worker process; shared PostgreSQL | Separates scheduling/inference from HTTP without adding Kafka/Redis/microservice deployment overhead. Offline training is a separate command | Accepted |
| ADR-004 | Keep immutable telemetry in local Parquet; store registries/replay/cursors/predictions/events/explanations in PostgreSQL | Small portfolio scope does not need a time-series extension or raw-row duplication. Read bounded file slices; database remains authoritative for replay progress | Accepted |
| ADR-005 | One replay session and one source instance per active session; REST commands and durable SSE | Bounded, reviewable replay/reconnect semantics; sequential IDs and unique persistence keys handle retries. Network delivery is at least once | Accepted |
| ADR-006 | Canonical JSON Schema plus semantic contract now; Pydantic/OpenAPI and generated TypeScript later | One reviewed contract spans ML assembly/backend/frontend. Schema validation alone cannot enforce temporal or registry invariants | Accepted |
| ADR-007 | Start with normal plus two event families chosen after audit | Limits scope to a defensible cohort. Contract lists all classes but model manifest declares actual supported subset. Revise scope if independent support is insufficient | Conditional on M1 |
| ADR-008 | Group by real anonymized well where feasible and preserve entire related source instances before windowing | Prevents overlap/identity leakage. Synthetic/drawn data is optional training-only augmentation; holdout reporting stays real. Do not claim unseen-well performance from instance-only splits | Accepted |
| ADR-009 | Explicit sensor allowlist, excluding `class`, `state`, identifiers, origin and directory labels | Upstream loader can leave `state` in features. Future loader use must be audited for side effects and leakage | Accepted |
| ADR-010 | Map only documented transient labels to event family and evaluate phases separately | Initial classifier predicts event family at window end, not onset phase. Unknown labels stay unknown; do not blindly subtract/modulo 100 | Accepted |
| ADR-011 | Preserve source timestamp and declare `source_naive_assumed_utc` for transport until timezone is verified | No source timezone was established. UTC-tagged source coordinates permit interoperable charts without claiming physical UTC; actual processing time remains real UTC | Accepted; source timezone unresolved |
| ADR-012 | Scikit-learn baseline, then XGBoost; CatBoost and deep models deferred | A shared causal feature pipeline and split enable interpretable comparison. No model score or superiority is assumed in Phase 0 | Accepted |
| ADR-013 | Immutable model/scope/feature/policy versions, confidence calibration state, explicit abstention | Probabilities are model scores, not certainty. Missing/unsupported inputs do not become normal predictions. Alert policy is backend-owned and deterministic | Accepted |
| ADR-014 | Evidence-only copilot with deterministic fallback; provider optional and off by default | The demo remains usable without credentials. Claims cite immutable evidence; LLM output cannot alter event/confidence/status or control equipment | Accepted |
| ADR-015 | Defer ChromaDB until retrieval evaluation establishes a need | Structured sensor/model evidence suffices for initial explanations. A future corpus requires source/version/license boundaries and injection defenses | Accepted |
| ADR-016 | Loopback-only single-user Docker demo; no public deployment in initial scope | Keeps deployment scope explicit. External exposure requires auth, TLS, rate limiting and secret management in a separate accepted decision | Accepted |
| ADR-017 | Six standalone Codex role TOMLs, inherited model, at most three concurrent subagents | Current official configuration supports `agents.enabled` and `agents.max_concurrent_threads_per_session`; root retains integration and assigns disjoint paths. No nested spawning | Accepted; runtime activation not tested |
| ADR-018 | Expose ongoing alert episode state independently of immutable prediction status | An abstention does not resolve an active alert. Snapshots and ordered events preserve continuity; explanation evidence captures only the episode state at prediction time | Accepted after Phase 0 review |
| ADR-019 | Explicit provider evidence allowlist with opaque linkage tokens | Source paths contain event-class directories; sending the whole canonical record would leak ground truth. Exclude label-bearing paths/IDs/manifests and future outcomes | Accepted after Phase 0 review |
| ADR-020 | Phase 1 authorization covers acquisition and audit, not preprocessing or an ML cohort | User approved the bounded task on 2026-11-10. Select one smallest file per available directory/origin stratum plus four new real well IDs; cap at 30 files/100 MiB. Size bias and limited group/phase coverage prevent split/model-scope acceptance | Accepted; 23 files acquired |
| ADR-021 | Preserve measured types, unknown labels and missing sensors unchanged | All selected files have float64 sensors and Int16 labels, unlike documented Float64/Int64. Each real file starts with 3,600 unknown labels; four sensors are entirely missing in the subset. Report discrepancies instead of coercing/filling raw data | Accepted after Phase 1 audit |
| ADR-022 | Verify acquisition with pinned Git blob identity and SHA-256; validate offline | Manifest-backed download and atomic publication protect original bytes. Separate validator checks schema, labels, time, missingness and grouping; report output is restricted to JSON under reports/ | Accepted; independent integrity review passed |

## Configuration evidence

The original project configuration already used the current `agents.enabled` and `agents.max_concurrent_threads_per_session` keys. It was retained and augmented with `features.multi_agent=true`, rather than replaced with older role-registration syntax. Official sources: [subagent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents) and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). The configured limit of three excludes the primary orchestrator. Models inherit session settings; no model availability or price assumptions are embedded in the profiles.

All seven TOML files were parsed with Python `tomllib`, and installed Codex `0.164.0-alpha.11.1` accepted `codex --strict-config app-server --print-startup-config` with exit 0. This confirms configuration loading, not that every role was launched in this existing session. A new session may be required to pick up role/config changes. User-profile temporary-directory/PATH warnings were emitted but did not fail the validation.

## Open decisions and resolution owners

| Question | Resolution gate / owner |
| --- | --- |
| Which two event families and sensor subset have independent real support? | M1 data audit, data engineer + orchestrator |
| What are actual index/timezone, state-code, label-coverage, missingness and overlap properties? | M1 inspected source report; preserve uncertainty where upstream evidence is absent |
| Which causal window, stride, imputation and gap policy is appropriate? | M2 validation-only experiments, ML engineer |
| Is confidence calibration justified and what are alert/dwell/recovery/release budgets? | M2 validation policy, fixed before final test |
| What hardware/resource envelope and event retention meet the local demo objective? | Define before M5 benchmark; verify in M7, backend + QA |
| Which optional LLM provider/model passes grounding checks and budget constraints? | M6; deterministic mode needs no provider decision |
| Is document retrieval or public hosting required? | Outside current MVP; separate scope decision and approval |

Metadata evidence, licensing and caveats are in [DATASET_METADATA.md](DATASET_METADATA.md). Progress and actual verification results are in [PROGRESS.md](PROGRESS.md).
