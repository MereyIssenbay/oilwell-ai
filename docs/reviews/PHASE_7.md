# Phase 7 independent replay review

Reviewed 2026-11-10. The user explicitly authorized historical replay after Phase 6. This review covers the additive diagnostic replay service, contracts and persistence; it does not accept the selected detector for monitoring.

## Result and executed verification

**63 passed in 11.77 seconds**, zero failures/skips, one existing upstream Starlette TestClient/httpx deprecation warning. This comprises 49 new contract cases, 13 new replay/integrity cases and the one narrowly adapted Phase 6 route-presence case. After root exported the three replay schemas, three additional exact schema-drift cases were added: the complete contract file then passed **52 cases in 1.10 seconds**. There are 66 distinct independently checked cases in total; 65 are new and one is the prior compatibility check. PostgreSQL persistence checks ran against the actual isolated QA database on PostgreSQL **18.3**, not an in-memory substitute. The frozen-artifact check hashes bytes only and does not decode or infer on test observations.

Executed from the repository root with `.venv/Scripts/python.exe`, loading only `OILWELL_QA_DATABASE_URL` from the ignored `.local/phase6/runtime.json` configuration before this call:

```python
pytest.main([
    "tests/qa/test_replay_integrity.py",
    "tests/contract/test_replay_contract.py",
    "tests/qa/test_backend_integrity.py::test_startup_docs_openapi_and_diagnostic_identity",
    "-q", "-p", "no:cacheprovider", "--tb=short",
])
```

An earlier 48-case run passed before the additional typed-payload, startup and real worker-restart checks were added. The final 63-case result supersedes that partial run. No result is a throughput benchmark, operational reliability metric or new model-quality evaluation.

## Findings and resolutions

| Severity | Finding | Resolution and regression evidence |
| --- | --- | --- |
| Medium, resolved | The new playback literal initially accepted integer `1` as `simulated_playback=true` | Backend owner added an exact Boolean validator; malformed flag tests now reject numeric aliases and misleading live/monitoring identities |
| Medium, resolved | Initial replay event payloads were untyped dictionaries, and episode envelope semantics allowed missing/inconsistent current-decision state | Backend owner added typed payloads and replay/sequence/episode validators; tests reject extra target/future fields, wrong payload kind, foreign replay IDs, mismatched sequence, future episode timestamps, missing positive episode, normal-with-open-episode and inconsistent status |
| Compatibility, resolved | Existing Phase 6 test required exactly six OpenAPI paths | Root authorized changing only that assertion to require the same six routes as a subset; no previous route requirement was removed |

No remaining replay correctness blocker was observed in the reviewed local MVP scope. Exported replay prediction, snapshot and event schemas pass Draft 2020-12 validation and exactly match their Pydantic definitions. The full repository regression, full OpenAPI comparison and live historical demo remain orchestrator-owned closeout checks, separately reported in progress.

## Independent evidence

| Area | Observed checks | Scope |
| --- | --- | --- |
| Ordering and causal startup | Fixture replay emits each source position once in ascending order; nonzero start 13 produces no inference before 60 replayed rows and first aligned prediction at 79 | Frozen global alignment is `59 + 10*k`; no pre-start warmup observations are supplied |
| Episode policy | Positive opens once, repeated positives update the same episode, abstention preserves it with insufficient-data status, normal resolves, a later positive opens a new episode | Synthetic decision sequence exercises branches honestly; it is not a claim that the selected model follows this sequence |
| Past evidence | Prior prediction episode snapshots retain their original prediction/status after later abstention, recovery and new episode | No later state is retroactively attached to earlier predictions |
| Commands | Pause prevents advancement, resume continues, stop is terminal, stale versions fail 409, same-key retry returns its original response without replaying the command | A repeated historical pause response does not pause the currently resumed session again |
| Binding | Changed source SHA, model version, threshold or preprocessing fingerprint prevents a new cursor/event commit | Original selected model and threshold remain immutable |
| Stream reconnection | Completed-stream reconnect returns exactly the saved suffix after a replay-qualified event ID; reconnect at last event returns empty; foreign, malformed and future cursors fail 400 | SSE is at-least-once delivery; clients deduplicate by replay ID and sequence |
| Stream failure | Injected failure after preflight yields sanitized `stream_error` without a fabricated durable event ID | Client resumes with last received durable event ID; no secret/path marker is exposed |
| Startup failure | Replay repository failure leaves docs accessible, health degraded and replay routes at structured 503 | No silent in-memory production fallback |
| PostgreSQL concurrency | Four competing due-step calls advance exactly one source row and create one prediction/opening | Real row locks and persisted due time, not a fixture lock |
| PostgreSQL atomic rollback | Injected failure after the real cursor UPDATE and first event INSERT rolls back cursor, history, prediction and episode together; retry creates exactly one prediction/opening | Simulates a transaction-stage crash/error, not a complete host/network partition |
| Actual worker restart | A real worker thread commits telemetry, stops, and a newly constructed service/repository/worker continues from the saved PostgreSQL cursor without duplicates | The original event prefix remains exactly equal; no claim of operating-system process-kill testing by this reviewer |
| Immutable sources/artifacts | All 31 original file hashes, selected code/dependency/data artifacts, bundle manifest/model/preprocessor/split and saved test outputs match their frozen hashes | Test access journal remains COMPLETE with one attempt; no new acquisition, fitting, retuning or test inference |
| Compatibility | Original canonical event-family and synchronous diagnostic schema files remain byte-for-byte unchanged | Replay uses a separate `diagnostic-replay-1.0.0` envelope around the original diagnostic prediction |

Each PostgreSQL fixture creates a unique replay/request namespace and deletes only its own replay, event and command rows. An independent post-run query found zero `qa-replay-*` create requests and zero active replay sessions remaining in the dedicated QA database. Credentials were never printed or included in this report.

## Limitations and separate responsibilities

- The actual source registry still serves only approved train/validation real instances; frozen test and excluded synthetic sources are not admitted. Real model equivalence and future-sensor mutation checks are assigned to the ML engineer; those results are not counted above.
- The selected binary model remains rejected for monitoring. Episode deduplication reduces duplicate notifications, not false-positive predictions. There is no verified event-family diagnosis or causal explanation.
- One active local session, a 0.1–20 speed range, bounded pages and one-million-observation session cap limit the MVP. Completed-session count and total database retention remain operational responsibilities; no pruning/expired-history behavior is implemented.
- Persisted UTC due times support restart and concurrent workers. System-clock changes can affect pacing; this is not a hard real-time scheduler. Source ordering and source-time inference remain independent of playback timing.
- SSE history is durable; slow readers are flow-controlled by streaming rather than an unbounded Python queue. Public deployment, authentication, fleet-scale load, high availability and long-running storage capacity were not accepted here.
- Ground-truth comparison belongs to a separate retrospective demo/evaluation path, never to inference, alert policy or event payloads.

## Handoff

QA ownership returns for [replay integrity tests](../../tests/qa/test_replay_integrity.py), [replay contract tests](../../tests/contract/test_replay_contract.py), the narrow [Phase 6 compatibility assertion](../../tests/qa/test_backend_integrity.py), and this review. Backend fixes were made by their owner; no production implementation file was edited by QA. Root owns integration, final exported contracts, complete-suite execution, actual historical demo evidence and progress. Stop at Phase 7.
