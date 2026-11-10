"""Independent structural and semantic checks for diagnostic API predictions.

All values in this module are synthetic fixtures, not dataset/model results.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest
from pydantic import ValidationError

from backend.app.schemas import DiagnosticPrediction, PredictRequest, SensorSample
from ml.data_pipeline.models import SENSOR_COLUMNS


ROOT = Path(__file__).resolve().parents[2]


def synthetic_prediction() -> dict:
    """Explicit synthetic usable positive response, with no real source claim."""
    return {
        "schema_version": "diagnostic-1.0.0",
        "prediction_id": "f1000000-0000-4000-8000-000000000001",
        "timestamp": "2026-01-01T00:00:59Z",
        "well_id": "qa-synthetic-well",
        "event_type": "undesirable_event",
        "confidence": 0.8,
        "confidence_kind": "raw_probability",
        "abnormal_score": 0.8,
        "threshold": 0.5,
        "model_version": "qa-synthetic-model",
        "feature_spec_version": "qa-synthetic-features",
        "policy_version": "qa-synthetic-policy",
        "diagnostic_only": True,
        "accepted_for_monitoring": False,
        "sensor_evidence": [{
            "evidence_id": "qa-evidence-1", "sensor_name": SENSOR_COLUMNS[0],
            "statistic": "mean", "value": 1.0, "unit": "qa-unit",
            "window_start": "2026-01-01T00:00:00Z",
            "window_end": "2026-01-01T00:00:59Z",
            "missing_fraction": 0.0, "method": "observed_summary",
        }],
        "alert_status": "alert", "abstention_reason": None,
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:00:59Z",
                   "sample_count": 60, "expected_sample_count": 60},
        "quality": {"status": "valid", "missing_fraction": 0.0, "warnings": []},
        "provenance": {
            "dataset_name": "3W", "dataset_version": "2.0.0",
            "dataset_revision": "0" * 40, "source_instance_id": "qa-synthetic-source",
            "source_sha256": "0" * 64, "source_kind": "real",
            "well_identity_kind": "anonymized_well",
            "source_timestamp": "2026-01-01T00:00:59",
            "time_basis": "source_naive_assumed_utc",
            "preprocessor_fingerprint": "0" * 64,
            "model_artifact_sha256": "0" * 64, "request_window_sha256": "0" * 64,
        },
        "execution": {"mode": "historical_inference", "generated_at": "2026-02-01T00:00:00Z"},
    }


def test_diagnostic_schema_is_additive_and_canonical_event_family_schema_remains_distinct():
    canonical = json.loads((ROOT / "docs/contracts/prediction.schema.json").read_text())
    diagnostic = json.loads((ROOT / "docs/contracts/diagnostic_prediction.schema.json").read_text())
    Draft202012Validator.check_schema(diagnostic)
    assert canonical["properties"]["schema_version"]["const"] == "1.0.0"
    assert diagnostic["properties"]["schema_version"]["const"] == "diagnostic-1.0.0"
    assert "undesirable_event" not in canonical["properties"]["event_type"]["enum"]
    assert set(diagnostic["properties"]["event_type"]["enum"]) == {"normal", "undesirable_event", "unknown"}
    required = {"timestamp", "well_id", "event_type", "confidence", "model_version",
                "sensor_evidence", "alert_status", "provenance", "execution"}
    assert required <= set(diagnostic["required"])
    wire = DiagnosticPrediction.model_validate(synthetic_prediction()).model_dump(mode="json")
    Draft202012Validator(diagnostic, format_checker=FormatChecker()).validate(wire)
    assert list(Draft202012Validator(canonical).iter_errors(wire))


def test_exported_schema_tracks_current_response_model():
    exported = json.loads((ROOT / "docs/contracts/diagnostic_prediction.schema.json").read_text())
    generated = DiagnosticPrediction.model_json_schema()
    # The orchestrator may supply JSON Schema identification/description metadata.
    for name in ("properties", "required", "additionalProperties", "$defs"):
        assert exported.get(name) == generated.get(name), name


def test_openapi_export_tracks_routes_and_typed_runtime_components():
    from backend.app.main import create_app
    exported = json.loads((ROOT / "docs/openapi.json").read_text())
    generated = create_app().openapi()  # Does not enter lifespan or load model/data.
    assert exported == generated
    prediction_schema = generated["components"]["schemas"]["DiagnosticPrediction"]
    assert prediction_schema["properties"]["schema_version"]["const"] == "diagnostic-1.0.0"
    assert generated["paths"]["/predict"]["post"]["requestBody"]["required"] is True
    assert any(p["name"] == "Idempotency-Key" and p["required"]
               for p in generated["paths"]["/predict"]["post"]["parameters"])


def test_normal_confidence_is_selected_binary_class_score_not_abnormal_score():
    payload = synthetic_prediction()
    payload.update(event_type="normal", alert_status="normal", abnormal_score=0.2, confidence=0.8)
    parsed = DiagnosticPrediction.model_validate(payload)
    assert parsed.confidence == 1 - parsed.abnormal_score
    payload["confidence"] = 0.2
    with pytest.raises(ValidationError):
        DiagnosticPrediction.model_validate(payload)


def test_threshold_tie_is_positive_and_abstention_is_not_normal():
    payload = synthetic_prediction()
    payload.update(abnormal_score=0.5, confidence=0.5)
    assert DiagnosticPrediction.model_validate(payload).event_type == "undesirable_event"
    payload.update(event_type="unknown", alert_status="insufficient_data", confidence=None,
                   abnormal_score=None, confidence_kind="unavailable", abstention_reason="missing_required_sensors")
    payload["sensor_evidence"] = []
    payload["quality"]["status"] = "invalid"
    assert DiagnosticPrediction.model_validate(payload).confidence is None
    payload["event_type"] = "normal"
    with pytest.raises(ValidationError):
        DiagnosticPrediction.model_validate(payload)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version="1.0.0"),
    lambda p: p.update(event_type="hydrate_in_production_line"),
    lambda p: p.update(diagnostic_only=False),
    lambda p: p.update(accepted_for_monitoring=True),
    lambda p: p.update(diagnostic_only=1),
    lambda p: p.update(accepted_for_monitoring=0),
    lambda p: p.update(abnormal_score="0.8"),
    lambda p: p.update(confidence=True),
    lambda p: p.update(confidence=float("nan")),
    lambda p: p.update(abnormal_score=float("inf")),
    lambda p: p.update(threshold=-0.1),
    lambda p: p.update(alert_status="normal"),
    lambda p: p.update(abstention_reason="insufficient_history"),
    lambda p: p.update(confidence_kind="unavailable"),
    lambda p: p.update(timestamp="2026-01-01T00:01:00Z"),
    lambda p: p["window"].update(start="2026-01-01T00:01:00Z"),
    lambda p: p["sensor_evidence"][0].update(window_end="2026-01-01T00:01:00Z"),
    lambda p: p["sensor_evidence"][0].update(sensor_name="class"),
    lambda p: p["sensor_evidence"][0].update(value=None),
    lambda p: p["sensor_evidence"].append(deepcopy(p["sensor_evidence"][0])),
    lambda p: p["quality"].update(status="invalid"),
    lambda p: p["execution"].update(mode="live"),
    lambda p: p["execution"].update(generated_at="2026-02-01T01:00:00+01:00"),
    lambda p: p["provenance"].update(source_kind="simulated"),
    lambda p: p["provenance"].update(time_basis="source_utc_verified"),
    lambda p: p.update(class_label=8),
    lambda p: p["window"].update(sample_count=59),
    lambda p: p["provenance"].update(source_timestamp="2026-01-01T00:00:58"),
])
def test_response_rejects_semantic_and_contract_corruption(mutation):
    payload = synthetic_prediction()
    mutation(payload)
    with pytest.raises(ValidationError):
        DiagnosticPrediction.model_validate(payload)


@pytest.mark.parametrize("bad_value", [True, False, "1.5", float("nan"), float("inf"), -float("inf"), {}, []])
def test_sensor_values_reject_coercion_and_nonfinite_input(bad_value):
    sensors = dict.fromkeys(SENSOR_COLUMNS, None)
    sensors[SENSOR_COLUMNS[0]] = bad_value
    with pytest.raises(ValidationError):
        SensorSample(timestamp="2026-01-01T00:00:00", sensors=sensors)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(endpoint_position=True),
    lambda p: p.update(endpoint_position="59"),
    lambda p: p.update(endpoint_position=59.0),
    lambda p: p.update(endpoint_position=-1),
    lambda p: p.update(endpoint_position=60),
    lambda p: p.update(class_label=8),
    lambda p: p.update(samples=[]),
    lambda p: p.update(model_version=""),
    lambda p: p.update(source_instance_id="x" * 129),
])
def test_predict_request_rejects_invalid_boundary(mutation):
    payload = {"source_instance_id": "qa-source", "endpoint_position": 59}
    mutation(payload)
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(payload)


def test_request_accepts_only_exact_upstream_sensors_and_complete_window():
    samples = [{"timestamp": f"2026-01-01T00:00:{i:02d}",
                "sensors": dict.fromkeys(SENSOR_COLUMNS, None)} for i in range(60)]
    value = PredictRequest(source_instance_id="qa-source", endpoint_position=59, samples=samples)
    assert len(value.samples) == 60
    for unexpected in ("class", "state", "well_id", "source_path"):
        broken = deepcopy(samples)
        broken[0]["sensors"].pop(SENSOR_COLUMNS[0])
        broken[0]["sensors"][unexpected] = 0
        with pytest.raises(ValidationError):
            PredictRequest(source_instance_id="qa-source", endpoint_position=59, samples=broken)
    with pytest.raises(ValidationError):
        PredictRequest(source_instance_id="qa-source", endpoint_position=59, samples=samples[:-1])
