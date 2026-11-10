# 3W audit data

Phase 1 acquired and inspected a bounded audit subset on 2026-11-10. Original Parquet files are unchanged and ignored by Git. There is no preprocessing, feature creation, imputation, timestamp conversion, label rewriting, training or train/validation/test split.

## Source and reproducibility

- Source: [Petrobras/3W](https://github.com/petrobras/3W), dataset version **2.0.0**.
- Immutable Git revision: `914af287b1cf3e5207dce0da1e9dc08361c9adeb`.
- [subset.json](manifests/subset.json) records the exact selection, original source paths, local destinations, Git blob SHA-1, SHA-256, sizes and origin/identity metadata. Do not edit its source/hash values to bypass integrity failures.
- [dataset_metadata.json](manifests/dataset_metadata.json) is a derived registry of the byte-verified upstream `dataset.ini`. It records sensor/label separation and metadata semantics, not transformed telemetry.
- Raw layout: `data/raw/3w/2.0.0/<revision>/<original repository path>`. Eight upstream provenance documents are retained there with the same integrity checks, including both license files, `dataset.ini`, structure/release documentation and the source of the official download helper.

The downloader is standard-library Python 3.11+ with no import-time I/O. The repository's [requirements-data.txt](../requirements-data.txt) pins the audit environment; Pandas/PyArrow are needed for inspection/validation, not for downloading. Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe scripts/download_data.py --dry-run
.\.venv\Scripts\python.exe scripts/download_data.py
.\.venv\Scripts\python.exe scripts/download_data.py --offline
.\.venv\Scripts\python.exe scripts/validate_data.py
```

On POSIX systems, use `.venv/bin/python` in place of `.venv\Scripts\python.exe`. A fresh download requires HTTPS access to `api.github.com` for pinned-tree discovery and `raw.githubusercontent.com` for the selected files. A saved manifest eliminates discovery calls. `--offline` performs no network calls or writes and fails if any expected source is absent or inconsistent. `--dry-run` reports the plan without downloading telemetry or writing files; if no manifest exists it fetches only Git tree metadata.

Existing original files are reused only after size, pinned Git blob hash and recorded SHA-256 agree. Conflicting bytes cause failure, never silent replacement. New original files are verified before being atomically published without clobbering an existing destination. The manifest checkpoints completed hashes so interrupted acquisitions can resume. A normal rerun rechecks every original; the verified Phase 1 rerun preserved all 31 source-document/data hashes and modification times.

The successful first acquisition required the execution environment's approved network escalation because its sandbox refused HTTPS connections. This is an environment restriction, not a dataset access/paywall blocker. The script itself uses ordinary public HTTPS and needs no credentials. Network retries, timeout and response size are bounded; malformed plans, path traversal, hash mismatches and incomplete downloads fail clearly.

## Selection and limits

The complete pinned Git tree lists 2,228 Parquet files (1,873,131,359 bytes) across 19 available event-directory/origin combinations. The selection deterministically takes the smallest file in each combination, with source-path ordering to break ties, then four additional files introducing distinct real well identifiers. Hard limits are 30 data files and 100 MiB including the provenance documents. No full archive or clone was downloaded.

| Acquired scope | Observed amount |
| --- | ---: |
| Parquet files | 23 |
| Original Parquet bytes | 10,719,108 |
| Provenance documents / bytes | 8 / 58,535 |
| Real / simulated / hand-drawn files | 14 / 7 / 2 |
| Distinct real anonymized well identifiers in subset | 12 |
| Available class/origin strata covered | 19 of 19 |
| Rows read by Pandas/PyArrow | 582,220 |

This is a **purposive, size-biased inspection subset**, not a statistically representative prevalence sample, modeling cohort or evidence of generalization. Smaller compressed files can favor shorter, simpler or more missing signals. Directory coverage does not guarantee all row labels, transient phases or operational states are present. The selected files do not establish sufficient independent real groups per event for model evaluation.

The official toolkit also supports full dataset version downloads from Figshare: version 2.0.0 maps to article `29205836` and a published archive SHA-256 in the [pinned helper](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/toolkit/ThreeWToolkit/utils/downloader.py). Repository clone/archive and official toolkit acquisition are alternatives, but were not used because this task needs only a small subset. Do not instantiate an upstream loader that may automatically download a complete dataset.

## Actual schema versus documentation

All 23 files read successfully with Pandas 2.2.3 and PyArrow 26.0.1. Each has 30 Arrow fields: 27 sensor fields, `class`, `state`, and `timestamp`. Pandas restores `timestamp` as the named index and exposes 29 columns.

| Category | Actual selected-file representation | Role |
| --- | --- | --- |
| 27 sensor columns | Arrow double; Pandas `float64`, missing values represented as NaN | Only these exact upstream names are candidate sensor features |
| `class` | Arrow signed int16; Pandas nullable `Int16` | Per-observation target label; never a sensor feature |
| `state` | Arrow signed int16; Pandas nullable `Int16` | Operational-status auxiliary label; never a sensor feature |
| `timestamp` | Arrow `timestamp[ns]`; Pandas naive `DatetimeIndex`, named `timestamp` | Observation index; source timezone is unverified |
| Path/directory/origin/well/instance IDs | Manifest metadata | Provenance/grouping only; never prediction features |

Upstream structure documentation describes nullable `Float64` and `Int64`; the inspected files instead use `float64` and nullable `Int16`. Preserve the original files and report the difference rather than coercing them to the documentation. The original timestamps remain timezone-naive; this audit does not localize them or assert UTC.

The sensor allowlist and original unit/domain descriptions are in [dataset_metadata.json](manifests/dataset_metadata.json) and the [metadata baseline](../docs/DATASET_METADATA.md). Do not select all numeric columns: doing so includes both labels. Numeric source identifiers, event-directory names, filenames and origin/missingness patterns can also leak identity or targets. Anonymized well IDs are upstream grouping hints, not verified physical well identities.

## Labels, origins and observed limitations

`class` base codes 0-9 map to the exact names in `dataset.ini`: normal; abrupt increase of BSW; spurious closure of DHSV; severe slugging; flow instability; rapid productivity loss; quick restriction in PCK; scaling in PCK; hydrate in production line; hydrate in service line. The transient codes are **101, 102, 105, 106, 107, 108, 109**. Do not accept arbitrary code-minus-100 mappings. Null means unknown/unlabeled, not normal. A directory names the instance context and does not assign every row's target. No target mapping is applied to the raw files in Phase 1.

The author manuscript's [state table](https://arxiv.org/html/2507.01048v1#S2.T5) defines: 0 Open, 1 Shut-In, 2 Flushing Diesel, 3 Flushing Gas, 4 Bullheading, 5 Closed With Diesel, 6 Closed With Gas, 7 Restart, 8 Depressurization; null is Unknown. `dataset.ini` itself only says “Well operational status,” so the derived ini registry intentionally does not pretend the code dictionary came from that file. The audit/report records the independently sourced mapping.

Origins are determined from exact source filenames: `WELL-...` real, `SIMULATED_...` simulated, `DRAWN_...` hand-drawn. The filename prefix before the first underscore is retained as `well_identifier` only for real instances. Synthetic instance numbers restart across event directories and are not well IDs. `source_instance_id` is `3w:` plus SHA-256 of `<revision>:<full source_path>`, ensuring path/revision-scoped identity. Source origin remains distinct from a future application replay mode.

Observed audit limitations:

- `class` and `state` each contain **50,400 null rows**. Each of the 14 selected real files has a 3,600-row initial unlabeled interval. This contradicts treating the release-note statement about closing label gaps as proof of complete labels in this pinned subset. No labels were filled or inferred.
- Event 7's selected instances contain normal/transient rows but no steady code `7`; transient `107` is present. Never infer steady-class coverage from directory names.
- `P-JUS-BS`, `P-MON-SDV-P`, `PT-P` and `QBS` are entirely missing across this subset. Many other columns have high or origin-dependent missingness. Complete missingness/class/state tables and per-instance checks are in [data_summary.json](../reports/data_summary.json).
- All selected timestamps were monotonic and had no duplicate index values. This does not prove global temporal independence or absence of overlapping/near-duplicate source segments outside the subset.
- Upstream simulated and hand-drawn instances have structurally missing channels; real data also has unavailable channels. Missingness can identify source origin, producing an easy but misleading classifier if origins are mixed without design controls.
- Before future modeling, keep whole related well/instance groups together, inspect overlaps and duplicates, choose labels from row targets, fit learned transforms only on training data, and keep real holdout evaluation separate from any synthetic augmentation. No split or model-scope approval is established here.

The consolidated [dataset audit](../docs/DATASET_AUDIT.md) and [machine-readable summary](../reports/data_summary.json) distinguish metadata claims from measured subset evidence. Their warnings are audit findings, not repaired data.

## License and attribution

The upstream [README license section](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/README.md#licenses) licenses dataset Parquet files under **CC BY 4.0** and repository code under **Apache-2.0**. Exact original `dataset/LICENSE-CC-BY`, `LICENSE.md` and `CITATION.md` are preserved among the downloaded provenance documents. Attribution: **Petrobras and the 3W contributors, 3W Dataset v2.0.0**, pinned revision and source link above. This acquisition makes no transformations to the source files. Selection and audit summaries are project outputs, and no Petrobras endorsement is implied.
