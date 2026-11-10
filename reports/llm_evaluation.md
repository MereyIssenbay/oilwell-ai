# Phase 9 copilot evaluation

The copilot is an evidence-constrained explanation interface, not a new diagnostic model. The selected ML artifact and threshold are unchanged and remain rejected for monitoring. This evaluation does not establish petroleum-domain expertise, production reliability or calibrated explanation confidence.

## LLM-owner verification

On 2026-11-10, the LLM owner ran:

```powershell
.venv/Scripts/python.exe -m pytest tests/llm/test_copilot.py -q -p no:cacheprovider --tb=short --basetemp .local/phase9-llm-tests-final
```

**Observed result: 48 passed in 1.80 seconds, zero failed/skipped.** All providers in these checks are offline fixtures or `httpx.MockTransport`. No paid OpenAI requests or credential reads were performed by the LLM owner. An initial restricted-token attempt encountered the established Windows pytest temporary-directory `WinError 5`; the narrow normal-permission rerun passed. The earlier implementation checkpoint had 34 passing cases before the 14-case versioned evaluation set was added.

| Verification area | What is actually checked |
| --- | --- |
| Factual grounding | Exact synthetic fixture mean 123, trend 0.5 and missing endpoint remain unchanged; all factual claims carry evidence IDs; raw packet is retained for inspection |
| Supported questions | Observation, trend, missing-data, score and alert-explanation intents; case/punctuation normalization; Russian supported example |
| Unsupported diagnoses/actions | Hydrate diagnosis, physical-cause speculation, valve closure, shutdown, future outcome and unknown questions abstain before a provider call |
| Missing/conflicting evidence | Empty observations, unavailable prediction, conflicting integrity flag, score/confidence/decision mismatch and missing-fraction/count inconsistency |
| Prompt injection | Instructions embedded in user questions never become provider prompts; poisoned retrieved text with a forged self-checksum fails the independently pinned source comparison |
| Provider grounding | Unknown/duplicate/empty claim IDs, forged citations and unapproved diagnosis IDs fall back; the model cannot output prose or sensor values in its selection schema |
| Citation fidelity | Actual local passage SHA-256, complete catalog pin, HTTPS source host allowlist, modified catalog rejection and citation/interpretation association |
| Availability and budget | Provider disabled, HTTP timeout, refusal/incomplete output and malformed response; lifetime two-call reservations survive restart and count failed attempts |
| Reproducibility/cache | Persisted valid response reused without another mock call; cache bounded to 128 entries; evidence, knowledge, prompt and provider configuration determine cache identity |
| Transport | Responses strict JSON Schema, 400-output-token cap, `store=false`, no tools, input-byte cap and fixed API host; no real network calls |

The explicit [14-case evaluation set](../llm/evaluation_cases.json) covers factual grounding (4), missing data (2), conflicting evidence (2), unsupported diagnoses (2), control requests (1), future outcomes (1), and prompt injection (2). All 14 cases passed within the 48-test run. They use clearly named synthetic fixtures; their values are not measured well telemetry. Broader adversarial integration tests are owned independently by QA.

## Why unsupported claims cannot be introduced as prose

The provider receives at most six server-built observation candidates, stored prediction/model facts, recognized question intent and three reviewed reference paragraphs. It returns only claim and citation identifiers plus an abstention flag. Python checks membership and citation support and renders approved sentences. Mandatory uncertainty/model/historical limitations remain regardless of selection. Numerical claims never come from provider-generated free text. Retrieved text is untrusted: only metadata/content matching the pinned reviewed source objects can support separate immutable interpretation templates.

The real-data adapter must independently verify persisted predictions, original causal windows, exact means and provenance before building the packet. It must omit labels, paths, class-bearing source identifiers and future outcomes, preserve endpoint-null readings and use episode state captured at prediction time. Those checks belong to backend integration and independent QA, not to this fixture-only result.

## Limitations

This is a deliberately narrow question interface with deterministic English responses and a small set of English/Russian question intents. Unrecognized paraphrases abstain rather than guess. The three-paragraph corpus supports data-quality and causality limits; it does not support general well engineering, event-family diagnosis or operating procedures. The provider prioritizes approved observations; it does not produce unconstrained narrative reasoning. Tests of malicious fixtures demonstrate the implemented boundaries, not completeness against every possible attack. Cache/budget state is local to this installation; deleting the ignored ledger would reset its counter. A model alias is configurable only within the reviewed allowlist and may change upstream.

Actual persisted-prediction/browser checks, full regression totals and any explicitly authorized economical provider smoke result are consolidated by the orchestrator below. No live-provider success or token expenditure is claimed by the LLM-owner test run.

## Initial economical provider check and transport adjustment

The orchestrator's first explicitly authorized generation attempt returned `provider_unavailable` after **2.727 seconds**. A repeat reused the cached fallback and made no further generation request; the durable lifetime counter retained one reserved attempt. The first transport failure category was not logged, so it cannot be identified as a timeout from this evidence alone. Generated-token usage and any billing for that failed attempt are unknown. A separate non-generating official model-access request returned HTTP 200 in 1.116 seconds, confirming access rather than successful generation.

The LLM owner then increased read/write timeouts from two to four seconds, retained two-second connect/one-second pool timeouts and the six-second elapsed chunk deadline, and added sanitized failure-category logging. Logs contain only fixed event names and HTTP status or exception type, never exception messages, response bodies, API keys or prompts. No cache, call counter or ledger was reset. Targeted offline transport checks after this change: **5 passed, 43 deselected in 1.19 seconds**. The LLM owner made no network or paid requests; any remaining authorized attempt is controlled by the orchestrator.


## Orchestrator integration and live-provider evidence

The backend explains existing persisted predictions and verifies their exact original causal windows without executing inference. The actual replay smoke used event 91 / row 3619 from replay `5a725349-e2c3-42e9-9dd3-4204ddd3ee7c`; saved prediction `17ae74db-f98f-42c3-b84c-1efe786eeb40`. All prediction fields and citation contents matched. The deterministic response took 0.089 seconds and its repeat was cached. The synchronous saved-prediction endpoint also returned HTTP 200 with episode state correctly `unknown`. See [API smoke](copilot/api_smoke.json) and [synchronous smoke](copilot/synchronous_smoke.json).

The first explicitly requested external attempt returned `provider_unavailable` in 2.727 seconds; its repeat was cached. No usage was received, so its billing and exact failure cause are unknown. A non-generating official model-access check returned HTTP 200 in 1.116 seconds. Before the second attempt, read/write limits were adjusted from two to four seconds while connect/pool stayed two/one and the elapsed chunk deadline remained six. A final review added a deadline check immediately after headers, before body reading; a fake-clock test verifies expired headers cause zero body reads. Per-I/O/deadline checks are not a universal OS-level DNS or absolute wall-clock guarantee.

The **second explicit external attempt succeeded** in **2.811 seconds**, returning valid selected claim/citation IDs and **1,331 input / 78 output tokens**. The server rendered and verified the actual sensor/model facts; the repeat was cached. At the [official standard text tariff](https://developers.openai.com/api/docs/models/gpt-6-luna) observed on 2026-11-10, this successful call is approximately **$0.0001721**. This is not an account bill, total-spend claim or balance check; first-attempt token usage remains unknown. See [provider result](copilot/provider_smoke.json), [initial failure](copilot/provider_attempt_1.json) and [access check](copilot/provider_access.json).

The persistent ledger is now **2/2**. A further supported provider-mode question returned deterministic `budget_exhausted` with **zero additional reservations**. The ledger was preserved across process restarts. No budget reset or third generation request occurred. [Budget verification](copilot/budget_verification.json) records these checks. The dashboard still works locally, and the successful provider response can be displayed from its one-hour cache; once expired, it also falls back without a new paid request.

Independent QA passed **90 offline Python/contract tests** and **11 real-browser checks**. An additional read-only browser check displayed the actual **provider-selected / cached** response, verified exact saved token usage/evidence, and observed ledger **2 -> 2** with zero uncaught browser errors. Both screenshots were inspected. [Independent review](../docs/reviews/PHASE_9.md), [main browser results](copilot/qa/browser_results.json) and [cached-provider browser result](copilot/qa/provider_browser_results.json) distinguish real persisted data from injected failures and offline fixtures.

Frontend tests: **25 passed in 5.05 seconds**, six files; TypeScript and Vite production build passed (551 ms). Runtime/HTTP/exported OpenAPI match and the generated TypeScript matches a fresh generation byte for byte. All **133 protected data/model/inference/schema files remain unchanged**; final-test journal still records exactly one completed attempt. Final full-suite count and release evidence are in [PROGRESS.md](../docs/PROGRESS.md).

Final release regression after the late-header guard: **672 passed in 58.12 seconds**, zero failed/skipped, one pre-existing Starlette/httpx deprecation warning. Breakdown: 523 prior tests + 10 backend copilot + 49 LLM + 90 independent QA/contract. No paid API calls occur in this suite.
