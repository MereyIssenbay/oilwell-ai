# 3W metadata baseline

Verified on 2026-11-09 from upstream documentation, configuration, loader source and Git tree metadata only. No telemetry files were downloaded or inspected. These findings are the acquisition specification, not a completed data audit.

**Phase 1 update, 2026-11-10:** the [measured audit](DATASET_AUDIT.md) now covers 23 original files. Their actual types are Pandas `float64` sensors, nullable `Int16` labels and a naive `datetime64[ns]` index, differing from the prose below. It also found 50,400 null values in each label and four entirely missing sensor columns. This document retains the Phase 0 metadata baseline; measured subset findings and limitations take precedence over assumptions about actual bytes.

## Version and authoritative sources

- Repository: [petrobras/3W](https://github.com/petrobras/3W).
- Pinned commit: `914af287b1cf3e5207dce0da1e9dc08361c9adeb` (2026-11-07).
- Dataset version: **2.0.0**, from [dataset.ini](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/dataset/dataset.ini). Dataset, toolkit and repository release versions are distinct.
- [Structure specification](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/3W_DATASET_STRUCTURE.md), [dataset release notes](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/dataset/README.md), [loader implementation](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/toolkit/ThreeWToolkit/dataset/parquet_dataset.py).
- [Dataset descriptor](https://www.nature.com/articles/s41597-026-07225-z) provides identity, sampling and timestamp context. [Citation guidance](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/CITATION.md) and [repository licensing](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/README.md) govern future attribution.

## Storage and observation schema

Instances live in `dataset/0/` through `dataset/9/`, one Parquet file per instance, written using pyarrow/Brotli. The documented index is `timestamp`; documentation describes 27 nullable `Float64` sensor variables and nullable `Int64` labels. Phase 1 instead measured Arrow double/Pandas `float64` sensors and Arrow int16/Pandas `Int16` labels in every selected file, with a physical `timestamp[ns]` field restored as the named index. No coercion was applied.

| Documented unit/domain | Exact upstream sensor columns |
| --- | --- |
| Percent | `ABER-CKGL`, `ABER-CKP` |
| Valve state: 0, 0.5, 1 | `ESTADO-DHSV`, `ESTADO-M1`, `ESTADO-M2`, `ESTADO-PXO`, `ESTADO-SDV-GL`, `ESTADO-SDV-P`, `ESTADO-W1`, `ESTADO-W2`, `ESTADO-XO` |
| Pa | `P-ANULAR`, `P-JUS-BS`, `P-JUS-CKGL`, `P-JUS-CKP`, `P-MON-CKGL`, `P-MON-CKP`, `P-MON-SDV-P`, `P-PDG`, `PT-P`, `P-TPT` |
| m³/s | `QBS`, `QGL` |
| °C (upstream spelling `oC`) | `T-JUS-CKP`, `T-MON-CKP`, `T-PDG`, `T-TPT` |

Preserve case and original names. `dataset.ini` escapes percent as `%%`; a future ConfigParser reader must preserve case (`optionxform = str`). Metadata unit aliases may be normalized for transport, with original units recorded in the manifest. Do not infer physical meanings or engineering limits from column names.

Version 2 removed `T-JUS-CKGL`, added 20 variables and added event 9. The descriptor states that the 20 added variables are unavailable in simulated/drawn instances. The historical eight-variable CSV schema must not be used as the ingestion contract.

## Labels

`class` is the per-observation event label. The enclosing directory supplies instance-level context, not the ground truth of every row. `state` is an operational-status label. The [Phase 1 audit](DATASET_AUDIT.md) confirms its 0-8 code mapping from the primary author manuscript; the ini itself does not contain that mapping. Neither label belongs in sensor features.

| Base code | Exact upstream event name | Valid transient code | Canonical `event_type` |
| --- | --- | --- | --- |
| 0 | `NORMAL` | None | `normal` |
| 1 | `ABRUPT_INCREASE_OF_BSW` | 101 | `abrupt_increase_of_bsw` |
| 2 | `SPURIOUS_CLOSURE_OF_DHSV` | 102 | `spurious_closure_of_dhsv` |
| 3 | `SEVERE_SLUGGING` | None | `severe_slugging` |
| 4 | `FLOW_INSTABILITY` | None | `flow_instability` |
| 5 | `RAPID_PRODUCTIVITY_LOSS` | 105 | `rapid_productivity_loss` |
| 6 | `QUICK_RESTRICTION_IN_PCK` | 106 | `quick_restriction_in_pck` |
| 7 | `SCALING_IN_PCK` | 107 | `scaling_in_pck` |
| 8 | `HYDRATE_IN_PRODUCTION_LINE` | 108 | `hydrate_in_production_line` |
| 9 | `HYDRATE_IN_SERVICE_LINE` | 109 | `hydrate_in_service_line` |

The transient offset is 100 **only for events whose metadata enables transients**. Do not apply modulo arithmetic to arbitrary labels. `EXTRA_INSTANCES_TRAINING=-1` is a configuration setting, not an event code. Keep raw labels, event family and source label phase separately. Null/unrecognized labels are excluded from supervised targets and remain visible in quality reports; they are never recoded as normal. `unknown` is our abstention output, not a 3W class.

MVP target policy: predict the event family at the causal window end; map valid transient/steady labels to the same family for the initial classifier, retain phase for separate evaluation, and do not claim to predict event phase. Only normal and event families explicitly admitted by the Phase 1 scope manifest may be trained or emitted. Unsupported families are excluded from the closed-set training/evaluation cohort and must not be portrayed as reliably recognized at runtime.

## Identity, time and provenance

Origin is encoded in filenames: `WELL` (real), `SIMULATED`, or `DRAWN`. Metadata examples include `dataset/0/WELL-00001_20170201010207.parquet`, `dataset/1/SIMULATED_00001.parquet`, and `dataset/1/DRAWN_00001.parquet`.

Real anonymized well identifiers are shared across event directories according to the descriptor. Synthetic incremental identifiers restart within each event directory. Therefore:

- `source_instance_id` derives from pinned revision plus the full relative source path; filenames alone are insufficient.
- Real `well_id` is namespaced as `3w:2.0.0:real:WELL-00001`; it denotes an upstream anonymized identifier, not a verified physical asset.
- Simulated/drawn `well_id` uses `3w:2.0.0:<origin>:<instance-digest>` and `well_identity_kind=synthetic_instance`. It must never be presented as a real well.
- Source origin and application execution mode are independent. Replaying a real file has `source_kind=real` and `mode=historical_replay`.

The descriptor documents 1 Hz observations and historical interpolation in the source system. Timestamp strings have no explicit offset; **no source timezone was verified**. Validate monotonicity, duplicates, gaps and actual intervals after acquisition. The initial adapter retains the original timestamp string and maps its numeric clock to a UTC-tagged transport coordinate only with `time_basis=source_naive_assumed_utc`; this is an explicit coordinate convention, not a claim about physical UTC. Never silently convert to the workstation timezone. Upstream interpolation is part of provenance; any further project preprocessing must remain causal.

## Metadata inventory (not profiling)

The complete pinned recursive Git tree (`truncated=false`) contains 2,228 paths matching `dataset/<class>/*.parquet`: 1,119 real, 1,089 simulated and 20 drawn. Counts by directory are shown below. They count files, not rows, usable windows, independent physical wells or event prevalence.

| Directory | Files |
| --- | ---: |
| 0 | 594 |
| 1 | 128 |
| 2 | 38 |
| 3 | 106 |
| 4 | 343 |
| 5 | 450 |
| 6 | 221 |
| 7 | 46 |
| 8 | 95 |
| 9 | 207 |

## Acquisition and leakage gates

Do not instantiate the upstream loader during Phase 0: it can automatically download missing files even when `force_download=False`. Its default `load_file` removes only `class`; `state` can remain in the feature matrix. Our adapter must explicitly allowlist sensor variables and exclude `class`, `state`, file/directory names, well identifiers and origin indicators from prediction features.

Phase 1 audited actual schema, timestamp ordering, row-label support, missingness, duplicates, overlapping selected intervals and operational state codes. The bounded audit does not establish an independent modeling cohort. In later approved work, split real data by anonymized well across directories when feasible, keep related/overlapping instances together, and create windows only after splitting. If insufficient wells prevent independent partitions, declare the limitation and revise scope rather than claim unseen-well performance. Synthetic/drawn augmentation is optional and training-only; real validation/test remain separate.

Release notes report closing label gaps in real data, while the descriptor permits unknown labels generally. Keep null handling and verify coverage after acquisition; do not assume either statement proves the selected cohort is complete.

Repository code is Apache-2.0; dataset Parquet files are CC BY 4.0. Future manifests and demo attribution must identify Petrobras/3W, version, revision, source link, license and transformations. No endorsement is implied. No upstream implementation or telemetry was copied in Phase 0.
