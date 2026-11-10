# Phase 8 backend contract verification

Scope: read the current engineering rules, architecture, API contract, progress and decisions; verify the dashboard's real API needs and implement only the orchestrator-authorized additive browsing/retrospective endpoints. Existing inference, source registry, original schemas, model artifacts, threshold and test evidence are unchanged. No training, test re-inference or external acquisition occurred.

## Additive contracts

| Route | Contract and boundary |
| --- | --- |
| `GET /replays?cursor&limit` | `ReplayList` with playback flags, `items: ReplaySnapshot[]`, `next_cursor`; default/max 100; newest first using stable `(created_at, replay_id)` keyset pagination |
| `GET /sensors` | `SensorCatalog.items` contains the exact registered sensor `name` and `unit_or_domain`; source time basis remains explicitly unverified/assumed UTC |
| `GET /replays/{id}/evaluation?after_sequence&limit` | `RetrospectivePage`, version `retrospective-1.0.0`, completed replay only; default 100/max 1000 stored prediction endpoints; 409 before completion, including stopped/failed sessions |

The retrospective response marks `retrospective_only=true`, `mode=historical_replay`, `simulated_playback=true`, `diagnostic_only=true`, and `accepted_for_monitoring=false`. Each row contains persisted prediction ID, event sequence, source position/timestamp, uncalibrated abnormal score and binary predicted event, separately from original class/state, actual family/name/phase, actual binary target and nullable decision match. Unknown labels are not normal; unsupported codes retain their raw value and have unknown derived target. Abstentions or unknown target produce a null match. `state` remains raw auxiliary ground truth without invented physical interpretation.

Evaluation first checks completed state, immutable source/model/preprocessor/threshold bindings and cursor consistency. It then reads only original class/state columns from one manifest-selected file, verifying original SHA-256 and metadata-registry SHA-256 before decoding. Paths cannot be supplied by callers; a 128 MiB source-byte cap bounds this adapter. Rows are joined by stored endpoint position and exact timestamp, source ID/checksum and replay/event identity. No data after the replay cursor or before its causal warmup is returned. Label frames are never placed in the serving registry, worker or inference runtime, and no inference call occurs during evaluation. Each request retains at most one source label frame; no unbounded cache is introduced.

Migration 003 adds the creation-time/UUID pagination index. The one-active-session invariant means an active session is the newest session under ordinary API writes, since another cannot be created while it is active. A page cursor remains stable when a newer replay is inserted. Normal history paging and an explicit next cursor prevent fabricated total counts.

## Verification evidence

- `.venv/Scripts/python.exe` invoked `pytest tests/backend/test_dashboard.py -q -p no:cacheprovider --tb=short` with the ignored dedicated `OILWELL_TEST_DATABASE_URL`: **12 passed in 11.84 seconds**, zero failed/skipped.
- After migration 003 and final contract changes, `pytest tests/backend tests/contract -q -p no:cacheprovider --tb=short` with the same dedicated database: **151 passed in 23.86 seconds**, zero failed/skipped.
- Both runs reported the existing upstream Starlette/httpx deprecation warning. No warning suppression or dependency change was made.
- Actual PostgreSQL tests persist/reload a completed replay and retrospectively join its stored predictions without model calls; fixture cleanup deletes only its own replay/event/request rows.
- Actual approved validation source labels confirm unknown class at row 3599, normal 0 at 3600 and transient 102 at 5759. Only `class`/`state` were decoded by the retrospective adapter; the serving registry remains sensor-only and rejects unregistered sources.
- Tests cover all noncompleted states before any label read, unknown/unmapped/null target semantics, strict Boolean markers, pagination, invalid cursors/limits, source-boundary and stored-provenance rejection, immutable event history and absence of retrospective labels in telemetry/history.
- Read-only frontend client review confirmed generated-schema aliases, real route names/query parameters, source-time formatting and idempotent mutation closures. Three client issues were reported to the frontend owner: a terminal-snapshot/SSE-tail reconnect race (reconnect must continue until the applied watermark catches up), retry closures retaining an old replay/source identity after selection changes, and conflict recovery refreshing the list without refreshing the selected snapshot version. These frontend fixes and their verification remain with that owner and QA.

Root owns final OpenAPI exports, whole-suite regression, actual browser/API integration, lifecycle process restart and the live UI demonstration. This review does not substitute fixture results for that acceptance evidence.

## Files and handoff

Changed implementation: `backend/app/dashboard.py`, `backend/app/dashboard_schemas.py`, the router registration in `backend/app/main.py`, additive list/migration methods in `backend/app/replay_repository.py`, and `backend/migrations/003_dashboard_indexes.sql`.

Tests/report: `tests/backend/test_dashboard.py` and this review. Root must export OpenAPI after these changes; the frontend generates its TypeScript consumers from that export. Old canonical, diagnostic and replay schema definitions are preserved. No model-quality acceptance is implied by a working retrospective comparison. Ownership is returned to the orchestrator, with no remaining backend contract blocker from these checks.
