# Phase 8 independent dashboard review

Status: **accepted for the local diagnostic dashboard scope**. No unresolved UI correctness blocker remains. The user explicitly authorized Phase 8. QA edited only its assigned browser harness, this review and `reports/frontend/qa/` evidence. Implementation fixes were made by the frontend/backend owners.

## Executed verification

Command from repository root: `node tests/e2e/dashboard.mjs`.

Final functional browser run: **15 passed, zero failed**, completed at `2026-11-10T10:47:24.294Z`. The harness uses installed Chrome through the pinned Playwright package, real Vite at `http://127.0.0.1:5173`, its same-origin `/api` proxy, and the actual local PostgreSQL/frozen-model backend. No fake predictions or success responses are substituted. The explicit network-failure test aborts a catalog request in an isolated browser context and then restores real requests; that fault injection is not a backend outage or successful data response.

The initial browser capability probe hit `spawn EPERM` under the restricted Windows token. Narrow execution escalation allowed installed Chrome to launch; no browser download was needed. A first 14-check functional run passed, then visual inspection identified encoding and stale-label issues. The owner fixed them, and the final 15-check run adds Stop, body/SVG encoding guards and selected-session state consistency. No failed assertion is hidden by claiming the first visual state was accepted.

Machine-readable results are in [results.json](../../reports/frontend/qa/results.json). Screenshots are under [reports/frontend/qa](../../reports/frontend/qa/).

| Route | Actual checks |
| --- | --- |
| `#overview` | Actual registered-well and sensor counts match API; historical badge and rejected-model disclosure; desktop/mobile layout |
| `#wells` | Real WELL-00011 P-PDG chart: all 600 x/y values equal the telemetry endpoint, null gaps remain disconnected; original timestamp strings retained despite browser timezone Asia/Oral; sensor/source selection; desktop/mobile layout |
| `#replay` | Existing 21-endpoint normal/transient comparison; real UI create/start/pause/speed/resume/reload/offline-reconnect/completion; exact retained reading count; confidence matches real prediction; unknown labels remain unavailable; separate Stop test |
| `#alerts` | Episode openings match persisted transitions, updates are not counted as new alerts; table/timeline reconcile to stored history; synchronous detections explicitly separate |
| `#model` | Model version, exact threshold and preprocessing fingerprint match endpoint; uncalibrated/rejected status and registered sensors are visible |

All five routes retain Historical Replay and rejected-monitoring disclosures. Both 1440x1000 desktop and 390x844 mobile viewports were exercised. No horizontal body overflow was observed; bounded tables/navigation may scroll inside their own containers. No uncaught browser exception was observed. The network fault test saw loading, a clear error, and successful retry against the real catalog.

## Actual replay evidence

The completed UI-created replay is `5a725349-e2c3-42e9-9dd3-4204ddd3ee7c`, registered validation source WELL-00011, inclusive positions 3540..3619. It persisted 80 original observations and three predictions at positions 3599, 3609 and 3619, ending at stream sequence 93. Pause held its cursor; speed changed 20 to 10 to 20; reload restored the selected paused session; resume plus a temporary offline browser period recovered the complete bounded history without duplicate readings.

Before completion the retrospective endpoint returned structured 409 and the UI withheld ground truth. After completion, endpoint 3599 retained null/unknown ground truth and unavailable comparison; the later endpoints displayed actual normal labels. This is development validation data, not a fresh detector benchmark. The UI separately displayed and reconciled the existing Phase 7 normal-to-transient case from the real retrospective endpoint.

The separate stopped replay is `c90d000a-6f39-4d68-90a6-a161871bbe7f`. UI Start followed by Stop ended at source position 1. Its snapshot remained exactly unchanged after waiting; Start/Resume/Stop controls were disabled; no prediction existed; retrospective evaluation remained 409. QA created and controlled only its own sessions and left no active session. Persisted completed/stopped history was retained.

## Findings and disposition

| Severity | Finding | Owner disposition / evidence |
| --- | --- | --- |
| Medium | Terminal snapshot could suppress SSE error recovery while the client watermark still lagged final events | Frontend added watermark-aware recovery; unit coverage and real reconnect flow pass |
| Medium | Command-conflict message suggested refreshing session listing, which did not refresh the selected command version | Frontend added explicit selected-replay refresh action; read-only integration review confirms correct callback |
| Medium | Plot cleanup purged the chart on every trace update, defeating preserved viewport state and risking resize races | Frontend separated mount/cleanup from serialized trace updates; real live chart rendered with no uncaught exceptions |
| Medium | Actual browser text contained mojibake separators/arrows/speed symbols | Frontend repaired UTF-8 and added a source guard; all-route body and SVG checks pass; refreshed screenshots show correct text |
| Medium | Selected replay option said running after the controller reached completed | Frontend derives the selected option from the current snapshot; final browser check asserts completed option text |
| Low | New-replay source selection could be confused with the independent persisted session selection | Frontend labels the controls New replay / well and New replay / dataset instance |
| Low | Mobile retrospective chart legend touched the positive trace | Frontend increased binary-chart top margin and anchored the legend above the plot; refreshed mobile screenshot verified |

A separate read-only final capture command, `node tests/e2e/capture_dashboard.mjs`, completed seven captures with zero browser exceptions. It waited for Plotly/container width agreement before screenshots: desktop 766.703/767 pixels, mobile 348/348, and full-width comparison 1112/1112. Desktop width remained correct after restoring from the mobile viewport. The earlier half-width desktop screenshot was a capture race with asynchronous resize, not a persistent chart defect. [Capture results](../../reports/frontend/qa/capture_results.json) and refreshed screenshots record the final legend spacing and responsive charts. No replay was created or controlled by this capture pass.

No unresolved functional correctness blocker remains. The final browser harness is [tests/e2e/dashboard.mjs](../../tests/e2e/dashboard.mjs). Root remains responsible for complete regression, production build, generated-contract verification and final progress.

## Immutable evidence and limits

Command: `.venv/Scripts/python.exe -m pytest tests/qa/test_replay_integrity.py::test_replay_preserves_originals_selected_artifacts_and_single_test_access -q -p no:cacheprovider --tb=short`.

Observed result: **1 passed in 3.20 seconds**, with the existing Starlette/httpx deprecation warning. This byte-hash audit verifies all 31 originals, frozen selection/code/dependency/data/model artifacts, rejected-monitoring flag and COMPLETE one-attempt test journal. It does not decode or infer on test data.

The selected model remains rejected for monitoring. The UI exposes diagnostic status and uncalibrated confidence; severity does not mean certified physical risk. SSE/pacing remain local best-effort behavior. Long-term storage retention, public deployment/authentication, fleet-scale load and multi-browser certification were not accepted here. Playwright used accessible-role and label selectors; no exhaustive keyboard, accessibility or screen-reader audit is claimed. Copilot work was not implemented.

## Handoff

Changed QA-owned files: `tests/e2e/dashboard.mjs`, `tests/e2e/capture_dashboard.mjs`, `docs/reviews/PHASE_8.md`, and screenshots/results under `reports/frontend/qa/`. No production, dependency, source, model or shared-contract file was changed by QA. Ownership returns to the orchestrator. Root may inspect the completed UI replay and retained screenshots without repeating model evaluation. Stop after Phase 8.
