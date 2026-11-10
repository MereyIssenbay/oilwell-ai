"""Reusable pipeline checks using explicit synthetic fixtures, never model metrics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.data_pipeline import (  # noqa: E402
    SENSOR_COLUMNS, CausalFeaturePipeline, Instance, PipelineConfig, SourceMetadata,
    SplitConfig, SplitManifest, load_exposure, load_instances, make_split,
)
from ml.data_pipeline.io import read_json  # noqa: E402


def instance(number: int, *, size: int = 12, well: int | None = None,
             origin: str = "real", values: np.ndarray | None = None) -> Instance:
    index = pd.date_range("2020-01-01", periods=size, freq="s", name="timestamp")
    frame = pd.DataFrame(np.nan, index=index, columns=SENSOR_COLUMNS)
    frame["P-TPT"] = np.arange(size, dtype=float) + number if values is None else values
    frame["class"] = pd.array([0] * size, dtype="Int16")
    frame["state"] = pd.array([0] * size, dtype="Int16")
    metadata = SourceMetadata(instance_id=f"fixture-{number}", source_path=f"fixture/{number}",
                              sha256=hashlib.sha256(str(number).encode()).hexdigest(),
                              origin=origin, well_id=f"WELL-{well or number:05}" if origin == "real" else None)
    return Instance(metadata, frame)


def cohort() -> tuple[Instance, ...]:
    return tuple(instance(i) for i in range(1, 10))


def pipeline() -> CausalFeaturePipeline:
    return CausalFeaturePipeline(PipelineConfig(window_rows=4, stride_rows=2), ("P-TPT",))


def test_windows_obey_configurable_start_end_stride_and_instance_boundaries() -> None:
    sources = cohort()
    split = make_split(sources)
    batch = pipeline().build(sources, split)
    assert len(batch.features) == 9 * 5
    assert batch.features.index.is_unique
    for _, records in batch.metadata.groupby("instance_id"):
        assert records.endpoint_position.tolist() == [3, 5, 7, 9, 11]
        assert ((records.timestamp - records.window_start).dt.total_seconds() == 3).all()


def test_seed_and_input_order_produce_byte_stable_split_and_batch() -> None:
    sources = cohort()
    first = make_split(sources, SplitConfig(seed=123))
    second = make_split(tuple(reversed(sources)), SplitConfig(seed=123))
    assert first.model_dump_json() == second.model_dump_json()
    a = pipeline().build(sources, first)
    b = pipeline().build(tuple(reversed(sources)), second)
    assert a.content_fingerprint == b.content_fingerprint
    pd.testing.assert_frame_equal(a.features, b.features)
    assert first.fingerprint != make_split(sources, SplitConfig(seed=124)).fingerprint


def test_split_json_roundtrip_and_corruption_fail_closed() -> None:
    split = make_split(cohort())
    assert SplitManifest.model_validate_json(split.model_dump_json()) == split
    altered = split.model_dump(mode="json")
    altered["assignments"][0]["partition"] = "test" if altered["assignments"][0]["partition"] == "train" else "train"
    with pytest.raises(ValueError, match="fingerprint"):
        SplitManifest.model_validate(altered)


def test_related_generator_families_stay_training_only_if_enabled() -> None:
    sources = cohort() + (instance(21, origin="simulated"), instance(22, origin="drawn"))
    default = make_split(sources)
    assert default.partition_for("fixture-21") == default.partition_for("fixture-22") == "excluded"
    augmented = make_split(sources, SplitConfig(include_synthetic_train=True))
    assert augmented.partition_for("fixture-21") == augmented.partition_for("fixture-22") == "train"


def test_exact_sensor_time_duplicate_content_grouped_even_if_byte_hash_differs() -> None:
    sources = list(cohort())
    sources[1] = Instance(sources[1].metadata, sources[0].frame.copy())
    split = make_split(sources)
    left, right = split.assignment_for("fixture-1"), split.assignment_for("fixture-2")
    assert left.group_id == right.group_id
    assert left.partition == right.partition


def test_short_instances_do_not_fabricate_partial_windows() -> None:
    sources = (instance(1, size=2), *cohort()[1:])
    split = make_split(sources)
    batch = pipeline().build(sources, split)
    assert "fixture-1" not in set(batch.metadata.instance_id)


def test_declared_cadence_changes_rate_units_without_resampling() -> None:
    sources = []
    for source in cohort():
        frame = source.frame.copy()
        frame.index = pd.date_range("2020-01-01", periods=len(frame), freq="2s", name="timestamp")
        sources.append(Instance(source.metadata, frame))
    split = make_split(sources)
    batch = CausalFeaturePipeline(PipelineConfig(window_rows=4, cadence_seconds=2), ("P-TPT",)).build(sources, split)
    np.testing.assert_allclose(batch.features["P-TPT__rate"], 0.5)
    np.testing.assert_allclose(batch.features["P-TPT__trend"], 0.5)
    with pytest.raises(ValueError, match="resampling"):
        CausalFeaturePipeline(PipelineConfig(window_rows=4, cadence_seconds=3), ("P-TPT",)).build(sources, split)


def test_fit_uses_unknown_training_endpoints_without_relabeling_them_normal() -> None:
    sources = cohort()
    for source in sources:
        source.frame["class"] = pd.array([None] * len(source.frame), dtype="Int16")
    split = make_split(sources)
    processor = pipeline()
    batch = processor.build(sources, split)
    assert batch.targets.event_family.isna().all()
    assert not batch.targets.supervised_eligible.any()
    processor.fit(batch.subset("train"), split)
    assert processor.state.training_window_count == len(batch.subset("train").features)
    assert np.isfinite(processor.transform(batch, split).to_numpy()).all()


def test_all_missing_windows_are_visible_and_not_supervised_eligible() -> None:
    sources = cohort()
    sources[0].frame.loc[:, "P-TPT"] = np.nan
    split = make_split(sources)
    processor = pipeline()
    batch = processor.build(sources, split)
    mask = batch.metadata.instance_id.eq("fixture-1")
    assert batch.quality.loc[mask, "all_missing"].all()
    assert batch.quality.loc[mask, "observed_cells"].eq(0).all()
    assert not batch.targets.loc[mask, "supervised_eligible"].any()
    assert batch.targets.loc[mask, "event_family"].eq(0).all()


def test_state_is_frozen_against_refitting_and_configuration_changes() -> None:
    sources = cohort()
    split = make_split(sources)
    processor = pipeline()
    batch = processor.build(sources, split)
    processor.fit(batch.subset("train"), split)
    with pytest.raises(ValueError, match="frozen"):
        processor.fit(batch.subset("train"), split)
    processor.config = PipelineConfig(window_rows=8)
    with pytest.raises(ValueError):
        processor.transform(batch, split)


def test_estados_are_registry_sensor_inputs_while_auxiliary_state_is_excluded() -> None:
    sources = cohort()
    for source in sources:
        source.frame["ESTADO-DHSV"] = np.array([0, 0.5, 1] * 4, dtype=float)
    split = make_split(sources)
    processor = CausalFeaturePipeline(PipelineConfig(window_rows=3), ("ESTADO-DHSV",))
    batch = processor.build(sources, split)
    assert batch.features["ESTADO-DHSV__mean"].eq(0.5).all()
    with pytest.raises(ValueError, match="registry"):
        CausalFeaturePipeline(sensor_names=("state",))


def _write_acquisition(root: Path) -> tuple[Path, Path]:
    """Write offline synthetic Parquets in the actual acquisition contract."""
    revision = "914af287b1cf3e5207dce0da1e9dc08361c9adeb"
    source_path = "dataset/0/WELL-00001_20200101000000.parquet"
    local_path = f"data/raw/3w/2.0.0/{revision}/{source_path}"
    target = root / local_path
    target.parent.mkdir(parents=True)
    instance(1).frame.to_parquet(target, engine="pyarrow")
    payload = target.read_bytes()
    metadata = {"source_path": source_path, "local_path": local_path,
                "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "git_blob_sha1": hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest(),
                "source_kind": "real", "event_code": 0, "well_identifier": "WELL-00001",
                "source_instance_id": "3w:" + hashlib.sha256(f"{revision}:{source_path}".encode()).hexdigest()}
    manifest = {"schema_version": "1.0.0", "status": "complete",
                "dataset": {"revision": revision, "version": "2.0.0"}, "files": [metadata]}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry_path = root / "registry.json"
    registry_path.write_text((ROOT / "data/manifests/dataset_metadata.json").read_text(), encoding="utf-8")
    return manifest_path, registry_path


def test_original_loader_checks_bytes_types_provenance_and_is_read_only(tmp_path: Path) -> None:
    manifest_path, registry_path = _write_acquisition(tmp_path)
    manifest = read_json(manifest_path)
    raw = tmp_path / manifest["files"][0]["local_path"]
    before = (raw.read_bytes(), raw.stat().st_mtime_ns)
    sources = load_instances(tmp_path, manifest_path, registry_path)
    assert sources[0].metadata.manifest_sha256 == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert sources[0].metadata.registry_sha256 == hashlib.sha256(registry_path.read_bytes()).hexdigest()
    assert tuple(sources[0].frame.columns) == (*SENSOR_COLUMNS, "class", "state")
    assert before == (raw.read_bytes(), raw.stat().st_mtime_ns)
    raw.write_bytes(raw.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        load_instances(tmp_path, manifest_path, registry_path)


@pytest.mark.parametrize("field,value", [("well_identifier", "WELL-00099"),
                                        ("source_kind", "drawn"), ("event_code", 9),
                                        ("source_instance_id", "arbitrary"),
                                        ("local_path", "data/raw/elsewhere.parquet")])
def test_loader_rejects_identity_override_even_when_file_checksum_is_valid(tmp_path: Path,
                                                                         field: str, value: object) -> None:
    manifest_path, registry_path = _write_acquisition(tmp_path)
    payload = read_json(manifest_path)
    payload["files"][0][field] = value
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        load_instances(tmp_path, manifest_path, registry_path)


def test_loader_rejects_duplicate_source_path(tmp_path: Path) -> None:
    manifest_path, registry_path = _write_acquisition(tmp_path)
    payload = read_json(manifest_path)
    payload["files"].append(payload["files"][0].copy())
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate source path"):
        load_instances(tmp_path, manifest_path, registry_path)


def test_json_and_exposure_loader_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "malformed.json"
    for text in ('{"a":1,"a":2}', '{"value":NaN}', '[]'):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            read_json(path)
    path.write_text('{"eda_exposure":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="exposure"):
        load_exposure(path)


def test_save_load_retains_exact_finite_transformation(tmp_path: Path) -> None:
    sources = cohort()
    split = make_split(sources)
    processor = pipeline()
    batch = processor.build(sources, split)
    processor.fit(batch.subset("train"), split)
    expected = processor.transform(batch, split)
    path = tmp_path / "preprocessor.json"
    processor.save(path)
    loaded = CausalFeaturePipeline.load(path)
    pd.testing.assert_frame_equal(expected, loaded.transform(batch, split))
    assert processor.state.fingerprint == loaded.state.fingerprint
