# Phase 6 independent backend review

Status: **independent Phase 6 review complete**. The user explicitly authorized Phase 6 after the Phase 5 stop; earlier phase-specific restrictions remain historical. No unresolved API/contract/persistence integrity blocker remains in the reviewed diagnostic scope. The model remains rejected for monitoring.

## Assignment and evidence boundary

The reviewer owns this report, `tests/qa/test_backend_integrity.py` and `tests/contract/test_diagnostic_api_contract.py` only. Backend implementation belongs to the backend engineer; ML integration, immutable source registry, shared contract/dependency files and final acceptance belong to the orchestrator. No nested delegation is used. Other contributors' files are reviewed read-only.

Read: engineering rules, architecture, API contract, model card, progress, decisions, frozen inference interface and prior integrity checks. The selected Logistic Regression is a binary diagnostic model rejected for monitoring after the Phase 5 test. This review will not retrain it, change its threshold/artifact, evaluate test sources again or infer an event-family identity from a binary result.

## Review criteria

- A separately versioned diagnostic contract must distinguish binary decisions and uncalibrated abnormal scores from the planned canonical event-family prediction. Responses must state historical mode and rejected monitoring status without invented replay-worker or episode guarantees.
- Exact upstream sensor names, numeric types, finite values, source time semantics and bounded requests are validated. Auxiliary labels, metadata and unknown sensor names cannot enter inference. Client-supplied sensor windows claiming source provenance must agree with registered original bytes.
- Only registered train/validation real instances are exposed for this integration scope. Frozen test and excluded synthetic sources must remain inaccessible through wells, telemetry and inference.
- Model loading occurs through verified saved preprocessing/inference at startup; request handlers never fit. Missing model or database returns explicit unavailability; fixture storage is not a production fallback.
- PostgreSQL commits prediction, diagnostic alert and idempotency state atomically. Identical retries return the saved result; conflicting reuse is rejected. Parameterized SQL, duplicate prevention and persistent restart behavior need executed evidence.
- Structured errors/logs exclude secrets, request sensor arrays, internal paths and traces. Request IDs are bounded and generated/validated safely. Payload, pagination, range and inference concurrency limits are explicit.
- OpenAPI and normative response schemas match actual Pydantic behavior. Unit fixtures and real-artifact/PostgreSQL integration evidence are distinguished; passing software tests does not imply detector quality.

## Resolved findings and contract decisions

- **Medium, resolved: response source/window consistency was initially incomplete.** The first `DiagnosticPrediction` validator accepted a usable result with fewer than 60 rows or a provenance source coordinate different from its transport endpoint. The backend owner added complete-history and source/transport equality checks. Independent adversarial cases reject both inconsistent forms. Source timestamp precision is bounded to the supported transport precision instead of silently discarding excess fractional digits.
- **Medium, resolved: typed instances and Boolean/numeric coercion could weaken response invariants.** The owner separately strengthened score/diagnostic-flag strictness and enabled Pydantic instance revalidation. Independent cases reject string probabilities, Boolean scores, numeric diagnostic flags, event-family substitutions, contradictory threshold decisions, invalid evidence bounds and malformed abstention states. Existing typed instances cannot bypass repository validation through an unchecked model copy.
- The additive `diagnostic-1.0.0` schema preserves the original canonical schema/example bytes. It uses `undesirable_event` only for a binary positive, distinguishes abnormal score from selected-class confidence, and declares rejected-monitoring status. Direct calls use `historical_inference` with processing time, without fabricated replay identifiers or operational episode state. This is a reviewed new surface, not canonical event-family compatibility.

The selected model's poor false-alarm behavior is an existing measured limitation, not a software defect fixed by this phase. API tests must not be cited as renewed model acceptance.

## Executed independent verification

The final reviewer command was executed on the project Windows/Python 3.13.3 environment:

```powershell
$phase6Runtime = Get-Content .local/phase6/runtime.json -Raw | ConvertFrom-Json
$env:OILWELL_QA_DATABASE_URL = $phase6Runtime.qa_database_url
$env:OILWELL_RUN_FROZEN_QA = '1'
.\.venv\Scripts\python.exe -m pytest tests/qa/test_backend_integrity.py tests/contract/test_diagnostic_api_contract.py -q -p no:cacheprovider --tb=short
```

**86 passed in 6.36 seconds, zero failed/skipped**: 51 contract cases and 35 API/registry/persistence cases. One upstream Starlette warning reports deprecation of its current `httpx` TestClient integration; no result was skipped or suppressed. Earlier contract-only checks had 44 passes and two failures solely because the orchestrator-owned JSON Schema export had not yet been created. After export and implementation fixes, all final checks passed.

Coverage actually exercised:

| Area | Independent evidence | Limits |
| --- | --- | --- |
| Normative schema/OpenAPI | Current Pydantic response schema matches exported properties/required/definitions; complete runtime OpenAPI equals its export; original canonical schema rejects the distinct diagnostic response | JSON Schema checks structural rules; Pydantic enforces cross-field semantics |
| Input boundaries | Missing idempotency key, Boolean/string/float endpoint positions, invalid stride/range, extra target fields, malformed JSON, nonfinite/string/Boolean sensor values, wrong sensor names/counts and incomplete submitted windows rejected | Synthetic malformed inputs, not newly acquired telemetry |
| Errors and logs | Unexpected inference, telemetry and response-validation exceptions containing synthetic secret/path markers return sanitized 500 envelopes; validation errors omit input values; request IDs are fresh UUIDs and match response headers | Markers are synthetic, no actual credentials were logged or exposed |
| Startup and capacity | Failed model/registry/database startup leaves docs available and health degraded; predict refuses without fallback; concurrent fixture inference hits 429 and subsequently recovers its slot | In-process ASGI tests, separate from live socket verification |
| Payload/pagination | Actual request bytes exceed the cap even with a false small Content-Length; negative length rejected; well pagination is complete; malformed/cross-resource/cross-filter cursors rejected | No operational throughput or public-network capacity claim |
| Idempotency/alerts | Same request/key returns exact saved result and only one diagnostic alert; conflicting payload returns 409 without inference; alert response links the persisted prediction | Per-prediction diagnostics, not durable replay episodes |
| Real registered telemetry | Actual startup exposes exactly ten approved real train/validation sources; all four frozen test source IDs are rejected by both inference and telemetry routes with 404; returned telemetry contains exact sensors without labels/source paths | Test IDs were read from manifest metadata only; no test sensor/label rows were decoded or inferred |
| Real frozen inference | Actual selected bundle returns its exact immutable version/threshold, source hash/time and 27 causal evidence items; short history abstains; a patched estimator `fit` raises if called and was never invoked | Uses an approved train/validation window, not test evaluation or model-quality measurement |
| Missing evidence | Synthetic all-null values injected at the trusted registry fixture boundary yield unavailable score/unknown state and no estimator call | Explicit fixture; no source file or saved real prediction was altered |
| Forged provenance | Submitted altered values, null replacements, timestamps and wrong model version fail 422; wrong well/source association fails 404 | Registry supplies authoritative original bytes; arbitrary live uploads remain outside this contract |
| PostgreSQL concurrency/restart | Four concurrent real connections for one key produce exactly one build, one prediction and one alert; a new repository instance retrieves the identical saved result without inference; conflicting request hash fails 409 | Dedicated `oilwell_ai_qa` database, separate from app/root/backend test databases |
| PostgreSQL rollback | After a real prediction INSERT, a deliberately injected alert-insert exception causes the real transaction to roll back; no prediction/idempotency row survives, and a subsequent explicit retry succeeds | Injection tests the transaction error boundary; not a claim of tested network partition recovery |
| PostgreSQL query safety | Hostile quote/SQL-like key/filter values remain data; tables remain usable; a normal prediction creates no alert | Parameterized-query evidence, not a comprehensive penetration test |

The reviewer independently queried the dedicated PostgreSQL server: **18.3**. Each persistence test uses a UUID-scoped key prefix and deletes only its own fixture rows. An independent post-run query confirmed **zero remaining `qa-independent-*` prediction rows**; no broad database reset or cleanup of another contributor's records was performed. Database credentials were loaded from ignored local runtime configuration and never printed in tool output or stored in this report.

## Frozen-artifact and source integrity audit

A separate inline Python audit completed successfully (exit 0) after the final test run:

- All **31 original files** (23 Parquets and eight provenance documents) match acquisition SHA-256 values. Only approved sensor columns were decoded for integration; reading whole-file byte hashes did not evaluate test data.
- Selected manifest SHA-256 remains `dfbe88250db8808d58730ab6f0010da3c548cb4b1c26715ba4a4b78057e7130b`. All saved selected-code/dependency hashes, selected bundle manifest/model/preprocessor/split hashes match.
- The Phase 5 test journal remains COMPLETE with **one attempt**; saved test prediction/metric hashes match. This reviewer made no new estimator calls on test rows.
- Git comparison shows original canonical schema/example, frozen inference/preprocessing/features, selection/evaluation reports, manifests and prior model dependency pins unchanged. Backend tests introduce no retraining or retuning path.

## Separately executed integration evidence

The orchestrator reported four passing real frozen-model/PostgreSQL integration cases and a live loopback smoke run with all six routes and `/docs` returning HTTP 200, invalid input returning 422, a real validation-window score of `0.9999803020883076`, one linked persisted alert and exact idempotent replay. The backend owner separately reported 30 passing component tests, including five PostgreSQL cases. These results belong to their executing owners and are not counted in the reviewer's independent 86-case result. Root retains the whole-project regression, live process handoff and final acceptance record.

## Handoff and remaining limits

Ownership returns to the orchestrator for:

- [Independent API/provenance/PostgreSQL checks](../../tests/qa/test_backend_integrity.py)
- [Diagnostic schema/OpenAPI checks](../../tests/contract/test_diagnostic_api_contract.py)
- This report

No unresolved contract/integrity blocker or further implementation patch is proposed. Root must retain the separately versioned diagnostic scope and the original model failure disclosures. The service is a loopback portfolio backend; public authentication/deployment, continuous replay/SSE, ongoing alert episode transitions, frontend and copilot behavior were not implemented or accepted by this review. PostgreSQL persistence and software test success do not establish reliable event detection. Stop after the authorized Phase 6 handoff.

## Orchestrator closeout evidence

After independent handoff, the orchestrator executed the documented complete suite with all three isolated PostgreSQL DSNs and `OILWELL_RUN_FROZEN_QA=1`: **429 passed in 29.51 seconds**, zero failed/skipped and one upstream TestClient deprecation warning. This aggregate result is attributed to the orchestrator, separately from the reviewer's 86 cases. Live HTTP and PostgreSQL/log reconciliation are recorded in `reports/backend_smoke.json` and `reports/backend_verification.json`.
