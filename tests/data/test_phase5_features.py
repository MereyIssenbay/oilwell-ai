"""Independent Phase 5 feature checks using synthetic observations only."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.data_pipeline import (  # noqa: E402
    CausalFeaturePipeline, Instance, PipelineConfig, SENSOR_COLUMNS,
    SourceMetadata, make_split,
)
from ml.features import summarize_windows  # noqa: E402
from ml.train_baseline import select_training_partitions  # noqa: E402


def _sources() -> tuple[Instance, ...]:
    result = []
    for number in range(1, 4):
        index = pd.date_range("2024-01-01", periods=12, freq="s", name="timestamp")
        frame = pd.DataFrame(np.nan, index=index, columns=SENSOR_COLUMNS)
        frame["P-TPT"] = np.arange(12, dtype=float) + number
        frame["ESTADO-DHSV"] = np.ones(12)
        frame["class"] = pd.array([0] * 12, dtype="Int16")
        frame["state"] = pd.array([0] * 12, dtype="Int16")
        metadata = SourceMetadata(
            instance_id=f"phase5-feature-fixture-{number}",
            source_path=f"fixture/{number}",
            sha256=hashlib.sha256(str(number).encode()).hexdigest(),
            origin="real", well_id=f"WELL-{number:05}",
        )
        result.append(Instance(metadata, frame))
    return tuple(result)


@pytest.mark.parametrize("window_rows", [3, 60])
def test_future_changes_cannot_affect_features_across_processing_chunks(window_rows: int) -> None:
    """Exercise over 512 endpoints, including the implementation chunk boundary."""
    rng = np.random.default_rng(193)
    observations = rng.normal(size=(800, 3))
    observations[::7, 1] = np.nan
    endpoints = np.arange(window_rows - 1, 700)
    expected, expected_counts = summarize_windows(observations, endpoints, window_rows, 1.0)
    changed = observations.copy()
    changed[700:] = 1e12
    actual, actual_counts = summarize_windows(changed, endpoints, window_rows, 1.0)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual_counts, expected_counts)


def test_summary_vector_does_not_preserve_full_trajectory() -> None:
    """A concrete compression limit, not evidence that a sequence model improves ML."""
    first = np.array([0, 1, 2, 3, 2, 1, 0], dtype=float)
    second = np.array([0, 2, 1, 3, 1, 2, 0], dtype=float)
    assert not np.array_equal(first, second)
    a, _ = summarize_windows(first[:, None], np.array([6]), 7, 1.0)
    b, _ = summarize_windows(second[:, None], np.array([6]), 7, 1.0)
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-15)


def test_discrete_valve_sensor_is_preserved_but_auxiliary_labels_do_not_change_features() -> None:
    sources = _sources()
    split = make_split(sources)
    pipeline = CausalFeaturePipeline(PipelineConfig(window_rows=4, stride_rows=2),
                                    ("P-TPT", "ESTADO-DHSV"))
    original = pipeline.build(sources, split)
    changed = []
    for source in sources:
        frame = source.frame.copy()
        frame["class"] = pd.array([108] * len(frame), dtype="Int16")
        frame["state"] = pd.array([8] * len(frame), dtype="Int16")
        changed.append(Instance(source.metadata, frame))
    relabeled = pipeline.build(changed, split)
    pd.testing.assert_frame_equal(original.features, relabeled.features)
    pd.testing.assert_frame_equal(original.quality, relabeled.quality)
    assert original.features["ESTADO-DHSV__mean"].eq(1).all()
    assert original.targets.event_family.eq(0).all()
    assert relabeled.targets.event_family.eq(8).all()
    assert not any(name.split("__")[0] in {"class", "state"} for name in original.features)


def test_observations_only_in_train_dropped_sensor_do_not_make_usable_model_evidence() -> None:
    sources = _sources()
    split = make_split(sources)
    changed = []
    for source in sources:
        frame = source.frame.copy()
        if split.partition_for(source.metadata.instance_id) == "validation":
            frame["P-TPT"] = np.nan
            frame["P-PDG"] = np.arange(len(frame), dtype=float)
        changed.append(Instance(source.metadata, frame))
    pipeline = CausalFeaturePipeline(PipelineConfig(window_rows=4, stride_rows=2),
                                    ("P-TPT", "P-PDG"))
    batch = pipeline.build(changed, split)
    pipeline.fit(batch.subset("train"), split)
    normalized = pipeline.transform(batch, split)
    assert pipeline.state is not None
    _, validation = select_training_partitions(
        normalized, batch.targets, batch.metadata, batch.quality,
        pipeline.state.retained_features, split,
    )
    assert np.isfinite(validation.features.to_numpy()).all()
    assert validation.targets.supervised_eligible.all()
    assert not validation.evidence_mask.any()
    assert not validation.eligible.any()


def test_training_constant_features_are_retained_without_learning_holdout_scale() -> None:
    sources = _sources()
    split = make_split(sources)
    changed = []
    for source in sources:
        frame = source.frame.copy()
        if split.partition_for(source.metadata.instance_id) == "train":
            frame["P-TPT"] = 5.0
        else:
            frame["P-TPT"] = np.arange(len(frame), dtype=float) * 1000
        changed.append(Instance(source.metadata, frame))
    pipeline = CausalFeaturePipeline(PipelineConfig(window_rows=4, stride_rows=2), ("P-TPT",))
    batch = pipeline.build(changed, split)
    pipeline.fit(batch.subset("train"), split)
    assert pipeline.state is not None
    before = pipeline.state.model_dump_json()
    transformed = pipeline.transform(batch, split)
    assert len(pipeline.state.retained_features) == 6
    assert pipeline.state.scales == (1.0,) * 6
    assert transformed.loc[batch.metadata.partition.eq("train")].eq(0).all().all()
    assert transformed.loc[batch.metadata.partition.eq("validation")].abs().to_numpy().max() > 100
    assert pipeline.state.model_dump_json() == before
