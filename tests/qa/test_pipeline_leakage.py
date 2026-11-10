"""Independent adversarial checks of the public preprocessing boundary.

All instances here are synthetic fixtures, not acquired telemetry or model runs.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.data_pipeline import (  # noqa: E402
    CausalFeaturePipeline,
    ExposureLedger,
    Instance,
    PipelineConfig,
    SourceMetadata,
    SplitConfig,
    SplitManifest,
    load_instances,
    make_split,
)


SENSORS = tuple(item["name"] for item in json.loads(
    (ROOT / "data/manifests/dataset_metadata.json").read_text())["sensor_columns"])


def _instance(number: int, values: list[float] | None = None, *, well: int | None = None,
              origin: str = "real", labels: list[int | None] | None = None,
              seconds: list[int] | None = None, sha: str | None = None) -> Instance:
    """Construct independent, traceable fixtures with the real column allowlist."""
    values = values if values is not None else [float(number + i) for i in range(9)]
    index = pd.Timestamp("2020-01-01") + pd.to_timedelta(seconds if seconds is not None else range(len(values)), unit="s")
    frame = pd.DataFrame({sensor: np.nan for sensor in SENSORS}, index=pd.DatetimeIndex(index, name="timestamp"))
    frame["P-TPT"] = values
    frame["T-TPT"] = np.asarray(values, dtype=float) * 2
    frame["class"] = pd.array(labels if labels is not None else [0] * len(values), dtype="Int16")
    frame["state"] = pd.array([0] * len(values), dtype="Int16")
    metadata = SourceMetadata(
        instance_id=f"qa-instance-{number}", source_path=f"dataset/0/qa-{number}.parquet",
        sha256=sha or hashlib.sha256(f"qa-source-{number}".encode()).hexdigest(),
        origin=origin, well_id=f"WELL-{well if well is not None else number:05d}" if origin == "real" else None,
    )
    return Instance(metadata=metadata, frame=frame)


def _cohort(first: Instance | None = None) -> tuple[Instance, ...]:
    return (first or _instance(1), *(_instance(i) for i in range(2, 9)))


def _pipeline(config: PipelineConfig | None = None) -> CausalFeaturePipeline:
    return CausalFeaturePipeline(config or PipelineConfig(window_rows=3, stride_rows=1), ("P-TPT", "T-TPT"))


def _build(instances: tuple[Instance, ...], config: PipelineConfig | None = None):
    split = make_split(instances, SplitConfig(seed=42))
    pipeline = _pipeline(config)
    return pipeline, split, pipeline.build(instances, split)


def test_future_values_cannot_change_past_raw_or_frozen_normalized_features() -> None:
    instances = _cohort()
    pipeline, split, batch = _build(instances)
    pipeline.fit(batch.subset("train"), split)
    original = pipeline.transform(batch, split)
    selected = batch.metadata.loc[batch.metadata.partition.eq("test"), "instance_id"].iloc[0]
    altered = []
    for source in instances:
        frame = source.frame.copy(deep=True)
        if source.metadata.instance_id == selected:
            frame.loc[frame.index[6:], ["P-TPT", "T-TPT"]] = 1e12
        altered.append(Instance(metadata=source.metadata, frame=frame))
    changed = pipeline.build(tuple(altered), split)
    prior = batch.metadata.instance_id.eq(selected) & (batch.metadata.endpoint_position < 6)
    pd.testing.assert_frame_equal(batch.features.loc[prior], changed.features.loc[prior])
    pd.testing.assert_frame_equal(original.loc[prior], pipeline.transform(changed, split).loc[prior])


def test_labels_and_state_cannot_change_feature_values_or_window_schedule() -> None:
    instances = _cohort()
    pipeline, split, batch = _build(instances)
    changed = []
    for source in instances:
        frame = source.frame.copy(deep=True)
        frame["class"] = pd.array([None, 101, 1] * 3, dtype="Int16")
        frame["state"] = pd.array([8] * len(frame), dtype="Int16")
        changed.append(Instance(metadata=source.metadata, frame=frame))
    other = pipeline.build(tuple(changed), split)
    pd.testing.assert_frame_equal(batch.features, other.features)
    pd.testing.assert_series_equal(batch.metadata.endpoint_position, other.metadata.endpoint_position)
    assert set(batch.features) == {f"{sensor}__{stat}" for sensor in ("P-TPT", "T-TPT")
                                   for stat in ("mean", "std", "min", "max", "rate", "trend")}


def test_feature_statistics_use_observed_values_and_actual_elapsed_time() -> None:
    pipeline, split, batch = _build(_cohort(_instance(1, [0.0, np.nan, 4.0, 6.0])))
    row = batch.features.loc[batch.metadata.instance_id.eq("qa-instance-1")].iloc[0]
    assert row["P-TPT__mean"] == pytest.approx(2.0)
    assert row["P-TPT__std"] == pytest.approx(2.0)
    assert row["P-TPT__min"] == 0.0
    assert row["P-TPT__max"] == 4.0
    assert row["P-TPT__rate"] == pytest.approx(2.0)
    assert row["P-TPT__trend"] == pytest.approx(2.0)


def test_recent_trend_is_not_merely_endpoint_rate() -> None:
    _, _, batch = _build(_cohort(_instance(1, [0.0, 3.0, 0.0, 0.0])), PipelineConfig(window_rows=4, stride_rows=1))
    row = batch.features.loc[batch.metadata.instance_id.eq("qa-instance-1")].iloc[0]
    assert row["P-TPT__rate"] == 0.0
    assert row["P-TPT__trend"] == pytest.approx(-0.3)


def test_no_backward_fill_from_later_observations() -> None:
    _, _, batch = _build(_cohort(_instance(1, [np.nan, np.nan, np.nan, 1000.0])))
    row = batch.features.loc[batch.metadata.instance_id.eq("qa-instance-1")].iloc[0]
    assert row.isna().all()


def test_windows_reset_at_timestamp_gaps() -> None:
    _, _, batch = _build(_cohort(_instance(1, [1., 2., 3., 10., 11., 12.], seconds=[0, 1, 2, 10, 11, 12])))
    rows = batch.metadata.loc[batch.metadata.instance_id.eq("qa-instance-1")]
    assert rows.endpoint_position.tolist() == [2, 5]
    assert ((rows.timestamp - rows.window_start).dt.total_seconds() == 2).all()


def test_short_instance_never_borrows_previous_instance_history() -> None:
    _, _, batch = _build(_cohort(_instance(1, [10., 20.])))
    assert "qa-instance-1" not in set(batch.metadata.instance_id)


def test_fit_rejects_mixed_partitions() -> None:
    pipeline, split, batch = _build(_cohort())
    with pytest.raises(ValueError):
        pipeline.fit(batch, split)


def test_fit_rejects_holdout_even_if_it_has_identical_sensor_values() -> None:
    pipeline, split, batch = _build(_cohort())
    with pytest.raises(ValueError):
        pipeline.fit(batch.subset("validation"), split)


def test_transform_does_not_mutate_fitted_statistics() -> None:
    pipeline, split, batch = _build(_cohort())
    pipeline.fit(batch.subset("train"), split)
    state = copy.deepcopy(pipeline.state)
    pipeline.transform(batch.subset("test"), split)
    assert pipeline.state == state


def test_normalization_matches_training_statistics_without_holdout_values() -> None:
    pipeline, split, batch = _build(_cohort())
    training = batch.subset("train")
    heldout = batch.subset("test")
    pipeline.fit(training, split)
    transformed = pipeline.transform(heldout, split)
    name = "P-TPT__mean"
    expected = (heldout.features[name] - training.features[name].mean()) / training.features[name].std(ddof=0)
    np.testing.assert_allclose(transformed[name], expected, rtol=1e-12, atol=1e-12)


def test_zero_and_constant_channels_remain_finite_without_becoming_missing() -> None:
    instances = []
    for number in range(1, 9):
        source = _instance(number)
        frame = source.frame.copy(deep=True)
        frame["P-TPT"] = 0.0
        instances.append(Instance(metadata=source.metadata, frame=frame))
    pipeline, split, batch = _build(tuple(instances))
    names = [name for name in batch.features if name.startswith("P-TPT__")]
    assert not batch.features[names].isna().any().any()
    assert (batch.features[names] == 0).all().all()
    pipeline.fit(batch.subset("train"), split)
    assert (pipeline.transform(batch, split)[names] == 0).all().all()


def test_holdout_observations_do_not_revive_train_allmissing_features() -> None:
    instances = _cohort()
    split = make_split(instances, SplitConfig(seed=42))
    altered = []
    for source in instances:
        frame = source.frame.copy(deep=True)
        frame["T-TPT"] = np.nan if split.partition_for(source.metadata.instance_id) == "train" else 1e9
        altered.append(Instance(metadata=source.metadata, frame=frame))
    pipeline = _pipeline()
    batch = pipeline.build(tuple(altered), split)
    pipeline.fit(batch.subset("train"), split)
    result = pipeline.transform(batch.subset("test"), split)
    assert not any(name.startswith("T-TPT__") for name in result.columns)
    assert np.isfinite(result.to_numpy()).all()


def test_same_published_well_and_transitive_duplicate_links_stay_together() -> None:
    common_sha = hashlib.sha256(b"qa-identical-source").hexdigest()
    instances = (_instance(1, well=1), _instance(2, well=1, sha=common_sha),
                 _instance(3, well=3, sha=common_sha), *(_instance(i) for i in range(4, 10)))
    split = make_split(instances, SplitConfig(seed=42))
    linked = [split.assignment_for(f"qa-instance-{i}") for i in (1, 2, 3)]
    assert len({a.group_id for a in linked}) == 1
    assert len({a.partition for a in linked}) == 1
    assert len({a.source.instance_id for a in split.assignments}) == len(instances)


def test_group_allocation_is_order_independent_for_fixed_seed() -> None:
    instances = _cohort()
    one = make_split(instances, SplitConfig(seed=7))
    two = make_split(tuple(reversed(instances)), SplitConfig(seed=7))
    assert one.fingerprint == two.fingerprint
    assert {a.source.instance_id: a.partition for a in one.assignments} == {
        a.source.instance_id: a.partition for a in two.assignments}


def test_synthetic_sources_are_excluded_or_train_only() -> None:
    instances = (*_cohort(), _instance(20, origin="simulated"), _instance(21, origin="drawn"))
    excluded = make_split(instances, SplitConfig())
    included = make_split(instances, SplitConfig(include_synthetic_train=True))
    for number in (20, 21):
        assert excluded.partition_for(f"qa-instance-{number}") == "excluded"
        assert included.partition_for(f"qa-instance-{number}") == "train"


def test_unknown_targets_remain_unknown_and_documented_transients_keep_phase() -> None:
    config = PipelineConfig(window_rows=3, stride_rows=1)
    _, _, batch = _build(_cohort(_instance(1, [1., 2., 3., 4., 5.], labels=[0, 0, None, 101, 1])), config)
    targets = batch.targets.loc[batch.metadata.instance_id.eq("qa-instance-1")]
    assert pd.isna(targets.event_family.iloc[0])
    assert not bool(targets.supervised_eligible.iloc[0])
    assert targets.raw_class.iloc[1] == 101 and targets.event_family.iloc[1] == 1
    assert targets.phase.iloc[1] == "transient"


def test_excluding_transient_supervision_does_not_remove_its_feature_window() -> None:
    instances = _cohort(_instance(1, [1., 2., 3., 4., 5.], labels=[0, 0, None, 101, 1]))
    _, _, included = _build(instances, PipelineConfig(window_rows=3, stride_rows=1, transient_policy="family"))
    _, _, excluded = _build(instances, PipelineConfig(window_rows=3, stride_rows=1, transient_policy="exclude"))
    # The target policy legitimately changes the config-bound window ID.
    # Compare the same source endpoints and values, rather than their IDs.
    pd.testing.assert_frame_equal(included.features.reset_index(drop=True), excluded.features.reset_index(drop=True))
    pd.testing.assert_frame_equal(included.metadata[["instance_id", "endpoint_position"]].reset_index(drop=True),
                                  excluded.metadata[["instance_id", "endpoint_position"]].reset_index(drop=True))
    row = excluded.targets.loc[excluded.metadata.instance_id.eq("qa-instance-1")].iloc[1]
    assert row.raw_class == 101 and not bool(row.supervised_eligible)


def test_protected_mode_rejects_missing_exposure_ledger() -> None:
    with pytest.raises(ValueError):
        make_split(_cohort(), SplitConfig(mode="protected", required_families=(0,)))


def test_fresh_supported_synthetic_fixture_can_use_protected_software_path() -> None:
    # A positive software fixture is not a claim that current 3W data are fresh.
    ledger = ExposureLedger(instance_ids=(), real_well_ids=(), ledger_sha256="0" * 64)
    instances = tuple(_instance(i, labels=[0, 0, 0, 1, 1, 1, 0, 0, 0]) for i in range(1, 9))
    split = make_split(instances, SplitConfig(mode="protected", required_families=(0, 1)), exposure=ledger)
    pipeline = _pipeline()
    batch = pipeline.build(instances, split)
    pipeline.fit(batch.subset("train"), split)
    assert np.isfinite(pipeline.transform(batch.subset("test"), split).to_numpy()).all()


def test_protected_mode_rejects_exposed_well_even_with_new_instance_identity() -> None:
    ledger = ExposureLedger(instance_ids=(), real_well_ids=tuple(f"WELL-{i:05d}" for i in range(1, 9)), ledger_sha256="0" * 64)
    with pytest.raises(ValueError):
        make_split(_cohort(), SplitConfig(mode="protected", required_families=(0,)), exposure=ledger)


def test_protected_mode_rejects_absent_required_class_support() -> None:
    ledger = ExposureLedger(instance_ids=(), real_well_ids=(), ledger_sha256="0" * 64)
    with pytest.raises(ValueError):
        make_split(_cohort(), SplitConfig(mode="protected", required_families=(0, 9)), exposure=ledger)


def test_protected_support_cannot_be_satisfied_by_labels_before_first_endpoint() -> None:
    ledger = ExposureLedger(instance_ids=(), real_well_ids=(), ledger_sha256="0" * 64)
    instances = tuple(_instance(i, labels=[9, 0, 0, 0, 0, 0, 0, 0, 0]) for i in range(1, 9))
    with pytest.raises(ValueError):
        split = make_split(instances, SplitConfig(mode="protected", required_families=(0, 9)), exposure=ledger)
        _pipeline().build(instances, split)


@pytest.mark.parametrize("sensor", ["class", "state", "timestamp", "well_id", "source_path"])
def test_labels_time_and_source_metadata_cannot_be_selected_as_sensors(sensor: str) -> None:
    with pytest.raises(ValueError):
        CausalFeaturePipeline(PipelineConfig(window_rows=3), (sensor,))


def test_saved_pipeline_roundtrip_is_exact_and_tampering_is_rejected(tmp_path: Path) -> None:
    pipeline, split, batch = _build(_cohort())
    pipeline.fit(batch.subset("train"), split)
    path = tmp_path / "pipeline.json"
    pipeline.save(path)
    restored = CausalFeaturePipeline.load(path)
    pd.testing.assert_frame_equal(pipeline.transform(batch, split), restored.transform(batch, split))
    saved = json.loads(path.read_text())
    saved["qa_unexpected_field"] = True
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError):
        CausalFeaturePipeline.load(path)


def test_mutating_built_batch_cannot_forge_train_membership() -> None:
    pipeline, split, batch = _build(_cohort())
    batch.metadata.loc[:, "partition"] = "train"
    with pytest.raises(ValueError):
        pipeline.fit(batch, split)


@pytest.mark.parametrize("invalid", [-1, 10, 100, 103])
def test_undocumented_target_codes_are_rejected(invalid: int) -> None:
    with pytest.raises(ValueError):
        _build(_cohort(_instance(1, labels=[invalid] * 9)))


def test_different_frozen_split_cannot_be_used_for_transform() -> None:
    instances = _cohort()
    pipeline, split, batch = _build(instances)
    pipeline.fit(batch.subset("train"), split)
    other_split = make_split(instances, SplitConfig(seed=123))
    with pytest.raises(ValueError):
        pipeline.transform(batch, other_split)


def test_unsupervised_statistics_can_use_unknown_label_training_windows() -> None:
    instances = tuple(_instance(i, labels=[None] * 9) for i in range(1, 9))
    pipeline, split, batch = _build(instances)
    assert batch.targets.event_family.isna().all()
    assert not batch.targets.supervised_eligible.any()
    pipeline.fit(batch.subset("train"), split)
    assert pipeline.state is not None
    assert pipeline.state.training_window_count == len(batch.subset("train").features)


def _acquired_fixture(root: Path) -> tuple[Path, dict]:
    """Write a tiny original-like Parquet, without using acquisition code."""
    revision = "914af287b1cf3e5207dce0da1e9dc08361c9adeb"
    source = "dataset/0/WELL-00001_20200101000000.parquet"
    relative = f"data/raw/3w/2.0.0/{revision}/{source}"
    parquet = root / relative
    parquet.parent.mkdir(parents=True)
    _instance(1).frame.to_parquet(parquet, engine="pyarrow")
    payload = parquet.read_bytes()
    entry = {
        "source_path": source, "local_path": relative, "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "git_blob_sha1": hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest(),
        "source_kind": "real", "event_code": 0, "well_identifier": "WELL-00001",
        "source_instance_id": "3w:" + hashlib.sha256(f"{revision}:{source}".encode()).hexdigest(),
    }
    manifest = {"schema_version": "1.0.0", "status": "complete",
                "dataset": {"revision": revision, "version": "2.0.0"}, "files": [entry]}
    directory = root / "data/manifests"
    directory.mkdir(parents=True)
    (directory / "dataset_metadata.json").write_bytes((ROOT / "data/manifests/dataset_metadata.json").read_bytes())
    path = directory / "subset.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


def test_valid_loader_preserves_original_bytes_and_metadata(tmp_path: Path) -> None:
    _, manifest = _acquired_fixture(tmp_path)
    entry = manifest["files"][0]
    raw = tmp_path / entry["local_path"]
    before = raw.read_bytes()
    instances = load_instances(tmp_path)
    assert len(instances) == 1
    assert instances[0].metadata.well_id == "WELL-00001"
    assert instances[0].metadata.sha256 == entry["sha256"]
    assert instances[0].metadata.instance_id == entry["source_instance_id"]
    assert raw.read_bytes() == before


@pytest.mark.parametrize("alteration", [
    {"well_identifier": "WELL-00002"},
    {"source_kind": "simulated", "well_identifier": None},
    {"event_code": 1},
    {"source_instance_id": "qa-forged-instance"},
])
def test_valid_bytes_cannot_hide_forged_manifest_group_identity(tmp_path: Path, alteration: dict) -> None:
    path, manifest = _acquired_fixture(tmp_path)
    manifest["files"][0].update(alteration)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_instances(tmp_path)


def _rehash(payload: dict) -> dict:
    body = {key: value for key, value in payload.items() if key != "fingerprint"}
    payload["fingerprint"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return payload


@pytest.mark.parametrize("relationship", ["well", "bytes"])
def test_deserialized_manifest_rechecks_group_relations_beyond_checksum(relationship: str) -> None:
    common_sha = hashlib.sha256(b"qa-shared-bytes").hexdigest()
    first = _instance(1, sha=common_sha if relationship == "bytes" else None)
    second = _instance(2, well=1 if relationship == "well" else 2,
                       sha=common_sha if relationship == "bytes" else None)
    split = make_split((first, second, *(_instance(i) for i in range(3, 10))))
    payload = split.model_dump(mode="json")
    altered = next(a for a in payload["assignments"] if a["source"]["instance_id"] == "qa-instance-2")
    altered["group_id"] = "f" * 64
    altered["partition"] = "validation" if altered["partition"] == "train" else "train"
    with pytest.raises(ValueError):
        SplitManifest.model_validate(_rehash(payload))


def test_deserialized_manifest_cannot_move_synthetic_source_into_holdout() -> None:
    split = make_split((*_cohort(), _instance(20, origin="simulated")),
                       SplitConfig(include_synthetic_train=True))
    payload = split.model_dump(mode="json")
    synthetic = next(a for a in payload["assignments"] if a["source"]["origin"] == "simulated")
    synthetic["partition"] = "test"
    with pytest.raises(ValueError):
        SplitManifest.model_validate(_rehash(payload))


def test_deserialized_protected_manifest_requires_exposure_provenance() -> None:
    ledger = ExposureLedger(instance_ids=(), real_well_ids=(), ledger_sha256="0" * 64)
    split = make_split(_cohort(), SplitConfig(mode="protected", required_families=(0,)), exposure=ledger)
    payload = split.model_dump(mode="json")
    payload["exposure_sha256"] = None
    with pytest.raises(ValueError):
        SplitManifest.model_validate(_rehash(payload))


@pytest.mark.parametrize("statement", [
    "from ml.features import feature_names, summarize_windows; from ml.data_pipeline import CausalFeaturePipeline",
    "from ml.data_pipeline import CausalFeaturePipeline; from ml.features import feature_names, summarize_windows",
])
def test_public_packages_import_in_fresh_process_in_either_order(statement: str) -> None:
    result = subprocess.run([sys.executable, "-c", statement], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
