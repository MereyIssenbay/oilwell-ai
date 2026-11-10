"""Independent additive replay input/identity contract checks."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from jsonschema import Draft202012Validator

from backend.app.replay_schemas import CreateReplay, Playback, ReplayCommand, ReplayEvent, ReplayPrediction, ReplaySnapshot
from tests.contract.test_diagnostic_api_contract import synthetic_prediction

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("filename,model", [
    ("replay_prediction.schema.json", ReplayPrediction),
    ("replay_snapshot.schema.json", ReplaySnapshot),
    ("replay_event.schema.json", ReplayEvent),
])
def test_exported_replay_schema_matches_current_typed_contract(filename, model):
    exported = json.loads((ROOT / "docs/contracts" / filename).read_text())
    Draft202012Validator.check_schema(exported)
    assert exported == {"$schema": "https://json-schema.org/draft/2020-12/schema", **model.model_json_schema()}


def test_prior_canonical_and_diagnostic_schema_bytes_are_unchanged():
    for path, expected in {
        "prediction.schema.json": "a581953b0a2875e90c2a91204c9d50b60a92a269e948a03b90f840dc0ac6309f",
        "diagnostic_prediction.schema.json": "6e1c6734c41651977cde122b39477c641bcc8384a921f644a725200f979f5a91",
    }.items():
        assert hashlib.sha256((ROOT / "docs/contracts" / path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("field,value", [
    ("start_position", True), ("start_position", "0"), ("start_position", -1),
    ("end_position", 2.5), ("end_position", False),
    ("speed_multiplier", True), ("speed_multiplier", "2"), ("speed_multiplier", 0.0),
    ("speed_multiplier", 20.1), ("speed_multiplier", float("nan")),
    ("speed_multiplier", float("inf")), ("source_instance_id", 123),
    ("source_path", "dataset/0/private.parquet"), ("class", 1), ("state", 0),
    ("threshold", .9), ("split", "test"),
])
def test_create_rejects_malformed_or_target_and_policy_overrides(field, value):
    with pytest.raises(ValidationError):
        CreateReplay.model_validate({"source_instance_id": "qa-source", field: value})


@pytest.mark.parametrize("speed", [.1, 1, 20.0])
def test_numeric_playback_speed_boundary_values(speed):
    assert CreateReplay(source_instance_id="qa-source", speed_multiplier=speed).speed_multiplier == speed


@pytest.mark.parametrize("data", [
    {"command": "set_speed", "expected_version": 1},
    {"command": "start", "expected_version": 1, "speed_multiplier": 2},
    {"command": "resume", "expected_version": True},
    {"command": "stop", "expected_version": "1"},
    {"command": "stop", "expected_version": 0},
    {"command": "rewind", "expected_version": 1},
    {"command": "set_speed", "expected_version": 1, "speed_multiplier": 21},
])
def test_commands_require_exact_version_and_speed_only_for_speed_change(data):
    with pytest.raises(ValidationError):
        ReplayCommand.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("mode", "live"), ("mode", "historical_inference"),
    ("simulated_playback", False), ("simulated_playback", 1),
    ("diagnostic_only", False), ("diagnostic_only", 1),
    ("accepted_for_monitoring", True), ("accepted_for_monitoring", 0),
])
def test_playback_identity_cannot_be_silently_reinterpreted(field, value):
    with pytest.raises(ValidationError):
        Playback.model_validate({field: value})


def test_playback_identity_is_distinct_from_source_origin():
    value = Playback().model_dump(mode="json")
    assert value == {"schema_version": "diagnostic-replay-1.0.0", "mode": "historical_replay",
                     "simulated_playback": True, "diagnostic_only": True, "accepted_for_monitoring": False}
    assert "source_kind" not in value


def usable_envelope():
    rid = str(uuid4())
    prediction = synthetic_prediction()
    episode = {"episode_id": str(uuid4()), "replay_id": rid,
               "opened_by_prediction_id": prediction["prediction_id"], "opened_at": prediction["timestamp"],
               "last_prediction_id": prediction["prediction_id"], "last_prediction_at": prediction["timestamp"],
               "last_data_status": "alert", "threshold": prediction["threshold"], "model_version": prediction["model_version"]}
    return {"replay_id": rid, "sequence": 61, "source_position": 59, "speed_multiplier": 1.0,
            "alert_episode": episode, "prediction": prediction}


@pytest.mark.parametrize("mutation", ["missing_episode", "normal_with_episode", "wrong_episode_status",
                                     "wrong_replay", "future_episode", "wrong_position", "wrong_prediction_id"])
def test_replay_prediction_episode_is_a_snapshot_of_current_decision(mutation):
    value = usable_envelope()
    assert ReplayPrediction.model_validate(value)
    if mutation == "missing_episode":
        value["alert_episode"] = None
    elif mutation == "normal_with_episode":
        value["prediction"].update(event_type="normal", abnormal_score=.2, confidence=.8, alert_status="normal")
    elif mutation == "wrong_episode_status":
        value["alert_episode"]["last_data_status"] = "insufficient_data"
    elif mutation == "wrong_replay":
        value["alert_episode"]["replay_id"] = str(uuid4())
    elif mutation == "future_episode":
        value["alert_episode"]["opened_at"] = "2027-01-01T00:00:00Z"
    elif mutation == "wrong_position":
        value["source_position"] = 60
    else:
        value["alert_episode"]["last_prediction_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        ReplayPrediction.model_validate(value)


@pytest.mark.parametrize("mutation", ["label", "future", "wrong_kind", "wrong_replay", "wrong_sequence"])
def test_typed_event_payload_rejects_labels_future_fields_and_identity_drift(mutation):
    envelope = usable_envelope()
    event = {"replay_id": envelope["replay_id"], "sequence": envelope["sequence"], "event_type": "prediction",
             "emitted_at": datetime.now(timezone.utc), "payload": envelope}
    assert ReplayEvent.model_validate(event)
    if mutation in {"label", "future"}:
        event["payload"]["class" if mutation == "label" else "future_observations"] = 1
    elif mutation == "wrong_kind":
        event["event_type"] = "telemetry"
    elif mutation == "wrong_replay":
        event["replay_id"] = str(uuid4())
    else:
        event["sequence"] += 1
    with pytest.raises(ValidationError):
        ReplayEvent.model_validate(event)
