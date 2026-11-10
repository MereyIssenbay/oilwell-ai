# Read-only alert copilot

`CopilotService.explain(EvidencePacket, question='', use_provider=False)` returns the Pydantic `Explanation` contract. The backend assembles the packet from a persisted prediction and a verified causal source window; this package has no model fitting, inference, target-label loader, plant controller or database access to replay state.

The optional provider selects approved observation/interpretation/citation IDs. All displayed numerical sentences are rendered by Python from typed evidence. Confidence remains uncalibrated, the selected model remains rejected for monitoring, and every explanation is historical/diagnostic. Means, endpoint readings and OLS trends describe observations; they are not SHAP values or proof of which sensor caused a decision.

Supported questions include `Explain this alert`, `What did the model observe?`, `Show sensor trends`, `What data is missing?` and `Explain the score`. Case, whitespace and terminal punctuation are normalized. A few Russian equivalents are supported. Unsupported diagnoses, control requests, future outcomes, prompt injection and other unrecognized questions abstain locally. The provider receives only the recognized intent, never raw user question text.

Public references and reuse terms are in [RAG_SOURCES.md](../docs/RAG_SOURCES.md). The local corpus has three reviewed paragraphs; lexical retrieval uses no paid embeddings. Claims refer to packet-local sensor IDs `eN`; reserved IDs are `p1` prediction/threshold/confidence, `m1` model/scope, `w1` causal window/time basis, `r1` episode state captured at prediction and `h1` historical mode/source origin. The provider sees at most six observation candidates. The response preserves the complete packet, so this subset is not mistaken for complete sensor coverage.

Server configuration:

| Environment | Default | Meaning |
| --- | --- | --- |
| `LLM_PROVIDER` | `disabled` | `disabled` or `openai`; explicit request `use_provider=true` is also required |
| `OPENAI_API_KEY` | empty | Server-side only; never put it in frontend/Vite variables or Git |
| `LLM_MODEL` | `gpt-6-luna` | Reviewed economical Responses model alias; arbitrary model names and provider URLs are rejected |
| `LLM_MAX_CALLS` | `2` | Conservative **lifetime** reservation cap, range 0..2, across restarts; failed requests also consume a reservation |

SQLite state under ignored `.local/copilot/cache.sqlite3` stores only bounded explanation cache entries and the paid-call counter. It stores no API key, raw question or raw prompt. Cache keys include packet, question hash, provider choice/configured model, knowledge version and prompt version. Entries expire after one hour; at most 128 are retained. Before reuse, cached factual claims, citations and evidence are checked against a freshly constructed deterministic explanation. Invalid cache data produces fresh deterministic output without another paid call. The lifetime counter never resets on cache expiration; removing its file would remove that limit and must be an explicit operator action.

Transport uses a fixed `https://api.openai.com/v1/responses`, `store=false`, no tools, redirects, environment proxy or retry. Input JSON is capped at 12,000 UTF-8 bytes; output at 400 model tokens and 65,536 response bytes. Connect/pool timeouts are two/one seconds, read/write timeouts four seconds, and a six-second monotonic chunk deadline bounds a trickling response to approximately ten seconds including the final blocked read. Disabled credentials, HTTP errors, timeout, budget exhaustion, refusal/incomplete output or ungrounded IDs produce a safe deterministic response/status. The code never surfaces provider exception text.

The [official Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) documents Responses `text.format` with strict JSON Schema; [the reviewed model page](https://developers.openai.com/api/docs/models/gpt-6-luna) supports the configured model and reasoning `none`. Model aliases can change; returned provider model identity and actual token usage are recorded when a valid response is available. As checked by the orchestrator on 2026-11-10, listed standard text rates were $0.10/input million tokens and $0.50/output million tokens. These are estimates for budgeting, not account billing evidence or a balance check. Two capped calls are far below the user's $5 ceiling under those rates. Automated tests never call the paid API.

Run offline checks from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest tests/llm -q -p no:cacheprovider
```

The [versioned evaluation set](evaluation_cases.json) contains explicit synthetic fixtures, never claimed as real oil-well observations. Actual persisted-prediction integration and browser checks are owned by the orchestrator and independent QA.
