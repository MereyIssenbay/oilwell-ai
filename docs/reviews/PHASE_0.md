# Independent Phase 0 review

Reviewed on 2026-11-09. Scope: architecture, ownership, metadata accuracy, canonical prediction semantics, replay/alert continuity, copilot evidence boundaries, and truthful completion claims. This is a static design review, not a runtime acceptance test.

## Files reviewed

- `AGENTS.md`, `README.md`, `.env.example`, `.gitignore`.
- `.codex/config.toml` and all six `.codex/agents/*.toml` profiles.
- `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/API_CONTRACT.md`, `docs/DATASET_METADATA.md`.
- `docs/contracts/prediction.schema.json` and `prediction.example.json`.

Dataset claims were compared with the pinned upstream documentation, configuration, loader source and Git tree reviewed for the [metadata baseline](../DATASET_METADATA.md). No telemetry records were inspected.

## Findings and resolution

| Finding | Original concern | Verified design resolution |
| --- | --- | --- |
| Alert continuity | Ongoing policy state was persisted but absent from the API read model. An abstaining prediction could obscure an earlier active alert after reconnect. | The [API contract](../API_CONTRACT.md) now defines nullable `alert_episode` in snapshots, replay-state payloads and ordered episode transition events. It separates current prediction status from active/recovering episodes, retains transition history and requires episode state to be captured at each prediction transaction. Historical explanations use that captured state without later outcomes. Architecture, M5 acceptance and ADR-018 agree. |
| Indirect ground-truth leakage | Canonical `provenance.source_path` contains the event-class directory; forwarding a complete record to the provider could reveal the target. | Provider input now uses an explicit field allowlist. Whole prediction/raw-manifest serialization is prohibited; class-bearing paths, filenames/identifiers, labels, split assignments and future outcomes are excluded. Linkage uses opaque packet-local tokens. The model's declared supported-class list remains legitimate scope metadata. Persistent rules, architecture, M6 acceptance and ADR-019 agree. |

Both findings are resolved at the design level. Their later implementation must satisfy the documented contract and acceptance tests.

## Verification actually performed

Read-only PowerShell inspection used `Get-Content` and `rg -n -C 3` to compare the affected documents and verify the revisions. A Python script, passed through PowerShell to `python -`, performed these checks:

| Check | Observed result |
| --- | --- |
| Parse `.codex/**/*.toml` using `tomllib.loads` | PASS: 7 files |
| Required canonical fields are in the schema's `required` list | PASS: timestamp, well_id, event_type, confidence, model_version, sensor_evidence, alert_status |
| Count exact sensor-name enum entries | 27; matches the reviewed upstream registry |
| `Draft202012Validator.check_schema(schema)` | PASS |
| `Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)` | PASS: explicitly synthetic abstention example |

The orchestrator's broader integration checks and CLI configuration-loading evidence are recorded separately in [PROGRESS.md](../PROGRESS.md); they are not represented here as independently repeated checks.

## Limitations and disposition

No additional Phase 0 blocker was found after the two corrections. Required role boundaries, milestone gates, source provenance, simulation/replay distinction and dataset metadata are consistent. The repository correctly describes model quality, API behavior, deployment and application tests as future work.

Static checks do not validate temporal/registry invariants, live Codex role activation, actual Parquet contents, model performance, replay recovery or provider grounding. No application tests, data acquisition, training or product implementation were performed. Source timezone, usable independent well groups, class scope and data quality remain Phase 1 audit questions. Phase 1 still requires the user's explicit approval.
