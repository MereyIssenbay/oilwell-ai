# Historical alert copilot

The copilot explains saved predictions. It does not diagnose a physical event, infer causality, prescribe procedures, change replay/alerts or issue equipment commands. The selected binary detector remains rejected for monitoring, and its confidence remains uncalibrated.

## Local use

Start the existing PostgreSQL service and API as described in [BACKEND.md](BACKEND.md). For the dashboard proxy, run `.venv\Scripts\python.exe scripts/run_backend.py --port 8001`, then `npm run dev` in `frontend/`. Open `http://127.0.0.1:5173/#replay`, select a saved replay and prediction, and press **Explain alert**. Default requests are entirely local. Questions can request readings, trends, missing data and confidence; the panel lists supported phrasing. Unsupported questions receive an explicit abstention.

The reproduced saved case is replay `5a725349-e2c3-42e9-9dd3-4204ddd3ee7c`. Run `.venv\Scripts\python.exe scripts/copilot_demo.py` to verify saved prediction fields, local citation content/checksums, cached repetition and unsupported-control abstention. This does not generate new predictions or control replay. See [API smoke evidence](../reports/copilot/api_smoke.json).

## Optional server-only provider

Environment defaults are `LLM_PROVIDER=disabled`, `LLM_MODEL=gpt-6-luna`, `LLM_MAX_CALLS=2`. For an intentional external request, export `LLM_PROVIDER=openai` and `OPENAI_API_KEY` into the API process. Alternatively, use `scripts/run_backend.py --port 8001 --llm-config .local/copilot/provider.json`; the optional ignored JSON maps those variable names to strings. Existing process environment takes precedence. The root `.env.example` is documentation, not an automatically loaded file. No browser environment variable receives a key.

The provider is an implementation of `Provider.select(payload)`. The OpenAI adapter uses the fixed official Responses endpoint, strict structured JSON, `store=false`, no tools, no redirects/proxy inheritance, no retries and reasoning effort `none`. The current economical model was verified in [official model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna) on 2026-11-10. Its public ID is an alias; the returned model ID and token counts are retained when a response succeeds. The implementation follows [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). A model alias is not a reproducible frozen provider snapshot.

The local maximum is **two paid attempts for the lifetime of the cache database**, including network failures. `LLM_MAX_CALLS` can reduce this to 0 or 1, never raise it beyond 2. Reservation happens before network access. The durable counter is `.local/copilot/cache.sqlite3`; restarting the API does not reset it. Do not delete it to bypass the budget. Other applications/account activity are outside this counter, and the application cannot see the account balance.

Requests cap the evidence payload at 12,000 UTF-8 bytes, output at 400 tokens and received response at 64 KiB. HTTP read/write timeout is 4 seconds, connect timeout 2 seconds and pool timeout 1 second, with a six-second elapsed deadline checked across chunks; a final blocked read can add up to four seconds. This is an application transport bound, not an OS-level DNS deadline guarantee. Two endpoint slots bound concurrent explanations. The cache holds at most 128 entries with one-hour validity. Identical requests are serialized and reused within the local single-service process; multi-process cache misses may each reserve one of the two lifetime attempts. Raw questions, credentials and provider prose are never logged or cached. Typed evidence and server-rendered explanation text are cached locally.

Official standard text prices observed on 2026-11-10 were $0.10 input and $0.50 output per million tokens. Any token-based cost figure in verification is an estimate using that tariff, not an account bill or balance check. There are no embeddings, hosted retrieval, tools or background paid evaluations. UI paid-provider opt-in is explicit and unchecked by default. Disabled provider, invalid output, exhausted budget or network errors return deterministic output with the reason visible.

## Evidence and retrieval

The backend verifies the exact stored raw-window checksum and model/source/preprocessing identity, timestamps, means, units and missing fractions. It then derives endpoint readings and OLS trends from only that same causal window. A final missing reading stays null; no backward fill or later recovery is used. The provider never sees source filenames/paths/IDs, well IDs, original `class`/`state`, split membership, ground truth or later episode outcomes. Synchronous predictions have unknown episode state; replay predictions use their immutable captured episode state.

Six deterministically selected sensor summaries are narrated; all 27 typed sensor entries remain available in the response and panel. Their ordering is not importance or causal attribution. General technical interpretations come from reviewed templates tied to exact licensed source content. A lexical index retrieves three curated passages without ChromaDB or embedding costs. [RAG_SOURCES.md](RAG_SOURCES.md) records URLs, licenses, attributions and limitations.

The provider selects only supplied claim/citation identifiers. Python rejects unknown/duplicate IDs, unrelated citations, free prose and malformed/incomplete output; it renders all numerical statements from the saved packet. Retrieved prose is untrusted: a reviewed catalog hash and source metadata checks prevent substituted content from becoming approved interpretation. Cached results are checked against regenerated factual claims and current evidence before reuse. These controls narrow the supported question surface; they do not constitute unrestricted natural-language QA or a safety certification.

## Verification

Run `python scripts/export_api.py` to export additive schemas/OpenAPI, and `npm run generate:api` in `frontend/` to regenerate TypeScript. Offline tests use explicit fake providers and never paid calls. The live demo's `--use-provider` option intentionally requests one budgeted provider result and verifies the repeat is cached; it must not be part of an automated test loop. Exact completed checks and limitations are recorded in [PROGRESS.md](PROGRESS.md), [LLM evaluation](../reports/llm_evaluation.md), and [independent review](reviews/PHASE_9.md).
