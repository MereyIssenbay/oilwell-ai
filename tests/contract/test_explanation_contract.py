"""Additive explanation schemas and provider allowlist; no network or inference."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from backend.app.main import create_app
from llm.schemas import EvidencePacket, Explanation
from llm.service import CopilotService
from tests.qa.test_copilot_integrity import service_packet

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name, model", [("explanation", Explanation), ("copilot_evidence", EvidencePacket)])
def test_exported_copilot_json_schema_matches_pydantic(name, model):
    schema = json.loads((ROOT / f"docs/contracts/{name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    schema.pop("$schema", None)
    assert schema == model.model_json_schema()


def test_actual_fallback_conforms_to_explanation_and_nested_evidence_contract():
    response = CopilotService().explain(service_packet()).model_dump(mode="json")
    schema = json.loads((ROOT / "docs/contracts/explanation.schema.json").read_text())
    Draft202012Validator(schema).validate(response)
    assert response["schema_version"] == "copilot-explanation-1.0.0"
    assert response["historical_replay"] is True and response["diagnostic_only"] is True
    assert response["accepted_for_monitoring"] is False
    assert response["evidence"]["packet_version"] == "copilot-evidence-1.0.0"


def test_provider_packet_declares_only_approved_fields_and_strict_known_sensors():
    schema = EvidencePacket.model_json_schema()
    assert schema["additionalProperties"] is False
    allowed = {"packet_version", "model_version", "event_type", "confidence", "abnormal_score", "threshold",
               "calibration", "alert_status", "episode_state", "source_origin", "source_time_basis",
               "window_start", "window_end", "sample_count", "expected_sample_count", "sensors",
               "integrity", "abstention_reason"}
    assert set(schema["properties"]) == allowed
    assert schema["properties"]["sensors"]["maxItems"] == 27
    assert schema["$defs"]["SensorEvidence"]["additionalProperties"] is False


def test_openapi_explanation_endpoint_accepts_only_question_and_opt_in_provider():
    spec = create_app().openapi()
    for path in ("/predictions/{id}/explanation", "/replays/{id}/predictions/{sequence}/explanation"):
        route = spec["paths"][path]["post"]
        ref = route["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        request = spec["components"]["schemas"][ref]
        assert request["additionalProperties"] is False
        assert set(request["properties"]) == {"question", "use_provider"}
        assert request["properties"]["question"]["maxLength"] == 500
        assert request["properties"]["use_provider"]["default"] is False
        assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/Explanation")
        for status in ("404", "409", "422", "429", "503"):
            assert route["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    assert "/copilot/sources/{source_id}" in spec["paths"]


def test_existing_prediction_schema_versions_remain_distinct_and_unpromoted():
    canonical = json.loads((ROOT / "docs/contracts/prediction.schema.json").read_text())
    diagnostic = json.loads((ROOT / "docs/contracts/diagnostic_prediction.schema.json").read_text())
    assert canonical["properties"]["schema_version"]["const"] == "1.0.0"
    assert diagnostic["properties"]["schema_version"]["const"] == "diagnostic-1.0.0"
    assert "undesirable_event" not in canonical["properties"]["event_type"]["enum"]
    assert set(diagnostic["properties"]["event_type"]["enum"]) == {"normal", "undesirable_event", "unknown"}
