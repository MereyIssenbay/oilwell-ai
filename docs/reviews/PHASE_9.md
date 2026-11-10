# Phase 9 independent copilot review

Status: independent review complete for the local historical copilot. No open high/medium findings remain in the reviewed scope. This is software grounding/security evidence, not acceptance of the underlying detector or proof of universal LLM reliability.

## Scope and evidence boundary

The reviewer owns independent QA/contract/browser tests and this review; the orchestrator owns backend integration and the implementation agents own the LLM service and UI. No paid provider calls, model fitting, new dataset acquisition or test-set inference are authorized for the reviewer.

The existing model is binary, uncalibrated and rejected for monitoring. An explanation cannot establish an event family, physical cause, operator procedure or safe intervention. Sensor means and recent trends describe observations, not validated feature attribution.

Review targets:

- Stored prediction lookup, immutable evidence/window hashes and episode snapshot at prediction time; no use of later replay state or retrospective labels.
- Explicit provider allowlist and packet-local evidence references; no class-bearing paths, raw source identities, labels, split metadata or future outcomes.
- Server rendering of numerical statements from evidence; rejection of forged facts, citations, unsupported diagnoses and control instructions.
- Missing/conflicting evidence, untrusted user questions and retrieved text, provider error/timeout and deterministic fallback.
- Explicit opt-in provider calls, bounded context/output/call budget, durable reservation, cache separation and absence of credentials in responses/browser assets/logs.
- Real stored-prediction UI flow, source attribution, historical/diagnostic warnings and no automatic provider request on replay updates.

## Findings and disposition

1. **High, resolved — retrieved prose was initially promoted into approved interpretations.** The initial service copied `Source.content` into claim text. A malicious passage could therefore bypass the provider's ID-only restriction through deterministic fallback. The implementation now uses separate reviewed interpretation templates, validates retrieved objects against the reviewed catalog, and pins the catalog's complete normalized metadata/content digest. Independent cases inject instructions, invented numerical readings, forged citation identity and attribution, and rewrite content with a fresh self-declared checksum; all are rejected before a provider call. See [service](../../llm/service.py), [catalog verification](../../llm/knowledge.py) and [QA cases](../../tests/qa/test_copilot_integrity.py).

2. **Medium, resolved — cached responses initially bypassed semantic grounding checks.** Typed cached `Claim.text` alone did not prove factual support. Cache reuse now compares evidence/provenance and fixed prediction/limitation claims with a freshly generated safe response, and admits only current approved observation/interpretation/citation objects. Corrupt cached facts, foreign evidence, altered hashes, attribution and abstention text regenerate a deterministic response without another paid request. Independent tampering cases pass.

3. **Low, resolved — source URL scheme/host and suggested question behavior.** Citation URLs now admit only reviewed HTTPS hosts without userinfo/custom ports; the frontend separately suppresses non-HTTPS links. The suggested observation question is accepted, and quick-fill buttons use documented supported questions without triggering requests.

## Executed checks

| Check | Actual result | Scope |
| --- | --- | --- |
| Independent Python QA and contract suite | **90 passed in 3.62 s**, zero failed/skipped | Synthetic source fixtures, mocked provider transport, temporary SQLite stores and actual exported schemas |
| Actual local Chrome flow | **11 checks passed**, zero failures/browser exceptions | Existing completed replay, explicit explanation, evidence/citation inspection, unsupported diagnosis/injection, missing data, cache, injected HTTP failure/retry, mobile layout |
| Cached live-provider browser capture | **1 additional check passed**, zero browser exceptions/new reservations | Exact previously generated provider answer displayed as cached; reported usage 1,331 input / 78 output tokens, with lifetime ledger unchanged at two attempts |
| Real evidence comparison | **27 sensor summaries** matched persisted means, final readings and finite counts from the original 60-row API window | Stored model version/score/confidence/threshold and prediction-time episode also matched; no new inference |
| Frozen integrity | **133 protected files unchanged**; test journal `COMPLETE`, `test_attempts=1` | Rechecked after implementation; hashes and source/model evidence preserved |
| Provider spending by reviewer | **0 paid calls** | Python provider cases use mocks; original browser harness disables provider. The later cached-provider capture verifies the exhausted two-call ledger before and after its single request |

The Python command was `python -m pytest tests/qa/test_copilot_integrity.py tests/contract/test_explanation_contract.py -q -p no:cacheprovider --tb=short --basetemp <unique local directory>`. The browser command was `node tests/e2e/copilot.mjs`. Narrow execution escalations were used for already-established Windows temporary-fixture/Chrome process restrictions. An intermediate QA failure was a fixture that omitted the newly required actual provider model field; the fixture was corrected, and the final complete suite passed. It was not counted as a production pass.

The tests cover past-window checksum/lineage conflicts, future-row isolation, final-row null preservation, observed OLS slope, metadata exclusions, prediction-time episode lookup, request evidence/credential injection, missing/conflicting evidence, unsupported diagnoses/commands and prompt injection, forged claim/citation IDs, malformed/refused/incomplete provider responses, response/input limits, redirect/error sanitization, no retry, deterministic fallback, cache separation/revalidation, restart-safe call budgets and concurrent reservations. Exported JSON schemas match Pydantic; explanation input cannot replace prediction evidence. Earlier canonical and diagnostic schema identities remain distinct.

The browser checked replay `5a725349-e2c3-42e9-9dd3-4204ddd3ee7c`, saved event/position recorded in [browser results](../../reports/copilot/qa/browser_results.json). No replay was created, started or controlled. All citation IDs resolved to the actual local source endpoint; returned content and SHA-256 matched the displayed passages. Desktop/mobile screenshots were visually inspected; no horizontal overflow was observed. [Desktop](../../reports/copilot/qa/copilot-desktop.png) and [mobile](../../reports/copilot/qa/copilot-mobile.png) are full-page captures.

NIST's [association/causality passage](https://www.itl.nist.gov/div898/handbook/ppc/section1/ppc136.htm) and [reuse policy](https://www.nist.gov/copyrights-disclaimers) were independently read. The canonical Nature URL redirected to an inaccessible publisher cookie endpoint in the review fetch; indexed article content was available. The LLM owner separately verified the article's actual rights-and-permissions text, rather than inferring an article license from the dataset license; the exact evidence and public URL are documented in [RAG sources](../RAG_SOURCES.md).

Machine-readable results and reviewed source hashes: [verification](../../reports/copilot/qa/verification.json), [immutable-file check](../../reports/copilot/qa/immutable_check.json). The orchestrator records full-project regression and any separately authorized live provider smoke results; these are not implied by the independent mock-provider tests.

## Final cached-provider capture and transport review delta

After the orchestrator's bounded live smoke, `node tests/e2e/copilot_provider.mjs` read the existing result for source row 3619/event 91 using the exact question `show sensor trends`. The harness first read the local ledger in read-only mode and required its hard two-attempt budget to be exhausted. The single UI request returned `status=provider`, `cached=true`, model `gpt-6-luna`, the same evidence hash/approved claims as the saved smoke, and actual recorded usage of 1,331 input / 78 output tokens. The ledger remained two before and after; no direct browser provider request or browser error occurred. This is reuse of an already-generated answer, not another paid completion. The [result](../../reports/copilot/qa/provider_browser_results.json) and visually reviewed [panel screenshot](../../reports/copilot/qa/copilot-provider-cached.png) show the provider/cached state.

The orchestrator reported an initial unavailable attempt followed by a successful 2.811-second attempt after adjusting transport read/write timeouts to four seconds, retaining two-second connect and one-second pool timeouts and the six-second monotonic deadline. Final review prompted an additional deadline check immediately after response headers, before waiting for body data; the change was confirmed in the final source. The fixed endpoint, no redirects/retries, response/input bounds, selection-only schema and hard two-attempt reservation remain intact. The failed attempt supplied no usage, so its billing is unknown; reviewer tests do not establish the account balance. Full final regression and live request evidence belong to the orchestrator's report.

## Residual limits

- The question interface deliberately accepts a small evidence-question vocabulary and abstains on unsupported text; it is not unrestricted domain diagnosis or operations advice.
- The curated corpus has three passages from two public works. Lexical ranking and fixed reviewed interpretations were tested; broad retrieval coverage or multilingual semantic search is not established.
- The provider selects approved IDs; no provider-written factual prose reaches users. Mocked transport/adversarial cases do not prove every live provider/runtime condition. API outage/refusal can validly yield deterministic fallback.
- The local SQLite cache/call ledger bounds retained explanations and attempts across restarts. This is a loopback, trusted-local-files MVP; it is not a tamper-proof billing system against an administrator who deletes or edits the ledger. Two configured attempts are a request limit, not a measured account balance.
- Historical source time remains unverified, missing readings remain unavailable, and the selected uncalibrated binary model remains rejected for monitoring. The copilot cannot validate a physical cause, event family, procedure or control action.
