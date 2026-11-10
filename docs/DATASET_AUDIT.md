# Dataset acquisition and audit

Completed-scope evidence for Phase 1, 2026-11-10 (Asia/Oral). This audit reads a bounded subset of original data. It does not preprocess, repair, split, train, or claim model readiness. Final verification and phase disposition are in [PROGRESS.md](PROGRESS.md).

## Provenance and access

Dataset **3W v2.0.0**, pinned repository commit `914af287b1cf3e5207dce0da1e9dc08361c9adeb`. Source: [Petrobras/3W](https://github.com/petrobras/3W). The exact acquisition plan and file hashes are in [subset.json](../data/manifests/subset.json); machine-readable observations are in [data_summary.json](../reports/data_summary.json).

Authoritative sources: [dataset.ini](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/dataset/dataset.ini), [structure documentation](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/3W_DATASET_STRUCTURE.md), [dataset release notes](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/dataset/README.md), [repository README](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/README.md), [dataset license](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/dataset/LICENSE-CC-BY), [code license](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/LICENSE.md), and [citation instructions](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/CITATION.md). Original copies are saved under the ignored revision-specific raw directory and checked like the Parquet files.

The repository pin is deliberately retained for reproducibility; this audit does not claim it is the latest branch head. Dataset and toolkit versions are separate. Public individual-file HTTPS acquisition succeeded with no credentials. The execution sandbox initially refused network connections; approved execution escalation resolved that environment restriction. There is no remaining dataset access blocker.

The [official downloader implementation](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/toolkit/ThreeWToolkit/utils/downloader.py) also offers the full v2.0.0 Figshare archive (article 29205836) with an archive checksum. Git clone/archive and toolkit download are alternatives. Neither a full archive nor a repository clone was acquired; invoking the upstream dataset loader could trigger an automatic full download.

## Reproducible commands

Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe scripts/download_data.py --dry-run
.\.venv\Scripts\python.exe scripts/download_data.py
.\.venv\Scripts\python.exe scripts/download_data.py --offline
.\.venv\Scripts\python.exe scripts/validate_data.py
.\.venv\Scripts\python.exe -m pytest tests/data tests/qa -q
```

On POSIX, substitute `.venv/bin/python`. Exact audit dependencies, including transitive dependencies, are pinned in [requirements-data.txt](../requirements-data.txt). The executed environment is Python 3.13.3, Pandas 2.2.3, NumPy 2.2.6 and PyArrow 26.0.1; other Python/OS combinations have not been tested. No application services were installed.

`download_data.py` uses only the standard library and performs no work on import. It uses the saved manifest when present, otherwise discovers the pinned Git tree. Selection is deterministic and bounded; downloads have timeout, retry and response-size limits. Complete bytes are verified before atomic publication, and conflicting existing originals are never replaced. The manifest checkpoints acquired hashes. `--offline` verifies all expected originals without network or writes.

`validate_data.py` is offline and read-only with respect to source data. It independently parses the verified ini, checks source identities/size/Git blob SHA-1/SHA-256, reads footer and Pandas schemas, measures missingness/labels/time/order/duplicates, and emits the JSON summary atomically. `--output` accepts JSON reports under repository `reports/` only. Exit 0 means the audit passed with possible warnings; exit 1 means data/integrity validation errors; exit 2 means a fatal manifest/configuration/I/O problem and no report update. A stale report must not be treated as a successful new run after a nonzero exit.

## Bounded selection

The pinned Git tree lists 2,228 Parquet paths totaling 1,873,131,359 bytes. These are metadata inventory counts, not inspected rows. It contains 19 nonempty event-directory/origin strata: ten real, seven simulated and two hand-drawn. The script selects the smallest file in each stratum, breaking ties by source path, then four files introducing additional real well identifiers. Hard ceilings are 30 Parquet files and 100 MiB including provenance documents.

| Origin | Selected files | Inspected rows |
| --- | ---: | ---: |
| real | 14 | 322,725 |
| simulated | 7 | 201,894 |
| drawn | 2 | 57,601 |
| **Total** | **23** | **582,220** |

Original Parquet size: **10,719,108 bytes** (about 10.22 MiB). Eight provenance documents add 58,535 bytes. All 19 available strata are covered; selected real files reference 12 distinct anonymized well IDs. All 31 originals have verified Git blob SHA-1 and recorded SHA-256. A repeat acquisition preserved original hashes and modification times.

**This is a purposive, size-biased audit subset.** Small compressed files can favor short, constant or highly missing signals. The distributions below describe only these selected observations, not population prevalence, balanced classes or independent evaluation samples. Directory coverage does not establish row-level event/phase coverage.

## Actual Parquet and Pandas schema

| Field category | Measured representation in all 23 files | Use |
| --- | --- | --- |
| 27 sensor names | Arrow `double`; Pandas `float64` with NaN | Sensor candidates only; exact allowlist from verified ini |
| `class` | Arrow `int16`; nullable Pandas `Int16` | Per-row target; excluded from sensors |
| `state` | Arrow `int16`; nullable Pandas `Int16` | Operational-status label; excluded from sensors |
| `timestamp` | Arrow `timestamp[ns]`; Pandas timezone-naive `DatetimeIndex`, name `timestamp` | Observation index, not a target or ordinary numeric feature |
| Source path/origin/well/directory/instance ID | Manifest fields, not observation columns | Provenance and grouping; excluded from features |

Each file has **30 Arrow fields and 29 Pandas columns plus the timestamp index**. Compression was read from each Parquet footer and is included in the JSON report. The source structure document describes nullable `Float64`/`Int64`; the selected files instead expose `float64`/`Int16`. This is a documentation-versus-bytes discrepancy, not a reason to rewrite the originals. Validation checks numeric sensor/integer label roles without assuming a 64-bit nullable label width.

The exact 27 names and original unit/domain descriptions are in the [verified registry](../data/manifests/dataset_metadata.json) and [metadata baseline](DATASET_METADATA.md). Selecting all numeric columns would leak both `class` and `state`. No feature matrix or transformed dataset was produced.

## Row-label meaning and observed distribution

Base event codes are defined by `dataset.ini`. Only 101, 102, 105, 106, 107, 108 and 109 are documented transient codes; arbitrary modulo/subtraction mapping is invalid. Null means unknown/unlabeled. The [author manuscript](https://arxiv.org/html/2507.01048v1) states that any valid class can label a row in any instance: directory class is contextual metadata, never an instruction to broadcast a row label. Phase 1 only counts the original values.

| Raw class code | Meaning | Selected rows |
| --- | --- | ---: |
| 0 | NORMAL | 153,971 |
| 1 | ABRUPT_INCREASE_OF_BSW | 29,631 |
| 2 | SPURIOUS_CLOSURE_OF_DHSV | 21,599 |
| 3 | SEVERE_SLUGGING | 30,975 |
| 4 | FLOW_INSTABILITY | 14,099 |
| 5 | RAPID_PRODUCTIVITY_LOSS | 23,999 |
| 6 | QUICK_RESTRICTION_IN_PCK | 18,153 |
| 7 | SCALING_IN_PCK | 0 |
| 8 | HYDRATE_IN_PRODUCTION_LINE | 20,061 |
| 9 | HYDRATE_IN_SERVICE_LINE | 21,239 |
| 101 | ABRUPT_INCREASE_OF_BSW (transient) | 32,544 |
| 102 | SPURIOUS_CLOSURE_OF_DHSV (transient) | 5,113 |
| 105 | RAPID_PRODUCTIVITY_LOSS (transient) | 5,914 |
| 106 | QUICK_RESTRICTION_IN_PCK (transient) | 7,724 |
| 107 | SCALING_IN_PCK (transient) | 51,277 |
| 108 | HYDRATE_IN_PRODUCTION_LINE (transient) | 91,561 |
| 109 | HYDRATE_IN_SERVICE_LINE (transient) | 3,960 |
| null | Unknown / unlabeled | 50,400 |

Code `7` is absent even though directory 7 is represented and transient `107` is present. The selected real observations also do not cover all event families and phases; use the per-origin/per-file distributions in the JSON instead of inferring support from the directory selection.

### Operational state

The ini describes `state` as well operational status but does not enumerate codes. The mapping below comes from the primary author manuscript [Table 5](https://arxiv.org/html/2507.01048v1#S2.T5), not an inferred relation to `class`. Table 3 separately describes valve sensor values: 0 closed, 1 open, 0.5 other state.

| State code | Documented meaning | Selected rows |
| --- | --- | ---: |
| 0 | Open | 445,398 |
| 1 | Shut-In | 59,395 |
| 2 | Flushing Diesel | 0 |
| 3 | Flushing Gas | 0 |
| 4 | Bullheading | 20,291 |
| 5 | Closed With Diesel | 0 |
| 6 | Closed With Gas | 0 |
| 7 | Restart | 1,553 |
| 8 | Depressurization | 5,183 |
| null | Unknown | 50,400 |

All selected simulated/drawn rows have state 0. This observation is subset-specific and is another reason not to use `state` as an input feature.

## Missingness and timestamps

`class` and `state` each have **50,400 null observations** (8.66% of all selected rows; 15.62% of selected real rows). In every one of the 14 real files, the null interval is exactly positions 0-3599: the first 3,600 observations. The validator records leading/trailing null counts and first/last positions. Do not fill these labels with normal or use future labels to fill them.

Release notes describe closing label gaps in real data. The measured initial gaps remain in this pin, so the release-note wording cannot be used as a guarantee of complete selected labels. The cause of those gaps has not been verified; calling them warm-up or sensor delay would be an inference.

| Sensor | Missing rows | Missing % | Files entirely missing |
| --- | ---: | ---: | ---: |
| `ABER-CKGL` | 413,442 | 71.01 | 19 / 23 |
| `ABER-CKP` | 560,629 | 96.29 | 20 / 23 |
| `ESTADO-DHSV` | 370,368 | 63.61 | 17 / 23 |
| `ESTADO-M1` | 370,368 | 63.61 | 17 / 23 |
| `ESTADO-M2` | 370,368 | 63.61 | 17 / 23 |
| `ESTADO-PXO` | 370,368 | 63.61 | 17 / 23 |
| `ESTADO-SDV-GL` | 351,122 | 60.31 | 17 / 23 |
| `ESTADO-SDV-P` | 335,171 | 57.57 | 15 / 23 |
| `ESTADO-W1` | 370,369 | 63.61 | 17 / 23 |
| `ESTADO-W2` | 370,369 | 63.61 | 17 / 23 |
| `ESTADO-XO` | 370,368 | 63.61 | 17 / 23 |
| `P-ANULAR` | 298,698 | 51.30 | 12 / 23 |
| `P-JUS-BS` | 582,220 | 100.00 | 23 / 23 |
| `P-JUS-CKGL` | 280,619 | 48.20 | 13 / 23 |
| `P-JUS-CKP` | 378,734 | 65.05 | 20 / 23 |
| `P-MON-CKGL` | 435,032 | 74.72 | 22 / 23 |
| `P-MON-CKP` | 68,107 | 11.70 | 5 / 23 |
| `P-MON-SDV-P` | 582,220 | 100.00 | 23 / 23 |
| `P-PDG` | 42,830 | 7.36 | 3 / 23 |
| `PT-P` | 582,220 | 100.00 | 23 / 23 |
| `P-TPT` | 32,059 | 5.51 | 2 / 23 |
| `QBS` | 582,220 | 100.00 | 23 / 23 |
| `QGL` | 323,453 | 55.56 | 16 / 23 |
| `T-JUS-CKP` | 233,071 | 40.03 | 8 / 23 |
| `T-MON-CKP` | 378,734 | 65.05 | 20 / 23 |
| `T-PDG` | 338,247 | 58.10 | 15 / 23 |
| `T-TPT` | 55,569 | 9.54 | 3 / 23 |

**Four sensors are entirely missing in this subset:** `P-JUS-BS`, `P-MON-SDV-P`, `PT-P`, `QBS`. This does not prove they are absent in all 3W files. Per-origin null counts and per-file minima/maxima/domain diagnostics are retained in the report. Missingness itself may reveal source origin or well identity and can create misleading prediction shortcuts.

Every selected timestamp index is monotonic, has no duplicate or null timestamp, and has exactly 1-second consecutive intervals. No source timezone is encoded; the audit preserves naive timestamps and does not convert them to UTC or the machine timezone. The descriptor reports source-system interpolation for historical real telemetry; this is inherited source provenance, not project preprocessing, and can limit prospective/causal evaluation claims.

## Identity, overlap and leakage findings

Real sources use `WELL-<id>_<timestamp>.parquet`; simulated and hand-drawn sources use `SIMULATED_<id>.parquet` and `DRAWN_<id>.parquet`. Real well IDs recur across directories. Synthetic sequence numbers restart within classes, so a basename is not globally unique and a synthetic instance ID is not a physical well. The project instance ID is `3w:` plus SHA-256 of `<revision>:<full source path>`.

The independent full-tree review found 40 distinct real filename IDs and 225 basename collision groups. Release notes describe 42 wells; the difference between release text and this pinned path inventory remains unresolved. Full-tree metadata also had no identical Git blob groups. These are metadata findings, not a whole-dataset content audit.

Within the acquired subset: 0 duplicate source-byte groups, 0 identical full-frame fingerprints, and 0 overlapping timestamp intervals among the same real well ID were detected. Full-frame fingerprints include timestamps, sensors and labels and are tied to the recorded Pandas version; they do not detect near-duplicates or shared subsequences. Negative results do not establish independence outside the subset.

`WELL-00002` appears in selected normal, event-1 and event-4 instances; keep these related sources together in any future partition. Other same-well and synthetic-family relationships must also be grouped before window construction. No random row split is acceptable.

| Event family | Real well IDs with observed base/transient row labels in this subset |
| --- | --- |
| 0 | WELL-00002, WELL-00004, WELL-00005, WELL-00006, WELL-00008, WELL-00011, WELL-00016, WELL-00024, WELL-00029, WELL-00036 |
| 1 | WELL-00002 |
| 2 | WELL-00011 |
| 3 | WELL-00001 |
| 4 | WELL-00002, WELL-00010 |
| 5 | WELL-00016 |
| 6 | WELL-00004 |
| 7 | WELL-00024 |
| 8 | WELL-00029 |
| 9 | None observed |

This subset does **not** establish an independent train/validation/test cohort for normal plus two undesirable families. No split manifest or final model scope is fabricated. A later approved data expansion must choose sufficient real groups, inspect repeated/overlapping segments, resolve label-phase support and select usable sensors before preprocessing or training.

Required future controls: exclude target/status/identity/origin/directory information from features; group related instances before windows; avoid future interpolation, backward fill and centered windows; fit learned transforms only on training partitions; reserve independent real validation/test groups; treat synthetic/drawn data as separately evaluated optional training augmentation. Keep source paths and label-bearing manifests out of LLM provider packets.

## Validation and independent review

The current automated audit read all 23 selected files and returned **0 errors and 74 warnings**. Warning counts are 23 per-file all-missing-sensor findings, 14 missing-class findings, 14 missing-state findings and 23 unknown-timezone findings. Passing means the audit checks completed and bytes/schema/allowed values/time ordering were valid; it does not mean the data is complete or model-ready.

The independent reviewer separately verified every original against the pinned Git tree, reread all Parquet files, and reconciled row counts, every sensor missing count, and class/state distributions against the generated report. Source hashes remained unchanged after reads. Downloader and validator failure-path tests use synthetic fixtures; their results and reviewed fixes are in [PHASE_1.md](reviews/PHASE_1.md) and [PROGRESS.md](PROGRESS.md). No model, backend or end-to-end application test was run.

## License, attribution and disposition

Dataset Parquet files are **CC BY 4.0**; repository code is **Apache-2.0**. Attribution: Petrobras and the 3W contributors, 3W Dataset v2.0.0, pinned revision and source links above. Both original licenses and CITATION.md are cached. Original data bytes were not transformed; selection, metadata registries and audit summaries are project-produced derivatives and should retain this attribution. No Petrobras endorsement is implied.

The requested acquisition-and-audit phase is complete, with 55 passing downloader/independent integrity tests and the final validation recorded in PROGRESS.md. No dataset access blocker remains. Source timezone, metadata/release discrepancies, sparse per-family well support, null labels and missing sensors remain explicit limitations. Preprocessing, cohort splitting, feature generation and training are outside this Phase 1 request and require a new approved scope.
