"""Unit tests use explicitly injected fixtures, never replace runtime models."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.repository import MemoryRepository
from backend.app.schemas import DiagnosticPrediction
from backend.app.settings import Settings
from ml.data_pipeline.models import SENSOR_COLUMNS

SOURCE = "fixture-source"
WELL = "fixture-well"
START = datetime(2020, 1, 1, tzinfo=timezone.utc)


def prediction(prediction_id, generated_at, endpoint=59, score=.8):
    end = START + timedelta(seconds=endpoint)
    first = max(0, endpoint - 59)
    unknown = endpoint < 59
    return DiagnosticPrediction.model_validate({
        "prediction_id": prediction_id, "timestamp": end, "well_id": WELL,
        "event_type": "unknown" if unknown else ("undesirable_event" if score >= .5 else "normal"),
        "confidence": None if unknown else (score if score >= .5 else 1 - score), "confidence_kind": "unavailable" if unknown else "raw_probability",
        "abnormal_score": None if unknown else score, "threshold": .5, "model_version": "fixture-model",
        "feature_spec_version": "fixture-features", "policy_version": "fixture-policy",
        "sensor_evidence": [{"evidence_id": "fixture-mean", "sensor_name": SENSOR_COLUMNS[0], "value": 0.0,
                             "unit": "%", "window_start": START + timedelta(seconds=first), "window_end": end,
                             "missing_fraction": 0.0}],
        "alert_status": "insufficient_data" if unknown else ("alert" if score >= .5 else "normal"),
        "abstention_reason": "insufficient_history" if unknown else None,
        "window": {"start": START + timedelta(seconds=first), "end": end,
                   "sample_count": min(60, endpoint + 1)},
        "quality": {"status": "degraded" if unknown else "valid", "missing_fraction": 0.0, "warnings": []},
        "provenance": {"dataset_version": "2.0.0", "dataset_revision": "a" * 40,
                       "source_instance_id": SOURCE, "source_sha256": "b" * 64,
                       "source_timestamp": end.replace(tzinfo=None).isoformat(),
                       "preprocessor_fingerprint": "c" * 64, "model_artifact_sha256": "d" * 64,
                       "request_window_sha256": "e" * 64},
        "execution": {"generated_at": generated_at}})


class FixtureRegistry:
    def startup(self):
        pass

    def list_wells(self):
        return [{"well_id": WELL, "source_instances": [{"source_instance_id": SOURCE,
                 "source_start": "2020-01-01T00:00:00", "source_end": "2020-01-01T00:01:39", "row_count": 100}]}]

    def telemetry(self, well_id, source_instance_id, offset, limit, sensors):
        return {"well_id": well_id, "source_instance_id": source_instance_id,
                "items": [{"timestamp": "2020-01-01T00:00:00", "sensors": {SENSOR_COLUMNS[0]: None}}],
                "next_offset": None}


class FixtureRuntime:
    def __init__(self):
        self.starts = 0
        self.calls = 0

    def startup(self):
        self.starts += 1

    def info(self):
        return {"model_version": "fixture-model", "task": "binary_normal_vs_documented_undesirable",
                "supported_labels": ["normal", "undesirable_event"], "calibration": "none",
                "status": "diagnostic_only_rejected_for_monitoring", "threshold": .5, "comparison": "ge",
                "sensor_names": list(SENSOR_COLUMNS), "window_rows": 60, "stride_rows": 10,
                "preprocessor_fingerprint": "c" * 64, "model_artifact_sha256": "d" * 64,
                "limitations": ["Synthetic unit-test fixture"]}

    def predict(self, request, prediction_id, generated_at):
        self.calls += 1
        return prediction(prediction_id, generated_at, request.endpoint_position)


@pytest.fixture
def services():
    runtime, registry, repository = FixtureRuntime(), FixtureRegistry(), MemoryRepository()
    return runtime, registry, repository


@pytest.fixture
def client(services):
    runtime, registry, repository = services
    with TestClient(create_app(Settings(), runtime=runtime, registry=registry, repository=repository)) as value:
        yield value


def body(endpoint=59):
    return {"source_instance_id": SOURCE, "endpoint_position": endpoint}


def test_startup_docs_openapi_and_version(client, services):
    runtime, _, _ = services
    assert runtime.starts == 1
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) >= {"/health", "/wells", "/wells/{id}/telemetry", "/predict", "/alerts", "/models/info"}
    assert schema["info"]["version"] == "diagnostic-1.0.0"
    info = client.get("/models/info").json()
    assert info["model_version"] == "fixture-model" and not info["accepted_for_monitoring"]


def test_prediction_alert_persistence_and_idempotent_replay(client, services):
    first = client.post("/predict", json=body(), headers={"Idempotency-Key": "fixture-repeat"})
    second = client.post("/predict", json=body(), headers={"Idempotency-Key": "fixture-repeat"})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.headers["Idempotency-Replayed"] == "false" and second.headers["Idempotency-Replayed"] == "true"
    assert services[0].calls == 1
    alerts = client.get("/alerts").json()["items"]
    assert len(alerts) == 1 and alerts[0]["prediction_id"] == first.json()["prediction_id"]
    assert alerts[0]["status"] == "diagnostic_detection" and not alerts[0]["accepted_for_monitoring"]
    conflict = client.post("/predict", json=body(69), headers={"Idempotency-Key": "fixture-repeat"})
    assert conflict.status_code == 409 and services[0].calls == 1


def test_insufficient_history_is_persisted_abstention_without_alert(client, services):
    response = client.post("/predict", json=body(10), headers={"Idempotency-Key": "short-history"})
    assert response.status_code == 200
    assert response.json()["abstention_reason"] == "insufficient_history"
    assert response.json()["confidence"] is None
    assert len(services[2].predictions) == 1 and not services[2].alerts


def test_normal_prediction_does_not_create_diagnostic_alert(services):
    runtime, registry, repository = services
    runtime.predict = lambda request, prediction_id, generated_at: prediction(prediction_id, generated_at, score=.2)
    with TestClient(create_app(Settings(), runtime=runtime, registry=registry, repository=repository)) as client:
        result = client.post("/predict", json=body(), headers={"Idempotency-Key": "normal"})
    assert result.status_code == 200 and result.json()["event_type"] == "normal"
    assert len(repository.predictions) == 1 and not repository.alerts


def test_invalid_copied_model_is_revalidated_before_persistence(services):
    runtime, registry, repository = services
    runtime.predict = lambda request, prediction_id, generated_at: prediction(prediction_id, generated_at).model_copy(
        update={"alert_status": "normal"})
    with TestClient(create_app(Settings(), runtime=runtime, registry=registry, repository=repository)) as client:
        result = client.post("/predict", json=body(), headers={"Idempotency-Key": "forged-output"})
    assert result.status_code == 500 and not repository.predictions and not repository.alerts


@pytest.mark.parametrize("mutation", [
    {"endpoint_position": True}, {"endpoint_position": "59"}, {"endpoint_position": -1},
    {"endpoint_position": 60}, {"source_instance_id": 3}, {"class": 0}, {"state": 1}, {"samples": []},
])
def test_invalid_request_rejected_without_inference(client, services, mutation):
    response = client.post("/predict", json={**body(), **mutation}, headers={"Idempotency-Key": "invalid"})
    assert response.status_code == 422 and services[0].calls == 0
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("bad", [True, "0.2", float("inf"), float("nan")])
def test_sensor_values_reject_boolean_strings_and_nonfinite(client, services, bad):
    sensor_values = {name: 0.0 for name in SENSOR_COLUMNS}; sensor_values[SENSOR_COLUMNS[0]] = bad
    value = body(0); value["samples"] = [{"timestamp": "2020-01-01T00:00:00", "sensors": sensor_values}]
    response = client.post("/predict", content=json.dumps(value), headers={"Idempotency-Key": "bad-sensor", "Content-Type": "application/json"})
    assert response.status_code == 422 and services[0].calls == 0


def test_exact_sensor_allowlist_and_timezone(client):
    value = body(0)
    sensors = {name: None for name in SENSOR_COLUMNS}
    sensors.pop(SENSOR_COLUMNS[0]); sensors["class"] = 0
    value["samples"] = [{"timestamp": "2020-01-01T00:00:00Z", "sensors": sensors}]
    assert client.post("/predict", json=value, headers={"Idempotency-Key": "bad-schema"}).status_code == 422


def test_idempotency_required_and_bounded(client):
    assert client.post("/predict", json=body()).status_code == 422
    assert client.post("/predict", json=body(), headers={"Idempotency-Key": "a" * 129}).status_code == 422
    assert client.post("/predict", json=body(), headers={"Idempotency-Key": "not a valid key"}).status_code == 422


def test_query_limits_and_cursor_scope(client):
    assert client.get("/alerts?limit=1001").status_code == 422
    assert client.get("/wells?limit=0").status_code == 422
    assert client.get("/alerts?cursor=malformed").status_code == 400
    assert client.get(f"/wells/{WELL}/telemetry?source_instance_id={SOURCE}&offset=-1").status_code == 422
    assert client.get("/wells").json()["items"][0]["well_id"] == WELL


def test_error_sanitization_and_failed_transaction(services, caplog):
    runtime, registry, repository = services
    def fail(*args, **kwargs):
        raise RuntimeError("secretpassword C:/private/model.bin traceback")
    runtime.predict = fail
    with caplog.at_level(logging.INFO, logger="oilwell.api"):
        with TestClient(create_app(Settings(), runtime=runtime, registry=registry, repository=repository)) as client:
            response = client.post("/predict", json=body(), headers={"Idempotency-Key": "failure"})
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secretpassword" not in response.text + caplog.text
    assert "private/model" not in response.text + caplog.text
    assert not repository.predictions and not repository.alerts


def test_degraded_startup_keeps_docs_accessible_and_rejects_inference(services):
    runtime, registry, repository = services
    runtime.startup = lambda: (_ for _ in ()).throw(ValueError("sensitive startup failure"))
    with TestClient(create_app(Settings(), runtime=runtime, registry=registry, repository=repository)) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/health").status_code == 503
        assert client.get("/models/info").status_code == 503
        response = client.post("/predict", json=body(), headers={"Idempotency-Key": "missing-model"})
        assert response.status_code == 503 and "sensitive" not in response.text


def test_body_limit_checks_actual_received_bytes(services):
    runtime, registry, repository = services
    with TestClient(create_app(Settings(max_request_bytes=1024), runtime=runtime, registry=registry, repository=repository)) as client:
        response = client.post("/predict", content=b" " * 2048, headers={"Idempotency-Key": "large"})
        assert response.status_code == 413 and runtime.calls == 0
        response = client.post("/predict", content=b" " * 2048, headers={"Idempotency-Key": "large", "Content-Length": "10"})
        assert response.status_code == 413 and runtime.calls == 0


def test_prediction_slots_reject_busy_and_release_after_completion(services):
    runtime, registry, repository = services
    entered, release = threading.Event(), threading.Event()
    original = runtime.predict
    def waiting(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args, **kwargs)
    runtime.predict = waiting
    with TestClient(create_app(Settings(max_concurrent_predictions=1), runtime=runtime, registry=registry, repository=repository)) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.post, "/predict", json=body(), headers={"Idempotency-Key": "slow"})
            assert entered.wait(timeout=5)
            try:
                busy = client.post("/predict", json=body(), headers={"Idempotency-Key": "busy"})
                assert busy.status_code == 429
            finally:
                release.set()
            assert first.result(timeout=10).status_code == 200
        assert client.post("/predict", json=body(), headers={"Idempotency-Key": "after"}).status_code == 200


def test_structured_logs_exclude_raw_request_values(client, caplog):
    with caplog.at_level(logging.INFO, logger="oilwell.api"):
        assert client.post("/predict", json=body(), headers={"Idempotency-Key": "log-check"}).status_code == 200
    records = [json.loads(record.message) for record in caplog.records if record.name == "oilwell.api"]
    assert {r["event"] for r in records} >= {"prediction_persisted", "diagnostic_alert_persisted"}
    assert all("sensors" not in r and "idempotency_key" not in r for r in records)
