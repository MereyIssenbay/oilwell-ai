# Phase 6 local diagnostic backend

The FastAPI service wraps the frozen selected model and PostgreSQL persistence. It exposes binary historical diagnostics only. The model failed its Phase 5 normal-time false-alarm check and is **not accepted for monitoring**; this status appears in health, model, prediction and alert responses. No model training occurs in handlers.

## Start locally

From the repository root, using Python 3.11+ (verified here on 3.13.3):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.txt
.\.venv\Scripts\python.exe scripts/local_postgres.py start
.\.venv\Scripts\python.exe scripts/run_backend.py
```

Open [Swagger UI](http://127.0.0.1:8000/docs), [health](http://127.0.0.1:8000/health) or [model information](http://127.0.0.1:8000/models/info). `run_backend.py` binds only `127.0.0.1`, defaults to port 8000 and accepts `--port`. Run it in the foreground for a normal Ctrl+C shutdown. The Phase 6 acceptance run also left a hidden local process running on port 8000; stop that existing project process before starting another on the same port, or choose another port.

The local PostgreSQL helper uses installed PostgreSQL binaries, defaulting to `C:/Program Files/PostgreSQL/18/bin`. Supply `--bin-dir` or `OILWELL_POSTGRES_BIN` elsewhere. It creates only `.local/phase6/postgres`, binds `127.0.0.1:55436`, and generates random credentials in ignored `.local/phase6/runtime.json` and its password file. It creates a dedicated app database plus three isolated test databases. Existing system databases are not used. An authenticated `SHOW data_directory` check prevents mistaking an unrelated listener for this cluster. Use `scripts/local_postgres.py stop` to stop this workspace cluster after stopping the API. Initialization/start required narrow execution escalation under the agent's Windows sandbox; normal terminal permissions may differ.

`DATABASE_URL` in the process environment takes priority over the ignored local runtime configuration. `.env.example` documents empty credentials and local defaults; the template is not loaded automatically. Do not put credentials in command-line arguments or tracked files. The local helper role owns only this dedicated cluster; it is a development setup, not deployment hardening.

Missing model/data/database leaves `/docs` accessible and `/health` degraded. Affected operations return structured 503 errors; no fake model or alternative persistence is selected. Restart the application after fixing a startup dependency. The registered model bundle and raw train/validation source files must already exist; startup does not download them.

## Routes and example

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Model/data/database readiness and diagnostic status |
| GET | `/wells` | Ten registered real train/validation wells with source bounds |
| GET | `/wells/{id}/telemetry` | Bounded sensor-only source rows, including null observations |
| POST | `/predict` | Actual frozen inference and atomic persistence |
| GET | `/alerts` | Persisted per-prediction diagnostic positive events |
| GET | `/models/info` | Immutable version, threshold, sensors, provenance and limitations |

Example using a registered validation source:

```powershell
$body = @{
    source_instance_id = '3w:3b7750afe480cb1d04361795d4a5cded832ae3a05d5ef30f533d440c81bfb4cf'
    endpoint_position = 59
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/predict' `
    -ContentType 'application/json' -Headers @{ 'Idempotency-Key' = 'example-window-59' } -Body $body
```

Repeat the exact key/body to retrieve the original prediction. Change the key for an intentional new operation; changing the body with the same key returns 409. A successful response is sent only after prediction and optional alert commit together. Keys remain stored for the lifetime of this local database. PostgreSQL uses parameterized SQL, bounded connection/statement/lock timeouts, unique keys and transaction-scoped advisory locking. The versioned [SQL migration](../backend/migrations/001_diagnostic_predictions.sql) is applied at startup under a migration lock.

Complete endpoints align to `59 + 10*k`; early prefixes return `insufficient_history`. Optional `samples` contain all 27 exact sensor names and must match the original source window, including timestamps/nulls. Model version may be supplied for strict matching; thresholds/features cannot be overridden. Test and excluded synthetic sources remain unregistered. No source labels, filenames or absolute paths enter the public payload or model inputs.

The response uses `schema_version=diagnostic-1.0.0` and `event_type=normal|undesirable_event|unknown`. `abnormal_score` is uncalibrated; `confidence` describes the selected binary class. The exact threshold is `1.1881945293311268e-14`. `execution.mode=historical_inference`, not live telemetry or a fabricated replay session. Source-naive timestamps are preserved in provenance while transport coordinates explicitly assume UTC; processing UTC is separate.

Alerts are **diagnostic positive-prediction records**, not operational episodes. This phase does not implement a replay worker, dwell/recovery, pause/resume, SSE, acknowledgement or ongoing-episode state. The [API contract](API_CONTRACT.md) separates this additive surface from the unchanged planned canonical event-family/replay contract. [Diagnostic JSON Schema](contracts/diagnostic_prediction.schema.json) and [OpenAPI export](openapi.json) are checked against typed implementation.

## Validation, logs and limits

Request bodies are capped at 262,144 bytes by default, including chunked bodies. Sensor Booleans/strings/nonfinite values, targets/metadata in sensor maps, unsupported sensors, duplicate or mismatched timestamps/windows, invalid model versions and unregistered sources are rejected. Telemetry pages are limited to 1,000 rows; well pages to 100. Prediction admission is capped at four concurrent requests, and shared model execution is serialized. These are local safeguards, not throughput guarantees.

Structured JSON logs record dependency readiness, prediction IDs/model version/status, idempotent replay and alert publication. They exclude raw sensor arrays, request bodies and credentials. Error envelopes contain code/message/bounded details/request ID; clients never receive stack traces, database URLs or internal absolute paths. Successful prediction logs appear only after persistence commits. The launcher disables ordinary URL access logs; application JSON logs remain enabled.

## Tests and observed acceptance

Fixture tests explicitly inject fake runtimes/registries and an in-memory repository. Production always instantiates PostgreSQL persistence; fixtures are not a database fallback. Actual database tests use isolated app-test, QA and integration databases, with unique keys and scoped cleanup. Real-artifact checks compare API results with saved validation predictions, validate original sensor payloads and ensure test sources are inaccessible.

The full verification command passes database URLs from ignored local configuration without printing them:

```powershell
@'
import json, os, pytest
from pathlib import Path
from uuid import uuid4
c = json.loads(Path('.local/phase6/runtime.json').read_text())
for env, key in [
    ('OILWELL_TEST_DATABASE_URL', 'test_database_url'),
    ('OILWELL_QA_DATABASE_URL', 'qa_database_url'),
    ('OILWELL_INTEGRATION_DATABASE_URL', 'integration_database_url'),
]:
    os.environ[env] = c[key]
os.environ['OILWELL_RUN_FROZEN_QA'] = '1'
raise SystemExit(pytest.main([
    'tests', '-q', '-p', 'no:cacheprovider', '--tb=short',
    '--basetemp', str(Path('.local') / ('pytest-phase6-' + uuid4().hex)),
]))
'@ | .\.venv\Scripts\python.exe -
```

Without explicit test DSNs, PostgreSQL integration tests skip instead of using another store; do not report such a run as real database acceptance. One upstream Starlette/httpx TestClient deprecation warning may appear; it does not indicate a failed assertion.

[Live HTTP smoke evidence](../reports/backend_smoke.json) records successful routes/docs, actual frozen validation inference, an associated PostgreSQL alert, exact idempotent replay and rejected invalid input. [Progress](PROGRESS.md) and [independent review](reviews/PHASE_6.md) record final test counts, commands, corrections and limitations. Serving a model is not a new evaluation: all Phase 5 selection/test artifacts remain unchanged, and no test inference or retraining occurs.
