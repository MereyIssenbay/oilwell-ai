# Independent Phase 1 data integrity review

Review date: 2026-11-10. Status: complete; no remaining blocker to Phase 1 acquisition/audit acceptance. This is not approval for preprocessing or model training.

## Scope and independence

The reviewer owns only `tests/qa/` and this report. Acquisition, raw files, manifests, validation implementation and the consolidated audit are owned by other agents. The reviewer did not download telemetry or transform source data. This review distinguishes acquisition/audit acceptance from readiness to train a model.

## Independent upstream evidence

Sources were inspected at repository commit `914af287b1cf3e5207dce0da1e9dc08361c9adeb`:

- [dataset.ini](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/dataset/dataset.ini): dataset version 2.0.0; 27 named sensor columns; `class` and `state` are labels, not sensor features. Only documented transient class codes are valid.
- [Dataset structure](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/3W_DATASET_STRUCTURE.md): timestamp index, nullable Float64 sensor columns, nullable Int64 labels, pyarrow/Brotli Parquet.
- [Licensing statement](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/README.md#licenses) and [dataset license](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/dataset/LICENSE-CC-BY): repository code Apache-2.0; dataset Parquet files CC BY 4.0. The code license is `LICENSE.md`, not `LICENSE`.
- [Loader source](https://github.com/petrobras/3W/blob/914af287b1cf3e5207dce0da1e9dc08361c9adeb/toolkit/ThreeWToolkit/dataset/parquet_dataset.py): filename prefixes identify origins; the default feature extraction drops `class` but can leave `state`, and initialization can download the whole dataset. The upstream loader was inspected, not executed.
- [Author manuscript, Table 5](https://arxiv.org/html/2507.01048v1#S2.T5): operational state codes are 0 Open, 1 Shut-In, 2 Flushing Diesel, 3 Flushing Gas, 4 Bullheading, 5 Closed With Diesel, 6 Closed With Gas, 7 Restart and 8 Depressurization; null denotes unknown. Nature and PMC page retrieval was unavailable to this reviewer, so the primary author manuscript was used for this mapping. Table 4 permits any documented class code on observations in any instance; a directory label is not a restriction on every row.

The complete pinned recursive Git tree (`truncated=false`) independently yielded 2,228 Parquet paths and 19 nonempty event-directory/origin strata: 10 real, seven simulated and two drawn. The sum of the smallest file in each stratum was 10,148,080 bytes. This supports a small coverage-oriented audit, not a representative prevalence estimate.

The tree contained 40 distinct real `WELL-<digits>` identifiers, 225 colliding basename groups and no duplicate Git blob hashes. The v2 release notes state 42 real wells; that historical statement must be distinguished from the observed pinned inventory. Multiple well identifiers occur across class directories. These observations use filenames/Git metadata only and do not establish physical-well identity or absence of duplicate signal segments.

## Findings communicated during implementation

1. **Sampling scope:** smallest-per-stratum selection is size-biased. The audit must disclose this, retain exact selection provenance and avoid claims about full-corpus row prevalence, class balance or train/test feasibility.
2. **Label semantics:** validate observation labels against the global registry; do not reject a valid label solely because it differs from the containing class directory. Never treat `EXTRA_INSTANCES_TRAINING=-1` as a class.
3. **Identity and source counts:** use full relative paths plus revision for instance identity; preserve the observed 40-vs-reported-42 well-count discrepancy rather than silently choosing one.
4. **No automatic ML readiness:** real/simulated/drawn are different source domains; synthetic sources share generating mechanisms and cannot substitute for independent real holdouts. No splits, preprocessing or training are authorized in this phase.

## Implementation findings and verified fixes

| Finding | Resolution and verification |
| --- | --- |
| An interrupted HTTP response (`http.client.IncompleteRead`) could escape downloader retry/error handling | The owner added it to bounded transport retries and added a regression test. The combined suite passed. Downloads are hash-verified before atomic publication. |
| Validator path containment originally trusted the resolved `data/raw` root even if that root was a directory symlink outside the repository | The orchestrator added containment of the raw root itself. A real directory-symlink fixture passed on this host; the test was not skipped. |
| Report output could target unrelated project files and used a predictable temporary filename | Output is now restricted to JSON beneath an in-repository `reports/` directory, and uses a unique temporary file with atomic replacement. Protected-source/manifest and output-boundary tests passed; unique temporary-file handling was reviewed in code. |
| Root manifest JSON values `[]` and `null` raised uncaught `AttributeError` instead of the documented fatal exit code | Both entry points now validate the root object type; validator validates nested manifest shapes as well. Regression tests confirm malformed roots return exit code 2 without creating a report. |

No other substantive implementation defect remained after these fixes. Source files were never changed to make validation pass. Null labels, missing channels and dtype/documentation differences remain visible audit findings.

## Acquired-data checks independently executed

The reviewer independently re-read all acquired files with Pandas/PyArrow and compared them with [data_summary.json](../../reports/data_summary.json), without calling the validator's counting functions:

| Check | Observed result |
| --- | --- |
| Manifest versus independently retrieved pinned Git tree | All 23 Parquet and eight provenance entries matched path, expected byte size and Git blob identity |
| Local byte integrity | All 31 sources matched byte length, SHA-256 and Git blob SHA-1 |
| Pandas and PyArrow reads | All 23 Parquet files readable; footer/Pandas row counts agreed |
| Total observations | 582,220: 322,725 real, 201,894 simulated, 57,601 drawn |
| Actual schema | Every file: 27 Arrow double/Pandas `float64` sensor columns, two Arrow int16/Pandas nullable `Int16` labels, and a timezone-naive `timestamp[ns]` index; 30 physical Arrow fields and 29 Pandas columns |
| Distribution and missingness reconciliation | Every per-file class/state distribution, every sensor null count and all corresponding report aggregates matched independent recomputation |
| Null labels | 50,400 null values in each label; exactly positions 0-3599 in every one of the 14 real files |
| Timestamp checks | Every inspected index was increasing, had no duplicate values and had one-second intervals; no timezone was inferred |
| Event-family coverage caveat | Both selected event-7 instances lacked steady label 7; transient 107 was present |
| Read preservation | SHA-256 remained unchanged after the reviewer's reads |
| Report status at reconciliation | Zero errors and 74 warnings; warnings are retained findings, not data repairs |

The schema width and null-label observations contradict treating upstream prose as an exact description of the pinned subset. They were communicated to the orchestrator and are documented in [data/README.md](../../data/README.md). All-missing channels and origin-dependent availability remain material limitations. `class`, `state` and source metadata are absent from `sensor_summary`; only the explicit sensor allowlist is considered.

## Automated verification actually run

The reviewer created [test_data_integrity.py](../../tests/qa/test_data_integrity.py) with 39 offline cases. These use small synthetic fixtures, never modified copies of the acquired dataset. They cover nullable/unknown label preservation, documented and invalid transient/state values, sensor/metadata separation, malformed schemas, infinity, missing/duplicate/backward timestamps, cadence gaps, null-label interval accounting, corrupt/missing files, metadata hash rejection before parsing, traversal/symlink boundaries, protected output paths and malformed manifest exit semantics.

The final combined command was:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_download_data.py tests/qa/test_data_integrity.py -q -p no:cacheprovider --basetemp <verified-unique-workspace-temp-directory> --tb=short
```

Observed result: **55 passed, zero failed, zero skipped** (16 downloader tests plus 39 independent QA cases; pytest reported 0.99 seconds). Environment: Python 3.13.3, Pandas 2.2.3, NumPy 2.2.6, PyArrow 26.0.1 and pytest 9.1.1. Initial sandboxed attempts could not create pytest temporary fixtures because of host ACL restrictions; a narrowly approved run used a verified temporary path beneath `tests/qa/.pytest_cache/`. Those setup failures were not application failures or successful tests. An intermediate run exposed the malformed-root defect above; its regression cases passed after correction.

Source/checksum/distribution reconciliations were performed with separate inline read-only Python scripts. The official metadata checks used the GitHub connector and primary-source web retrieval. The reviewer did not acquire telemetry, execute the upstream loader, implement preprocessing, create splits, train models or run application/end-to-end services.

## Disposition and residual limitations

Phase 1 acquisition and audit have sufficient independent evidence for acceptance. The bounded size-biased subset is not an ML evaluation cohort. Directory/origin coverage does not establish all label/state/phase coverage, independent group support, operational prevalence or generalization. Source timezone, physical identity equivalence, synthetic-family relationships, wider-corpus overlaps/near-duplicates and the effects of upstream historical interpolation remain unresolved or require later scoped work. No model metrics or training readiness are claimed. Stop after the orchestrator records final provenance hashes and progress; later phases require user approval.
