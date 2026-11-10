# OilWell AI

A production-oriented portfolio MVP for historical oil-well monitoring, ML event detection, telemetry replay and evidence-grounded explanations using the [Petrobras 3W dataset](https://github.com/petrobras/3W).

**Current state: Phase 3 reproducible preprocessing complete.** The acquired 23-file subset now has an executed EDA notebook, eight actual-data charts, five testable hypotheses, deterministic grouped diagnostic partitions and a causal feature pipeline with training-only imputation/normalization. The default real-only run produces 32,197 windows and 120 retained features. All 141 data/EDA/pipeline tests passed. No event detector has been trained. Current verification and phase status are recorded in [PROGRESS.md](docs/PROGRESS.md). Further work requires a new phase approval.

The planned stack is Python 3.11+, Pandas/PyArrow, scikit-learn and XGBoost, FastAPI/Pydantic, PostgreSQL, React/TypeScript/Plotly, Docker and pytest. CatBoost is a possible later challenger; ChromaDB is deferred until document retrieval is justified. The LLM provider is optional and disabled by default.

## Design

An offline data/ML pipeline builds versioned artifacts. A separate replay worker consumes historical files, runs the accepted inference pipeline, and atomically stores predictions, policy state and replay progress in PostgreSQL. FastAPI serves REST snapshots/commands and reconnectable SSE to the dashboard. The copilot explains immutable evidence and can fall back to deterministic summaries.

The candidate first model covers normal plus two undesirable event families, selected only after the data audit establishes usable independent groups. Predictions include the required timestamp, well ID, event type, confidence, model version, sensor evidence and alert status, plus provenance, quality and replay metadata. A closed-set model does not guarantee detection of unsupported events.

3W was verified at dataset **v2.0.0**, commit `914af287b1cf3e5207dce0da1e9dc08361c9adeb`: **Parquet, 27 sensor variables, `class` and `state` labels**. Actual selected files use `float64` sensors and nullable `Int16` labels. Each label has 50,400 unknown values, and four sensors are entirely missing in this subset. Source timezone remains unverified. The [dataset audit](docs/DATASET_AUDIT.md) distinguishes these observations from upstream metadata claims. This project is a historical demo, not a well-control or certified safety system.

## Documents

- [Architecture and scope](docs/ARCHITECTURE.md)
- [Milestone graph and acceptance criteria](docs/ROADMAP.md)
- [Current progress and verification](docs/PROGRESS.md)
- [Dataset audit](docs/DATASET_AUDIT.md), [acquisition instructions](data/README.md) and [machine-readable summary](reports/data_summary.json)
- [EDA notebook](notebooks/01_eda.ipynb), [chart and findings guide](reports/eda/README.md), [ML hypotheses](docs/ML_HYPOTHESES.md) and [split strategy](docs/SPLIT_STRATEGY.md)
- [Feature engineering and reproduction](docs/FEATURE_ENGINEERING.md), [preprocessing summary](reports/preprocessing_summary.json) and [development split](data/manifests/development_split.json)
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
|-- requirements-data.txt
|-- requirements-eda.txt
|-- requirements-pipeline.txt
|-- notebooks/01_eda.ipynb
|-- data/{raw,interim,processed,manifests}/
|-- ml/{data_pipeline,features,training,inference,artifacts,runs}/
|-- backend/{app,migrations}/
|-- frontend/src/{components,features,api}/
|-- llm/{evidence,prompts,providers,index}/
|-- tests/{data,ml,backend,frontend,llm,contract,integration,e2e,qa}/
|-- tests/test_data_pipeline.py
|-- scripts/{download_data.py,validate_data.py,prepare_data.py,data/,ml/}
|-- reports/data_summary.json
|-- reports/preprocessing_summary.json
|-- reports/eda/                 # actual-data charts, descriptive CSVs and provenance
`-- docs/
    |-- ARCHITECTURE.md
    |-- ROADMAP.md
    |-- PROGRESS.md
    |-- DECISIONS.md
    |-- API_CONTRACT.md
    |-- DATASET_METADATA.md
    |-- DATASET_AUDIT.md
    |-- ML_HYPOTHESES.md
    |-- SPLIT_STRATEGY.md
    |-- FEATURE_ENGINEERING.md
    |-- contracts/{prediction.schema.json,prediction.example.json}
    `-- reviews/{PHASE_0.md,PHASE_1.md,PHASE_2.md,PHASE_3.md}
```

Data acquisition/validation, descriptive EDA and reusable preprocessing/features are implemented, with manifests, reports and tests. Original and processed data remain ignored. ML training/inference, backend, frontend and LLM directories remain placeholders. Docker Compose and application startup commands belong to later approved milestones. Do not attempt to launch services yet.

## Agent workflow

The primary orchestrator owns integration, shared contracts, root configuration and phase gates. Six roles own disjoint component/test paths: data engineering, ML, backend/replay, frontend, LLM evidence and independent QA. [AGENTS.md](AGENTS.md) is the persistent ownership reference. Each assignment reserves exact files; subagents do not delegate further.

Project Codex settings enable multi-agent execution with a maximum of **three concurrent subagents**, excluding the primary orchestrator. Role files inherit the active model. TOML parsing and strict CLI configuration loading were checked; all six profiles have not been launched together, and a fresh Codex session may be needed to load changes.

## Reproduce the data audit

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe scripts/download_data.py
.\.venv\Scripts\python.exe scripts/download_data.py --offline
.\.venv\Scripts\python.exe scripts/validate_data.py
```

The saved manifest fixes the exact bounded selection. Original files are hash-verified and never silently replaced. The audit is size-biased; later approved work must establish sufficient independent real groups and row-label coverage before a model evaluation. `.env.example` remains proposed application configuration with blank credentials; the data scripts need no secrets.

For EDA, install `requirements-eda.txt` into the same project environment and follow the [reproduction instructions](reports/eda/README.md). Descriptive class/run summaries and plot-only unit scaling do not modify source files or provide trained features. The publisher's stable real `WELL` IDs support grouping across event directories. All 23 inspected files and their 12 real well IDs are development-exposed; a future final evaluation must reserve fresh groups. Current per-family well support is insufficient for the planned multiclass train/validation/test split.

For preprocessing:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
.\.venv\Scripts\python.exe scripts/prepare_data.py
```

The default diagnostic split preserves whole published well groups, excludes synthetic sources, computes trailing-window features and fits preprocessing statistics only on train. Versioned manifests/reports describe the result; separate features, targets, provenance, quality and fitted preprocessing JSON live under ignored `data/processed/phase3/`. Its validation/test names do not imply an untouched final holdout. See [feature engineering](docs/FEATURE_ENGINEERING.md) for policies, configurable settings, limitations and checks.

Upstream code is Apache-2.0 and the dataset files are CC BY 4.0. Future acquisition and demo artifacts must preserve Petrobras/3W attribution, source/version and transformation details; the project does not imply endorsement.
