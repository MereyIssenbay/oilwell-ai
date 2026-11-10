# Historical telemetry replay

Phase 7 adds API-controlled playback of one registered train/validation source at a time. Every replay response/event says `mode=historical_replay`, `simulated_playback=true`, `diagnostic_only=true` and `accepted_for_monitoring=false`. Playback of a real historical source does **not** change its `source_kind=real` to synthetic.

The selected model remains `oilwell-binary-phase5-c4e1835a82620306778a`, with the exact threshold `1.1881945293311268e-14`. It failed monitoring acceptance in Phase 5. This is a working replay system around a rejected diagnostic model, not evidence of operational detection reliability.

## Run locally

Use the existing pinned backend environment and workspace PostgreSQL described in [BACKEND.md](BACKEND.md). From the repository root in PowerShell:

```powershell
.venv\Scripts\python.exe scripts/local_postgres.py start
.venv\Scripts\python.exe scripts/run_backend.py --port 8001
```

The launcher binds only to `127.0.0.1`. The Phase 7 demo uses port 8001 so an earlier Phase 6 acceptance process on 8000 need not be stopped. The API initializes additive migration `002_historical_replay.sql` and its worker at startup. Credentials remain in ignored local configuration; no model fitting occurs. Swagger is at [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs).

In another terminal, run the bounded actual-data scenario:

```powershell
.venv\Scripts\python.exe scripts/replay_demo.py --base-url http://127.0.0.1:8001
```

An existing created/running/paused session must first be stopped through its command endpoint; the script never silently cancels another replay. Each invocation creates a new replay and retains its PostgreSQL history. The report is written under `reports/replay/` and identifies that invocation. A completed run is not resumed or rewound; create a new session instead.

## API controls and reading results

`GET /wells` lists the ten registered real train/validation instances. Test and excluded synthetic sources are not served. Source IDs, rather than client file paths, select an instance.

| Route | Behavior |
| --- | --- |
| `POST /replays` | Create with `source_instance_id`, inclusive `start_position`/`end_position`, optional exact `model_version` and speed 0.1..20; requires `Idempotency-Key`; returns 201 snapshot |
| `GET /replays/{id}` | Durable snapshot with cursor, command version, last sequence and current alert episode |
| `POST /replays/{id}/commands` | `start`, `pause`, `resume`, `stop`, `set_speed`; requires current `expected_version`, idempotency key, and speed only for `set_speed` |
| `GET /replays/{id}/event-history` | Bounded ordered persisted events after `after_sequence`; page size 1..1000 |
| `GET /replays/{id}/predictions` | Same paging, filtered to prediction events |
| `GET /replays/{id}/alerts` | Same paging, filtered to episode transitions, including updates/resolutions |
| `GET /replays/{id}/events` | SSE stream; `Last-Event-ID: <replay_id>:<sequence>` resumes after the last committed event received |

Creation defaults to the whole source, with a one-million-observation upper bound. The source registry independently verifies increasing unique one-second timestamps. Only one created/running/paused session is permitted. Stop is terminal; pause preserves the cursor and open episode. Commands are committed at row boundaries under a database lock. Same scoped key/payload returns the original result; conflicting reuse or stale command version returns 409. A worker does not increment the command version for every telemetry row, so ordinary playback does not make a UI command stale continuously.

Example creation body for the demo:

```json
{
  "source_instance_id": "3w:3b7750afe480cb1d04361795d4a5cded832ae3a05d5ef30f533d440c81bfb4cf",
  "start_position": 5600,
  "end_position": 5859,
  "speed_multiplier": 20.0
}
```

Follow with `{"command":"start","expected_version":1}` and a new idempotency key. Read the current snapshot version before each new command. A retry must retain its original body and key, not rebuild the body from a later snapshot.

## Order, causality and persistence

Each processing transaction advances exactly one original source row. It commits that reading, any aligned prediction, episode transitions and the new cursor/sequence together. The source row lock serializes concurrent workers and commands. If inference or persistence fails, the transaction rolls back; the row is eligible for retry. A process restart resumes from persisted cursor, with source/model/preprocessor/threshold bindings rechecked. Network delivery is at least once; database processing does not depend on a connected client.

Replay begins with empty history at its requested start. The first prediction requires at least 60 replayed rows and an endpoint on the frozen original grid `59+10*k`. The existing adapter receives only the trailing 60 sensor observations, with no row before replay start or after the current position. Speed changes delivery pacing, never feature windows, source timestamps or model decisions. Persisted UTC deadlines make pacing best-effort: system-clock jumps and PostgreSQL/inference overhead can alter achieved speed. The observed 260-row demo took 67.34 seconds from creation to completion, including API controls/pause, despite requesting 20x; this is not a 20x throughput guarantee. There is no catch-up row skipping. The saved preprocessing, missing-value policy and exact selected inference pipeline are reused unchanged.

An SSE event ID identifies a durable per-replay sequence across all event types. Consumers keep the last successfully applied ID, deduplicate repeated IDs and reconnect using that watermark. Snapshot watermark N followed by subscription after N avoids a snapshot/stream race. Invalid, foreign and ahead cursors are rejected before streaming. Terminal streams drain committed history then close. Heartbeats consume no sequence numbers. A stream transport error requests reconnection; it is not a persisted model result. REST event history is the fallback.

There is no silent history expiration in this local phase: sessions/events remain in PostgreSQL until an explicit future retention policy or administrator action. Reads use bounded pages, and SSE reads bounded batches without an unbounded in-memory client queue. Repeated sessions still consume disk. Production retention, fleet scale and public hosting remain outside this local MVP.

## Diagnostic alert deduplication

The immutable policy `replay-episode-ge-no-dwell-v1` opens an episode on the first usable score `>=` the frozen threshold. More positive predictions update the same episode instead of opening duplicate alerts. A usable normal prediction resolves it; a subsequent positive opens a new episode. Abstention records insufficient data and preserves any open episode. No training, threshold selection, dwell fitting or calibration occurs in replay.

The `/alerts` endpoint from Phase 6 retains its per-synchronous-prediction meaning. Replay episode events are read from `/replays/{id}/alerts`; consumers count `transition=opened` for new alerts, not every update. Episode state is captured in each prediction envelope at prediction time, so a later recovery cannot rewrite historical evidence. A replay ending with an open episode is right-censored, not automatically recovered. Its initial positive can be left-censored; neither is a verified event onset.

The unchanged inner `diagnostic-1.0.0` prediction retains `execution.mode=historical_inference`. Its outer `diagnostic-replay-1.0.0` envelope explicitly supplies replay identity, event sequence, speed, source position and episode-at-prediction state. This additive contract does not widen canonical event-family schema v1.0 or claim family classification.

## Retrospective ground truth

Runtime/streams contain only the exact 27 admitted sensor columns and model evidence. `class` and auxiliary `state` are excluded. Genuine registered `ESTADO-*` sensor inputs are distinct from the excluded `state` label column. No future labels, paths containing class directories, or evaluation outcomes are joined into inference.

The separate demo script waits for completion, verifies original bytes, then reads labels locally and joins them to persisted predictions by source position. It compares scores against the already saved validation predictions with absolute tolerance 1e-14 and exact decisions. The scenario deliberately includes known normal rows followed by transient class 102 (spurious closure of DHSV). This is a retrospective software demonstration chosen from development-exposed validation data, not a new benchmark or unseen-well result. Null labels stay unknown. Source time is preserved with `source_naive_assumed_utc`; actual physical UTC and physical causality remain unverified.

Actual demo output, verification commands and independent review outcomes are recorded in [PROGRESS.md](PROGRESS.md) after execution.
