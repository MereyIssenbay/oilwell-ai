# Reproducible preprocessing and causal features

Phase 3, authorized 2026-11-10. This phase implements reusable preprocessing and verifies its boundaries. No event detector is fitted, no ML hypothesis is established, and no additional telemetry is acquired. Fitting imputation and normalization statistics on the assigned training partition is preprocessing. The [split policy](SPLIT_STRATEGY.md) and [five hypotheses](ML_HYPOTHESES.md) remain the evaluation constraints.

The statements above describe Phase 3's completed scope. Phase 4 subsequently authorizes fixed diagnostic baselines using these frozen artifacts under the [baseline protocol](../reports/baseline/PROTOCOL.md); it does not refit or revise preprocessing using validation/test data.

## Input contract and immutable sources

The source is Petrobras/3W v2.0.0 at revision `914af287b1cf3e5207dce0da1e9dc08361c9adeb`, under CC BY 4.0 with attribution to Petrobras and the 3W contributors. The [acquisition manifest](../data/manifests/subset.json) fixes each original path, unique source-instance ID, origin, published well ID, byte size and SHA-256. The [metadata registry](../data/manifests/dataset_metadata.json) fixes the exact 27 sensor names and documented label codes. Original Parquets remain under ignored `data/raw/` and are never repaired or overwritten.

Each instance is loaded separately. Its unique, increasing source timestamp index, original source identity and checksum remain available for provenance. Source timestamps are naive; the pipeline does not localize them or assert physical UTC. Labels, identifiers and source paths are separate from sensor inputs. No concatenated history is allowed across files, wells or partitions.

The auxiliary column **`state` is a label** and is excluded alongside `class`. The registry's `ESTADO-*` valve-position variables are actual sensor columns, distinct from that label. They remain candidate inputs through the exact allowlist. Numerical summaries of their discrete codes describe observations; they do not establish physical mechanisms or certify a useful modeling representation.

## Partition before windows

The splitter groups all real instances with the same published `WELL-xxxxx` ID across event directories, and connects exact duplicates. Group membership is transitive. Missing a reliable real well key is not permission to fall back silently to a row split. Every included source instance belongs to exactly one partition. Synthetic and drawn sources are excluded by default; an explicit augmentation setting may place them in training only. They cannot enter the primary real validation/test partitions.

Allocation is deterministic for a fixed input inventory, configuration and seed. Connected groups are ranked by SHA-256 of seed plus group identity; constrained largest-deficit rounding allocates the requested group ratios while keeping all three real partitions nonempty. A single allocation is used; the implementation does not search seeds for favorable event coverage. Ratios refer to groups rather than rows and may require integer rounding. Exact sensor-and-timestamp copies are linked even when annotation columns differ; explicit related-family metadata can also connect groups. The resulting manifest records actual assignments and support limitations. Private asset aliases, near-duplicate subsequences and undocumented synthetic families cannot be inferred automatically.

Two uses must remain distinct:

- **Diagnostic:** exercise data flow and isolation on the existing EDA-exposed subset. A partition named `test` in this mode is a development diagnostic, not a pristine final evaluation.
- **Protected:** enforce exposure and declared class-support prerequisites before a future evaluation. Current inspected instances and all 12 published real well IDs are recorded in the [EDA exposure ledger](../reports/eda/eda_summary.json); future files from those same IDs remain exposed for an unseen-well claim. Missing evidence must not silently become a fresh-test claim.

Current event support is insufficient for the planned three-way multiclass evaluation. The implementation cannot repair that by splitting one well's windows across partitions. Protected-test readiness requires separately approved cohort work; no such acquisition is authorized here.

## Cadence, gaps and resampling

EDA and the independent Phase 3 raw audit found that all 23 acquired files have unique, increasing timestamps, with every within-instance interval exactly one second. Consequently **no resampling is performed**. A different rate would discard or synthesize measurements without evidence that it helps.

The expected cadence is configurable. A timestamp gap starts a new segment and resets window generation; windows never bridge it. Duplicate, null or non-increasing timestamps are invalid. Missing sensor values do not create observations or trigger interpolation. Future irregular sources need an explicit, independently reviewed policy before any resampling option is introduced; backward fill, centered aggregation and future interpolation remain prohibited.

## Causal windows and feature definitions

For a segment with `N` rows, window length `W` and stride `S`, endpoints begin at position `W - 1` and advance by `S` while inside the segment. Each window includes exactly rows `[end - W + 1, end]`, including the prediction endpoint. Short segments produce no complete windows. Window alignment depends on source coordinates and configuration, never true event boundaries or labels.

The initial reproducibility configuration uses 60 rows and stride 10 at a one-second cadence. This is an implementation exercise, not a validated optimum. A 60-row window has 59 seconds between its first and last timestamps and 60 one-second observations of support. Do not confuse elapsed span with observation count.

For each allowed sensor, compute the following from finite observed samples **inside that window only**:

| Feature | Definition | Missing-data behavior |
| --- | --- | --- |
| Mean | Arithmetic mean | Missing when no observed samples |
| Standard deviation | Population standard deviation, `ddof=0` | Zero for one observed sample; missing for none |
| Minimum / maximum | Observed extrema | Missing when no observed samples |
| Rate of change | Last observed value minus first observed value, divided by their actual elapsed seconds | Missing with fewer than two distinct observed times; never assume adjacent valid samples are one second apart |
| Recent trend | Ordinary least-squares slope of observed values against within-window elapsed seconds | Missing with fewer than two observed times; units are sensor units per second |

Trend is a numerical time slope, not an inferred physical cause. Raw units and zeros are preserved. Pressure features are calculated in the source's Pa, unlike display-only MPa scaling in EDA charts. No filename, directory, well ID, source origin, absolute timestamp, file-start offset, `class`, `state` or future label enters the feature matrix.

## Missing values and training-only normalization

No raw-sensor imputation is performed before window summaries. This keeps a long outage from becoming an invented flat signal and avoids future fills. Summary values can therefore remain missing, and quality information must accompany the features.

Only assigned **training windows** fit preprocessing state, including training windows whose endpoint target is unknown. Labels do not decide the feature schema or imputation parameters. Validation and test windows never contribute to these statistics.

1. Identify feature columns entirely missing on training windows and drop them from the fitted schema. Freeze the decision; a holdout observation cannot reactivate a dropped feature.
2. Learn each retained feature's median from observed training values. Use that median to fill missing feature summaries in every partition.
3. Compute training mean and population standard deviation after this imputation. Standardize with those frozen values. Constant columns use a safe unit scale; a constant observed zero is not changed to missing.
4. Preserve quality/availability separately. A finite imputed vector is not evidence that the original sensors were observed or that a prediction would be eligible. A future detector needs an explicit minimum-evidence/abstention policy.

The fitted object must reject a mixed or non-training fit batch, a mismatched split/configuration/schema, or invalid persisted statistics. Saved state is versioned, carries provenance/fingerprints and is validated on reload. It contains preprocessing parameters, not a trained event detector. Reusing it for a different cohort or fitting state again requires an explicit new preprocessing run.

These choices make holdout perturbations unable to change the fitted schema or parameters. They do not establish that median imputation or standardization is optimal. Missingness, absolute levels and constant channels can still encode well/source identity; the future ablations in H1/H2 remain necessary.

## Target policy

The target is the **label at the window endpoint**, for event detection at that source timestamp. It is not a majority label over the window and not a future-event forecast. Features may span an actual event transition without using the target sequence to align the window.

Default family mapping includes exactly documented transient codes: `101 -> 1`, `102 -> 2`, `105 -> 5`, `106 -> 6`, `107 -> 7`, `108 -> 8`, `109 -> 9`. Base labels `0..9` retain their meanings. No modulo/subtraction rule is applied to arbitrary codes. Invalid codes fail validation. Raw endpoint code and phase are retained separately for later transient/base evaluation.

This default preserves event-2/5/7 evidence where the selected real files contain only transients. An explicit transient-exclusion setting supports a future controlled comparison, while preserving the raw annotations and exclusion counts. Unknown endpoints remain nullable and in quality/provenance output; they are never normal examples. A separate eligibility flag controls supervised use. Unknown-to-abnormal boundaries do not supply a verified onset or detection-delay origin.

## Reproduction and acceptance evidence

Install [requirements-pipeline.txt](../requirements-pipeline.txt) into the project `.venv`. It preserves the Phase 1 data pins and adds pinned Pydantic dependencies for validated configuration and persisted artifacts. Plotting/notebook dependencies are optional and remain in `requirements-eda.txt`. The executed environment was Windows/Python 3.13.3; Python 3.11/3.12 have not been separately tested.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
.\.venv\Scripts\python.exe scripts/prepare_data.py
```

The [integration command](../scripts/prepare_data.py) accepts window length, stride, cadence, seed, group ratios, target policy and synthetic-training settings; `--help` lists them. Default output is:

- [Development split manifest](../data/manifests/development_split.json), versioned with assignments, grouping, support, exposure hash and deterministic fingerprint.
- [Preprocessing summary](../reports/preprocessing_summary.json), versioned with counts, warnings, code/input/dependency hashes and artifact checksums.
- Ignored `data/processed/phase3/`: validated `preprocessor.json` and separate `features.parquet`, `targets.parquet`, `metadata.parquet`, `quality.parquet`. No raw rows or processed features are committed.

Outputs are replaced atomically **per file**, not as an all-artifact transaction. A failed run can leave a mixed generation; consumers must verify the completed summary's hashes before reuse. Input files cannot be overwritten by the CLI's split/summary paths, and processed output is constrained to the repository's `data/processed/` tree. The command validates source hashes before/after reads, validates saved state, and checks exact Parquet/state round trips.

The reusable Python interface is:

```python
from pathlib import Path
from ml.data_pipeline import (
    CausalFeaturePipeline, PipelineConfig, SplitConfig,
    load_exposure, load_instances, make_split,
)

root = Path.cwd()
instances = load_instances(root)
exposure = load_exposure(root / "reports/eda/eda_summary.json")
split = make_split(instances, SplitConfig(seed=42, mode="diagnostic"), exposure)
pipeline = CausalFeaturePipeline(PipelineConfig(window_rows=60, stride_rows=10))
batch = pipeline.build(instances, split)
pipeline.fit(batch.subset("train"), split)
features = pipeline.transform(batch, split)
# batch.targets, batch.metadata and batch.quality stay separate and index-aligned.
```

`fit` rejects mixed/holdout batches and repeated fitting. `transform` is read-only with respect to fitted statistics. `save`/`load` use validated JSON, not executable pickle; reload checks the implementation hash and the recorded package versions. Reproduce with the same code/environment rather than silently loading incompatible state. Checksums detect corruption and inconsistency; they are not a signature or a security boundary against arbitrary trusted Python code modifying its inputs.

## Actual-data verification

The default run loaded all 23 originals (582,220 rows) and included 14 real files (322,725 rows); nine simulated/drawn files were excluded. It produced **32,197 windows**, with 162 candidate features and **120 retained features**. Forty-two train-allmissing feature columns were dropped without consulting holdout availability. All training endpoints, including unknown targets, contributed to preprocessing statistics.

| Diagnostic partition | Published real well groups | Source instances | Windows | Known-target, observed-input eligible windows | Unknown endpoints |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 7 | 7 | 10,134 | 7,649 | 2,485 |
| Validation | 3 | 3 | 17,583 | 16,518 | 1,065 |
| Test | 2 | 4 | 4,480 | 3,060 | 1,420 |

The 7/3/2 group allocation illustrates integer rounding of 60/20/20; row percentages differ substantially. Some event families occur only outside training. Explicit warnings remain in the manifest/summary, and this split is unsuitable for a claimed multiclass detector evaluation. It is not adjusted to manufacture class coverage.

There are 4,970 unknown-target windows and 10,710 transient endpoints. No default window is entirely missing across all selected sensors. `supervised_eligible` means a mapped endpoint family and at least one observed selected-sensor value; it is **not** an approved inference-quality threshold. Counts refer to selected sensors before train-allmissing feature removal. A future detector must check retained-feature evidence and declare its abstention rule rather than treating imputation as sufficient evidence.

Actual integration checks:

- Two default runs produced byte-identical split, summary, state and four Parquet files (seven files total).
- Source hashes remained unchanged, all 12 real well IDs and all 14 included source instances were disjoint across partitions, and normalized training means/standard deviations matched the declared policy.
- An independent calculation reconciled 5,040 feature values at first/middle/last windows across all 14 included instances, using `numpy.linalg.lstsq` as a separate trend reference.
- `--mode protected` rejected the EDA-exposed holdout. Invalid window configuration, raw-output paths and attempts to overwrite the input manifest were rejected without changing completed outputs.
- **141 automated tests passed**, zero failed/skipped: 74 prior data/EDA tests, 20 implementation tests and 47 independent Phase 3 leakage tests. They include future perturbations, target invariance, analytic statistics, gaps, repeated wells, duplicate groups, train-only fitting, transient/unknown policy, deterministic ordering, malformed artifacts and standalone imports.

See [independent review](reviews/PHASE_3.md) and [PROGRESS.md](PROGRESS.md) for commands and scope. Passing these checks establishes preprocessing behavior, not predictive accuracy, calibration or deployment readiness.

Upstream historical interpolation remains a limitation even when this project's calculations are causal. Near-duplicate subsequences and undocumented synthetic-family relationships also require wider-cohort review before an evaluation claim.

Validation reference: [Pydantic strict mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/) documents strict type checking; the implementation also checks domain invariants such as source membership, finite statistics and positive scales. This document describes project policy rather than claiming that a validation library alone prevents data leakage.
