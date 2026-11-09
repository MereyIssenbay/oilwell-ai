# OilWell AI

A production-oriented portfolio MVP for historical oil-well monitoring, ML event detection, telemetry replay and evidence-grounded explanations using the [Petrobras 3W dataset](https://github.com/petrobras/3W).

**Current state: Phase 0 design and scaffolding only.** No telemetry has been downloaded, no model has been trained, and no application or runtime tests exist. Phase 1 is awaiting the user's explicit approval. The files here describe intended behavior; they are not a running demo.

The planned stack is Python 3.11+, Pandas/PyArrow, scikit-learn and XGBoost, FastAPI/Pydantic, PostgreSQL, React/TypeScript/Plotly, Docker and pytest. CatBoost is a possible later challenger; ChromaDB is deferred until document retrieval is justified. The LLM provider is optional and disabled by default.

## Design

An offline data/ML pipeline builds versioned artifacts. A separate replay worker consumes historical files, runs the accepted inference pipeline, and atomically stores predictions, policy state and replay progress in PostgreSQL. FastAPI serves REST snapshots/commands and reconnectable SSE to the dashboard. The copilot explains immutable evidence and can fall back to deterministic summaries.

The candidate first model covers normal plus two undesirable event families, selected only after the data audit establishes usable independent groups. Predictions include the required timestamp, well ID, event type, confidence, model version, sensor evidence and alert status, plus provenance, quality and replay metadata. A closed-set model does not guarantee detection of unsupported events.

3W was verified at dataset **v2.0.0**, commit `914af287b1cf3e5207dce0da1e9dc08361c9adeb`: **Parquet, 27 sensor variables, `class` and `state` labels**. The source timezone is unverified. [Dataset metadata](docs/DATASET_METADATA.md) records exact names, classes, units, identity/origin caveats, attribution and future audit gates. This project is a historical demo, not a well-control or certified safety system.

## Documents

- [Architecture and scope](docs/ARCHITECTURE.md)
- [Milestone graph and acceptance criteria](docs/ROADMAP.md)
- [Current progress and verification](docs/PROGRESS.md)
- [Architecture decisions](docs/DECISIONS.md)
- [API contract](docs/API_CONTRACT.md), [prediction JSON Schema](docs/contracts/prediction.schema.json) and [synthetic abstention example](docs/contracts/prediction.example.json)
- [Engineering rules and ownership](AGENTS.md)

## Repository structure

```text
oilwell-ai/
|-- .codex/
|   |-- config.toml
|   `-- agents/
|       |-- data_engineer.toml
|       |-- ml_engineer.toml
|       |-- backend_engineer.toml
|       |-- frontend_engineer.toml
|       |-- llm_engineer.toml
|       `-- qa_reviewer.toml
|-- AGENTS.md
|-- README.md
|-- .gitignore
|-- .env.example
|-- data/{raw,interim,processed,manifests}/
|-- ml/{features,training,inference,artifacts,runs}/
|-- backend/{app,migrations}/
|-- frontend/src/{components,features,api}/
|-- llm/{evidence,prompts,providers,index}/
|-- tests/{data,ml,backend,frontend,llm,contract,integration,e2e,qa}/
|-- scripts/{data,ml}/
`-- docs/
    |-- ARCHITECTURE.md
    |-- ROADMAP.md
    |-- PROGRESS.md
    |-- DECISIONS.md
    |-- API_CONTRACT.md
    |-- DATASET_METADATA.md
    |-- contracts/{prediction.schema.json,prediction.example.json}
    `-- reviews/
```

Module directories contain only `.gitkeep` placeholders in Phase 0. Root dependency manifests, lockfiles, Docker Compose and startup commands will be added in approved implementation milestones. Do not attempt to launch services yet.

## Agent workflow

The primary orchestrator owns integration, shared contracts, root configuration and phase gates. Six roles own disjoint component/test paths: data engineering, ML, backend/replay, frontend, LLM evidence and independent QA. [AGENTS.md](AGENTS.md) is the persistent ownership reference. Each assignment reserves exact files; subagents do not delegate further.

Project Codex settings enable multi-agent execution with a maximum of **three concurrent subagents**, excluding the primary orchestrator. Role files inherit the active model. TOML parsing and strict CLI configuration loading were checked; all six profiles have not been launched together, and a fresh Codex session may be needed to load changes.

## Next approved step

After explicit Phase 1 approval: set up pinned project tooling, select and acquire a documented 3W subset, verify checksums and attribution, inspect its actual Parquet schema and quality, and freeze source/scope/split manifests. Do not train a model during that data-foundation phase. `.env.example` documents proposed local configuration only; credentials are blank, and `.env` is ignored.

Upstream code is Apache-2.0 and the dataset files are CC BY 4.0. Future acquisition and demo artifacts must preserve Petrobras/3W attribution, source/version and transformation details; the project does not imply endorsement.
