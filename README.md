# OilWell AI

A production-oriented portfolio MVP for historical oil-well monitoring, ML event detection, telemetry replay and evidence-grounded explanations using the [Petrobras 3W dataset](https://github.com/petrobras/3W).

**Current state: Phase 9 copilot complete.** The [dashboard](http://127.0.0.1:5173/#replay) explains saved historical predictions using verified sensor evidence, licensed citations, explicit abstention and deterministic fallback. Optional server-side OpenAI selects approved claims; it cannot invent values or issue control commands. Verification: **672 Python tests, 25 frontend tests and 11 main browser checks passed**, with a successful bounded live-provider request. See [copilot use and limits](docs/COPILOT.md), [evaluation](reports/llm_evaluation.md), [independent review](docs/reviews/PHASE_9.md) and [progress](docs/PROGRESS.md). The selected model remains rejected for monitoring. The two-attempt API budget is exhausted; new uncached provider requests safely fall back locally. Stop after Phase 9.

The planned stack is Python 3.11+, Pandas/PyArrow, scikit-learn and XGBoost, FastAPI/Pydantic, PostgreSQL, React/TypeScript/Plotly, Docker and pytest. CatBoost is a possible later challenger; ChromaDB is deferred until document retrieval is justified. The LLM provider is optional and disabled by default.

## Design

An offline data/ML pipeline builds versioned artifacts. A dedicated local replay worker thread consumes historical files, runs the frozen diagnostic inference pipeline, and atomically stores predictions, policy state and replay progress in PostgreSQL. FastAPI serves REST snapshots/commands and reconnectable SSE to the dashboard. The copilot explains immutable evidence and can fall back to deterministic summaries.

The candidate first model covers normal plus two undesirable event families, selected only after the data audit establishes usable independent groups. Predictions include the required timestamp, well ID, event type, confidence, model version, sensor evidence and alert status, plus provenance, quality and replay metadata. A closed-set model does not guarantee detection of unsupported events.

3W was verified at dataset **v2.0.0**, commit `914af287b1cf3e5207dce0da1e9dc08361c9adeb`: **Parquet, 27 sensor variables, `class` and `state` labels**. Actual selected files use `float64` sensors and nullable `Int16` labels. Each label has 50,400 unknown values, and four sensors are entirely missing in this subset. Source timezone remains unverified. The [dataset audit](docs/DATASET_AUDIT.md) distinguishes these observations from upstream metadata claims. This project is a historical demo, not a well-control or certified safety system.

## Documents

- [Dashboard startup and flows](docs/FRONTEND.md), [screenshots and verification](reports/frontend/README.md), [UI review](docs/reviews/PHASE_8.md), and [backend contract review](docs/reviews/PHASE_8_BACKEND.md)

- [Historical replay API and reproduction](docs/REPLAY.md), [observed demo and chart](reports/replay/README.md), [QA review](docs/reviews/PHASE_7.md) and [ML consistency review](docs/reviews/PHASE_7_ML.md)

- [Backend startup and examples](docs/BACKEND.md), [typed OpenAPI](docs/openapi.json), [live smoke evidence](reports/backend_smoke.json) and [backend verification](reports/backend_verification.json)
- [Architecture and scope](docs/ARCHITECTURE.md)
- [Milestone graph and acceptance criteria](docs/ROADMAP.md)
- [Current progress and verification](docs/PROGRESS.md)
- [Dataset audit](docs/DATASET_AUDIT.md), [acquisition instructions](data/README.md) and [machine-readable summary](reports/data_summary.json)
- [EDA notebook](notebooks/01_eda.ipynb), [chart and findings guide](reports/eda/README.md), [ML hypotheses](docs/ML_HYPOTHESES.md) and [split strategy](docs/SPLIT_STRATEGY.md)
- [Feature engineering and reproduction](docs/FEATURE_ENGINEERING.md), [preprocessing summary](reports/preprocessing_summary.json) and [development split](data/manifests/development_split.json)
- [Baseline comparison and failures](reports/baseline/README.md), [fixed experiment protocol](reports/baseline/PROTOCOL.md) and [exact validation metrics](reports/baseline/metrics.json)
- [Phase 5 comparison](reports/model_comparison.csv), [final evaluation](reports/final_evaluation.md), [model card](docs/MODEL_CARD.md) and [independent evaluation review](docs/reviews/PHASE_5.md)
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
|-- requirements-baseline.txt
|-- requirements-models.txt
|-- requirements-backend.txt
|-- notebooks/01_eda.ipynb
|-- data/{raw,interim,processed,manifests}/
|-- ml/{data_pipeline,features,training,inference,artifacts,runs}/
|-- ml/{train_baseline.py,evaluate.py,predict.py}
|-- ml/training/phase5.py
|-- backend/app/{main,schemas,settings,errors,pagination,repository,registry,inference}.py
|-- backend/migrations/001_diagnostic_predictions.sql
|-- frontend/src/{components,features,api}/
|-- llm/{evidence,prompts,providers,index}/
|-- tests/{data,ml,backend,frontend,llm,contract,integration,e2e,qa}/
|-- tests/test_data_pipeline.py
|-- tests/test_training.py
|-- scripts/{download_data.py,validate_data.py,prepare_data.py,data/,ml/}
|-- scripts/{run_backend.py,local_postgres.py}
|-- reports/data_summary.json
|-- reports/preprocessing_summary.json
|-- reports/eda/                 # actual-data charts, descriptive CSVs and provenance
|-- reports/baseline/            # validation metrics, figures, protocol and provenance
|-- reports/experiments/         # bounded search, selection and one-shot test evidence
|-- reports/model_comparison.csv
|-- reports/final_evaluation.md
|-- reports/model_selection_verification.json
|-- reports/{backend_smoke,backend_verification}.json
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
    |-- MODEL_CARD.md
    |-- BACKEND.md
    |-- openapi.json
    |-- contracts/{prediction.schema.json,prediction.example.json,diagnostic_prediction.schema.json}
    `-- reviews/{PHASE_0.md,PHASE_1.md,PHASE_2.md,PHASE_3.md,PHASE_4.md,PHASE_5_FEATURES.md,PHASE_5.md,PHASE_6.md}
```

Data acquisition/validation, EDA, preprocessing/features, model selection, internal binary inference and the local diagnostic API/PostgreSQL store are implemented. Raw/processed data, model binaries, database volumes and local credentials remain ignored. The additive diagnostic API is distinct from the planned canonical event-family/replay contract. Continuous replay, frontend, LLM and deployment remain future work.

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

For the fixed baseline comparison, after preprocessing:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-baseline.txt
.\.venv\Scripts\python.exe -m ml.train_baseline
```

The command verifies frozen inputs, fits train only, scores validation only, checks artifact reload, and writes compact reports plus ignored model/prediction bundles. It does not tune thresholds or score test rows. AP and trapezoidal PR-AUC are reported separately; source/family/phase/well support and normal-time alarm occupancy accompany pooled metrics. The [baseline report](reports/baseline/README.md) records observed failures and remaining readiness requirements.

Upstream code is Apache-2.0 and the dataset files are CC BY 4.0. Future acquisition and demo artifacts must preserve Petrobras/3W attribution, source/version and transformation details; the project does not imply endorsement.

## Selected diagnostic artifact

Install `requirements-models.txt` for the Phase 5 environment. The selected local bundle is `ml/artifacts/phase5/c4e1835a82620306778a/`. Load it through `ml.predict.load_bundle`, then call `predict_instance` with one ordered sensor-only instance; exact schema, score and abstention semantics are in the model card. The bundle contains the saved estimator, frozen preprocessing, split, threshold and provenance. It is retained as a failed diagnostic experiment and must not be presented as a reliable monitoring detector.

The bounded search and one selected-model test evaluation are complete. Their CLI commands refuse another search/test attempt once `reports/experiments/test_access.json` exists. Inspect saved reports; do not reset that journal to obtain another test result. Future experiments need a separately approved protocol and suitable independent data. CatBoost inference timing has a documented thread-control deviation; no post-test rerun or model change was made.
