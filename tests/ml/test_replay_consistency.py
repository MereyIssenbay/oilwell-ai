"""Frozen train/validation-only replay consistency and causal input checks.

These are software integration checks, not a second model-quality evaluation.
Original raw/model files and the one-shot test journal must remain unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from backend.app.inference import Runtime
from backend.app.registry import Registry, trusted_selection
from backend.app.schemas import PredictRequest

ROOT = Path(__file__).resolve().parents[2]
DEMO_SOURCE = "3w:3b7750afe480cb1d04361795d4a5cded832ae3a05d5ef30f533d440c81bfb4cf"


@pytest.fixture(scope="module")
def frozen():
    selection = trusted_selection(ROOT)
    bundle = ROOT / selection["bundle_path"]
    if not (bundle / "model.joblib").exists():
        pytest.skip("Locally acquired data and frozen Phase 5 model are required")
    journal = ROOT / "reports/experiments/test_access.json"
    protected = [journal, ROOT / "ml/predict.py", ROOT / "reports/experiments/selection.json"]
    protected.extend(bundle / name for name in ("manifest.json", "model.joblib", "preprocessor.json", "split.json"))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    registry = Registry(ROOT)
    registry.startup()
    runtime = Runtime(registry, ROOT)
    runtime.startup()
    saved_path = ROOT / selection["validation_predictions_path"]
    assert hashlib.sha256(saved_path.read_bytes()).hexdigest() == selection["validation_predictions_sha256"]
    saved = pd.read_parquet(saved_path, filters=[("model", "==", selection["candidate_id"])])
    assert set(saved.partition) == {"validation"}
    assert all(sid in registry.records for sid in saved.instance_id.unique())
    yield registry, runtime, saved
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected} == before


def test_source_boundary_window_matches_frozen_offline_score(frozen):
    registry, runtime, saved = frozen
    checked = []
    for sid, rows in saved.groupby("instance_id"):
        expected = rows.sort_values("endpoint_position").iloc[0]
        prediction = runtime.predict(PredictRequest(source_instance_id=sid,
            endpoint_position=int(expected.endpoint_position)), uuid4(), datetime.now(timezone.utc))
        assert np.isclose(prediction.abnormal_score, expected.score, atol=1e-14, rtol=0)
        assert (prediction.alert_status == "alert") == bool(expected.predicted)
        assert prediction.window.sample_count == 60
        assert prediction.provenance.source_sha256 == registry.record(sid).source.sha256
        checked.append(sid)
    assert len(checked) == 3


def test_future_sensor_perturbations_cannot_change_past_windows(frozen):
    registry, runtime, _ = frozen
    original = registry.record(DEMO_SOURCE).frame.iloc[5600:5860].copy(deep=True)
    poisoned = original.copy(deep=True)
    # Changes begin strictly AFTER row 5709, including missingness changes.
    poisoned.iloc[110:] = 1e6
    expected = runtime.predictor.predict_instance(original)
    actual = runtime.predictor.predict_instance(poisoned)
    past = expected.index <= original.index[109]
    np.testing.assert_allclose(actual.loc[past, "score"], expected.loc[past, "score"], atol=1e-14, rtol=0)
    pd.testing.assert_series_equal(actual.loc[past, "predicted"], expected.loc[past, "predicted"])
    assert not np.allclose(actual.loc[~past, "score"], expected.loc[~past, "score"], atol=1e-14, rtol=0)


def test_runtime_cannot_observe_future_or_cross_source_boundaries(frozen, monkeypatch):
    registry, runtime, _ = frozen
    original_predict = type(runtime.predictor).predict_instance
    observed = []

    def inspected(predictor, sensors):
        observed.append(sensors.copy(deep=True))
        return original_predict(predictor, sensors)

    monkeypatch.setattr(type(runtime.predictor), "predict_instance", inspected)
    for sid in (DEMO_SOURCE, next(s for s in registry.records if s != DEMO_SOURCE)):
        runtime.predict(PredictRequest(source_instance_id=sid, endpoint_position=59), uuid4(), datetime.now(timezone.utc))
        pd.testing.assert_frame_equal(observed[-1], registry.record(sid).frame.iloc[:60])
        assert set(observed[-1]) == set(registry.sensor_names)
        assert "class" not in observed[-1] and "state" not in observed[-1]


@pytest.mark.parametrize("label", ["class", "state"])
def test_original_labels_are_rejected_as_inference_inputs(frozen, label):
    registry, runtime, _ = frozen
    sensors = registry.record(DEMO_SOURCE).frame.iloc[:60].copy(deep=True)
    sensors[label] = 0
    with pytest.raises(ValueError, match="sensor-only"):
        runtime.predictor.predict_instance(sensors)


def test_short_history_is_abstention_and_missing_evidence_never_normal(frozen):
    registry, runtime, _ = frozen
    frame = registry.record(DEMO_SOURCE).frame.iloc[:60].copy(deep=True)
    short = runtime.predictor.predict_instance(frame.iloc[:59])
    assert short.empty and short.attrs["empty_reason"] == "insufficient_history"
    frame.iloc[:] = np.nan
    missing = runtime.predictor.predict_instance(frame).iloc[0]
    assert missing.abstention_reason == "missing_required_sensors"
    assert pd.isna(missing.predicted) and pd.isna(missing.score)


def _replay(frozen, start, end, speed):
    from backend.app.replay import ReplayService
    from backend.app.replay_repository import MemoryReplayRepository
    from backend.app.replay_schemas import CreateReplay, ReplayCommand

    registry, runtime, _ = frozen
    store = MemoryReplayRepository()
    service = ReplayService(registry, runtime, store)
    snapshot, repeated = service.create(CreateReplay(source_instance_id=DEMO_SOURCE,
        start_position=start, end_position=end, speed_multiplier=speed), str(uuid4()))
    assert repeated is False
    rid = snapshot["replay_id"]
    service.command(rid, ReplayCommand(command="start", expected_version=1), str(uuid4()))
    for position in range(start, end + 1):
        assert service.step(rid, ignore_schedule=True)
        assert store.get(rid)["cursor_position"] == position
    assert store.get(rid)["state"] == "completed"
    assert service.step(rid, ignore_schedule=True) is False
    return store.events(rid, limit=1000)["items"]


@pytest.mark.parametrize("speed", [0.1, 1.0, 20.0])
def test_all_replay_demo_predictions_match_saved_validation_at_every_speed(frozen, speed):
    registry, _, saved = frozen
    events = _replay(frozen, 5600, 5859, speed)
    predictions = [event for event in events if event["event_type"] == "prediction"]
    telemetry = [event for event in events if event["event_type"] == "telemetry"]
    expected = saved.loc[(saved.instance_id == DEMO_SOURCE)
                        & saved.endpoint_position.between(5659, 5859)].set_index("endpoint_position")
    assert len(predictions) == len(expected) == 21
    assert [e["payload"]["source_position"] for e in telemetry] == list(range(5600, 5860))
    assert [e["payload"]["timestamp"] for e in telemetry] == [t.isoformat() for t in registry.record(DEMO_SOURCE).frame.index[5600:5860]]
    for event in predictions:
        envelope = event["payload"]
        position = envelope["source_position"]
        value = envelope["prediction"]
        assert envelope["speed_multiplier"] == speed
        assert envelope["sequence"] == event["sequence"]
        assert envelope["mode"] == event["mode"] == "historical_replay"
        assert envelope["simulated_playback"] is True
        assert np.isclose(value["abnormal_score"], expected.loc[position, "score"], atol=1e-14, rtol=0)
        assert (value["alert_status"] == "alert") == bool(expected.loc[position, "predicted"])
        assert pd.Timestamp(value["timestamp"]).tz_localize(None) == expected.loc[position, "timestamp"]
        assert value["window"]["sample_count"] == 60
        assert "class" not in value and "state" not in value
    episodes = [e["payload"] for e in events if e["event_type"] == "alert_episode"]
    assert [(e["transition"], e["source_position"]) for e in episodes
            if e["transition"] in {"opened", "resolved"}] == [("opened", 5659), ("resolved", 5809), ("opened", 5849)]
    assert len({e["episode_id"] for e in episodes}) == 2


def test_unaligned_replay_start_waits_for_full_local_history_and_global_stride(frozen, monkeypatch):
    registry, runtime, _ = frozen
    original_predict = type(runtime.predictor).predict_instance
    inputs = []

    def inspect(predictor, sensors):
        inputs.append(sensors.copy(deep=True))
        return original_predict(predictor, sensors)

    monkeypatch.setattr(type(runtime.predictor), "predict_instance", inspect)
    events = _replay(frozen, 5603, 5689, 20.0)
    positions = [e["payload"]["source_position"] for e in events if e["event_type"] == "prediction"]
    # 5659 is globally aligned but has only 57 replay-local observations.
    # 5662 has 60 local observations but is not a frozen global endpoint.
    assert positions == [5669, 5679, 5689]
    assert len(inputs) == 3
    for position, sensors in zip(positions, inputs):
        pd.testing.assert_frame_equal(sensors, registry.record(DEMO_SOURCE).frame.iloc[position - 59:position + 1])
        assert sensors.index[0] >= registry.record(DEMO_SOURCE).frame.index[5603]
        assert sensors.index[-1] == registry.record(DEMO_SOURCE).frame.index[position]


def test_replay_shorter_than_window_emits_no_prediction(frozen):
    events = _replay(frozen, 5603, 5661, 20.0)
    assert sum(e["event_type"] == "telemetry" for e in events) == 59
    assert not any(e["event_type"] in {"prediction", "alert_episode"} for e in events)
