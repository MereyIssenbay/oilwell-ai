# Local historical monitoring dashboard

The Phase 8 dashboard uses React, TypeScript and Plotly with real local API responses. It presents Overview, Wells & Sensor Explorer, Historical Replay, Alerts & Event History, and Model Information. The selected detector is still rejected for monitoring. The persistent **Historical Replay** badge identifies playback of historical records; this is not SCADA connectivity.

## Start

Keep the existing workspace PostgreSQL and backend running as described in [REPLAY.md](REPLAY.md). The frontend proxies its same-origin `/api` requests to `http://127.0.0.1:8001`, including the SSE connection. No credentials belong in the frontend or browser bundle.

From the repository root in PowerShell:

```powershell
.venv\Scripts\python.exe scripts/local_postgres.py start
.venv\Scripts\python.exe scripts/run_backend.py --port 8001
```

In another terminal:

```powershell
Set-Location frontend
npm ci
npm run generate:api
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite binds to loopback with a strict port. Stop foreground processes with Ctrl+C. A running acceptance instance should be reused, rather than starting a second process on the same port. Node/package versions and the exact verification outcomes are recorded in progress and the frontend lockfile.

Routes are `/#overview`, `/#wells`, `/#replay`, `/#alerts`, and `/#model`. The tested environment was Node 24.18.0/npm 11.16.0, React 19.3.1, TypeScript 5.9.3, Plotly basic 4.2.0 and Vite 8.3.7, pinned in `frontend/package-lock.json`.

## Main user flow

1. Open Overview and inspect backend status, registered wells and the loaded replay catalog. Counts describe the returned data rather than an invented fleet total.
2. In Wells & Sensor Explorer, select a real registered well/source and sensor. The chart uses observed nullable values and units from `/sensors`; missing values remain gaps. Source timezone is unverified.
3. In Historical Replay, create a bounded source interval, start it, pause, change speed and resume. Observe the streamed chart, prediction score/confidence, source cursor and diagnostic episode state. Stop is terminal; resume applies only to a paused session.
4. In Alerts & Event History, distinguish replay episode openings/updates/resolutions from the separate synchronous diagnostic alerts. Repeated positive predictions do not mean new episodes.
5. After a replay completes, inspect predicted-versus-actual comparison. Original labels come from the completed-only retrospective endpoint, never the ongoing sensor stream. Unknown target and abstention comparisons remain unavailable.
6. Inspect Model Information for the exact model version, frozen threshold, feature/window settings and limitations. This interface does not train or choose a model.

The already persisted Phase 7 validation example is the completed WELL-00011 session whose ID starts `4bc2ec39` (source rows 5600..5859). It includes normal-to-transient class 102, false-positive alerts and missed abnormal prediction endpoints. Select it from the server-provided session list; a new replay of those bounds reproduces the same frozen decisions. Its original evidence and chart are in [the replay report](../reports/replay/README.md). No hardcoded copy of those predictions is shipped in the UI; selecting its session reads the backend.

## Contracts and failure handling

Frontend API response types are generated from [OpenAPI](openapi.json). Regenerate after a reviewed backend contract export; do not maintain divergent handwritten interfaces. The additive dashboard endpoints and retrospective schema are specified in [API_CONTRACT.md](API_CONTRACT.md). The original diagnostic and replay contracts remain unchanged.

REST mutations use idempotency keys and command versions. A transport retry must reuse its original key/body; a stale-version conflict requires refreshing state before a new deliberate command. SSE events have durable per-replay sequence IDs. The consumer deduplicates deliveries, recovers gaps through bounded history reads and reconnects after transport failure. Reload restores the selected replay; terminal history must be fully drained before declaring the stream complete.

Chart/event buffers are bounded; displayed-range indicators disclose truncation. Source coordinates are preserved rather than silently converted into verified local or UTC measurements. Confidence is the uncalibrated probability for the selected binary class, distinct from abnormal score. Diagnostic warning/status colors do not estimate physical hazard severity. Rejected-model status remains visible rather than being converted into a healthy-well claim.

Loading, empty data, missing samples, backend failure and validation conflicts have explicit states. No placeholder metric, random time series, mock model result or static prediction fallback replaces an unavailable API. Test fixtures and intercepted failure cases are confined to tests.

## Verification

```powershell
Set-Location frontend
npm run typecheck
npm test
npm run build
```

From the repository root with services running, use `node tests/e2e/dashboard.mjs` for the reproducible browser flow and `node tests/e2e/capture_dashboard.mjs` for read-only final captures. The former creates only its own bounded local replay sessions; ensure another replay is not active. `OILWELL_FRONTEND_URL` defaults to `http://127.0.0.1:5173`, and `OILWELL_BROWSER_PATH` defaults to the installed Windows Chrome executable. The capture command consumes the completed session ID in the saved QA results and never mutates the API.

Independent browser checks use installed Chrome and live local services; selected failure scenarios deliberately intercept requests and are reported separately. Actual route coverage, screenshots, regression outcomes and remaining limitations are recorded in [PROGRESS.md](PROGRESS.md) and the Phase 8 review. Browser startup and Windows pytest fixtures can require execution outside the restricted agent token; this does not change the loopback-only application scope.

This phase does not include the LLM copilot, public hosting, authentication rollout, operational certification or a production deployment of Vite.

Observed acceptance: 523 Python tests passed in 87.72 seconds; 16 frontend tests passed in 4.03 seconds; TypeScript and production build passed (Vite build 746 ms); 15 browser checks passed with zero failures. Eight saved desktop/mobile screenshots were reviewed, and seven final read-only captures verified Plotly widths after viewport changes with zero browser exceptions. The lazy Plotly chunk is about 385 KB gzip. Performance, accessibility certification and cross-browser coverage were not established by these local checks.

The additional native Computer Use inspection ended because that tool could not confidently determine the Windows browser URL. No further native UI actions were issued; the separately planned automated tests used an explicit localhost URL in their own installed-Chrome browser context. This limitation does not represent a failed dashboard route.
