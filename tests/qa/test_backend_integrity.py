"""Independent Phase 6 API, provenance and real PostgreSQL integrity checks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from backend.app.errors import ServiceError
from backend.app.main import create_app
from backend.app.repository import MemoryRepository, PostgresRepository
from backend.app.schemas import DiagnosticPrediction, PredictRequest
from backend.app.settings import Settings
from ml.data_pipeline.models import SENSOR_COLUMNS


ROOT = Path(__file__).resolve().parents[2]
SECRET = "qa-secret-password-never-log"


def prediction(prediction_id=None, generated_at=None, *, positive=True):
    """Independent synthetic response fixture; no actual data/model results."""
    source_time = "2026-01-01T00:00:59"
    start, end = "2026-01-01T00:00:00Z", source_time + "Z"
    score = 0.8 if positive else 0.2
    return DiagnosticPrediction.model_validate({
        "prediction_id": prediction_id or uuid4(), "timestamp": end, "well_id": "qa-well",
        "event_type": "undesirable_event" if positive else "normal",
        "confidence": score if positive else 1 - score, "confidence_kind": "raw_probability",
        "abnormal_score": score, "threshold": 0.5, "model_version": "qa-synthetic-model",
        "feature_spec_version": "qa-features", "policy_version": "qa-policy",
        "sensor_evidence": [{"evidence_id": "qa-mean", "sensor_name": SENSOR_COLUMNS[0],
                             "value": 1.0, "unit": "qa-unit", "window_start": start,
                             "window_end": end, "missing_fraction": 0.0}],
        "alert_status": "alert" if positive else "normal", "abstention_reason": None,
        "window": {"start": start, "end": end, "sample_count": 60},
        "quality": {"status": "valid", "missing_fraction": 0.0, "warnings": []},
        "provenance": {"dataset_version": "2.0.0", "dataset_revision": "0" * 40,
                       "source_instance_id": "qa-source", "source_sha256": "0" * 64,
                       "source_timestamp": source_time, "preprocessor_fingerprint": "0" * 64,
                       "model_artifact_sha256": "0" * 64, "request_window_sha256": "0" * 64},
        "execution": {"generated_at": generated_at or datetime(2026, 2, 1, tzinfo=timezone.utc)},
    })


class FixtureRegistry:
    def __init__(self):
        self.starts = 0

    def startup(self):
        self.starts += 1

    def list_wells(self):
        return [{"well_id": name, "source_instances": [{"source_instance_id": "qa-source",
                "source_start": "2026-01-01T00:00:00", "source_end": "2026-01-01T00:01:59",
                "row_count": 120}]} for name in ("qa-a", "qa-b")]

    def telemetry(self, well_id, source_id, offset, limit, sensors):
        if source_id != "qa-source":
            raise ServiceError("SOURCE_NOT_FOUND", "Registered source not found", 404)
        return {"well_id": well_id, "source_instance_id": source_id,
                "items": [{"timestamp": "2026-01-01T00:00:00", "sensors": {SENSOR_COLUMNS[0]: None}}],
                "next_offset": None}


class FixtureRuntime:
    def __init__(self):
        self.starts = 0
        self.calls = []

    def startup(self):
        self.starts += 1

    def predict(self, request, prediction_id, generated_at):
        self.calls.append(request)
        return prediction(prediction_id, generated_at)

    def info(self):
        return {"model_version": "qa-synthetic-model", "task": "binary_normal_vs_documented_undesirable",
                "supported_labels": ["normal", "undesirable_event"], "calibration": "none",
                "status": "diagnostic_only_rejected_for_monitoring", "threshold": 0.5,
                "comparison": "ge", "sensor_names": list(SENSOR_COLUMNS), "window_rows": 60,
                "stride_rows": 10, "preprocessor_fingerprint": "0" * 64,
                "model_artifact_sha256": "0" * 64, "limitations": ["synthetic QA fixture"]}


@pytest.fixture
def service():
    runtime, registry, repository = FixtureRuntime(), FixtureRegistry(), MemoryRepository()
    app = create_app(Settings(max_request_bytes=4096, max_concurrent_predictions=1),
                     runtime=runtime, registry=registry, repository=repository)
    with TestClient(app) as client:
        yield client, runtime, registry, repository


def post(client, key="qa-key", **body):
    return client.post("/predict", json={"source_instance_id": "qa-source", "endpoint_position": 59, **body},
                       headers={"Idempotency-Key": key})


def assert_error(response, status, code=None):
    assert response.status_code == status, response.text
    data = response.json()
    assert set(data) == {"error"}
    assert set(data["error"]) == {"code", "message", "details", "request_id"}
    UUID(data["error"]["request_id"])
    assert response.headers["X-Request-ID"] == data["error"]["request_id"]
    assert SECRET not in response.text
    assert "Traceback" not in response.text and "C:\\private" not in response.text
    if code:
        assert data["error"]["code"] == code


def test_startup_docs_openapi_and_diagnostic_identity(service):
    client, runtime, registry, _ = service
    assert runtime.starts == registry.starts == 1
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/health", "/wells", "/wells/{id}/telemetry", "/predict", "/alerts", "/models/info"}
    assert schema["info"]["version"] == "diagnostic-1.0.0"
    assert schema["paths"]["/predict"]["post"]["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    info = client.get("/models/info").json()
    assert info["accepted_for_monitoring"] is False and info["diagnostic_only"] is True
    assert info["calibration"] == "none"


def test_idempotency_persists_exact_original_response_and_one_alert(service):
    client, runtime, _, repository = service
    first = post(client)
    assert first.status_code == 200
    second = post(client)
    assert second.status_code == 200 and second.json() == first.json()
    assert first.headers["Idempotency-Replayed"] == "false"
    assert second.headers["Idempotency-Replayed"] == "true"
    assert len(runtime.calls) == len(repository.predictions) == len(repository.alerts) == 1
    alert = client.get("/alerts").json()["items"][0]
    assert alert["prediction_id"] == first.json()["prediction_id"]
    assert alert["status"] == "diagnostic_detection"
    assert alert["mode"] == "historical_inference"
    assert_error(post(client, endpoint_position=69), 409, "IDEMPOTENCY_CONFLICT")
    assert len(runtime.calls) == 1


@pytest.mark.parametrize("method,path,kwargs", [
    ("post", "/predict", {"json": {"source_instance_id": "qa-source", "endpoint_position": 59}}),
    ("post", "/predict", {"json": {"source_instance_id": "qa-source", "endpoint_position": True}, "headers": {"Idempotency-Key": "q"}}),
    ("post", "/predict", {"json": {"source_instance_id": "qa-source", "endpoint_position": 59, "class": 8}, "headers": {"Idempotency-Key": "q"}}),
    ("post", "/predict", {"content": '{"bad":', "headers": {"Content-Type": "application/json", "Idempotency-Key": "q"}}),
    ("post", "/predict", {"json": {"source_instance_id": "qa-source", "endpoint_position": 59}, "headers": {"Idempotency-Key": "bad key"}}),
    ("get", "/wells?limit=101", {}),
    ("get", "/alerts?limit=1001", {}),
    ("get", "/wells/qa-well/telemetry?source_instance_id=qa-source&limit=1001", {}),
    ("get", "/wells/qa-well/telemetry?source_instance_id=qa-source&offset=-1", {}),
])
def test_invalid_requests_have_structured_errors_and_do_not_infer(service, method, path, kwargs):
    client, runtime, _, repository = service
    assert_error(getattr(client, method)(path, **kwargs), 422)
    assert not runtime.calls and not repository.predictions


def test_body_limit_uses_actual_bytes_not_only_claimed_content_length(service):
    client, runtime, _, _ = service
    response = client.post("/predict", content=b"x" * 4097,
                           headers={"Content-Length": "1", "Idempotency-Key": "q"})
    assert_error(response, 413, "PAYLOAD_TOO_LARGE")
    assert_error(client.post("/predict", content=b"{}", headers={"Content-Length": "-1"}), 400)
    assert not runtime.calls


def test_request_ids_are_server_generated_and_errors_do_not_echo_input_values(service):
    client, _, _, _ = service
    response = client.post("/predict", json={"source_instance_id": "q", "endpoint_position": SECRET},
                           headers={"Idempotency-Key": "q", "X-Request-ID": SECRET})
    assert_error(response, 422)
    assert response.headers["X-Request-ID"] != SECRET


@pytest.mark.parametrize("failure", ["inference", "response_validation", "telemetry"])
def test_unexpected_errors_and_logs_exclude_internal_details(service, monkeypatch, caplog, failure):
    client, runtime, registry, repository = service
    caplog.set_level(logging.INFO, logger="oilwell.api")
    def fail(*args, **kwargs):
        raise RuntimeError(f"{SECRET} at C:\\private\\model.joblib")
    if failure == "inference":
        monkeypatch.setattr(runtime, "predict", fail)
        response = post(client)
    elif failure == "response_validation":
        monkeypatch.setattr(runtime, "info", lambda: {"secret": SECRET})
        response = client.get("/models/info")
    else:
        monkeypatch.setattr(registry, "telemetry", fail)
        response = client.get("/wells/qa-well/telemetry?source_instance_id=qa-source")
    assert_error(response, 500, "INTERNAL_ERROR")
    assert SECRET not in caplog.text and "Traceback" not in caplog.text
    assert not repository.predictions


def test_prediction_alert_logs_contain_ids_and_status_but_not_request_payload(service, caplog):
    client, _, _, _ = service
    caplog.set_level(logging.INFO, logger="oilwell.api")
    response = post(client, key=SECRET)
    assert response.status_code == 200
    records = [json.loads(record.message) for record in caplog.records if record.name == "oilwell.api"]
    assert {r["event"] for r in records} >= {"prediction_persisted", "diagnostic_alert_persisted"}
    assert SECRET not in caplog.text and "sensors" not in caplog.text
    assert all("prediction_id" in r and "model_version" in r for r in records)


@pytest.mark.parametrize("unavailable", ["model", "registry", "database"])
def test_degraded_startup_keeps_docs_and_fails_prediction_without_storage_fallback(unavailable):
    runtime, registry, repository = FixtureRuntime(), FixtureRegistry(), MemoryRepository()
    target = {"model": runtime, "registry": registry, "database": repository}[unavailable]
    def fail():
        raise RuntimeError(SECRET)
    setattr(target, "initialize" if unavailable == "database" else "startup", fail)
    with TestClient(create_app(Settings(), runtime=runtime, registry=registry, repository=repository)) as client:
        response = client.get("/health")
        assert response.status_code == 503 and response.json()[unavailable] == "unavailable"
        assert client.get("/docs").status_code == 200
        assert_error(post(client), 503)
        assert not repository.predictions and not runtime.calls


def test_concurrent_prediction_limit_is_bounded_and_slot_recovers(service, monkeypatch):
    client, runtime, _, _ = service
    entered, release = Event(), Event()
    original = runtime.predict
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(runtime, "predict", blocked)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(post, client, "first")
        try:
            assert entered.wait(3)
            assert_error(post(client, key="second"), 429, "INFERENCE_BUSY")
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 200
    assert post(client, key="third").status_code == 200


def test_cursor_pages_are_complete_and_bound_to_resource_and_filter(service):
    client, _, _, _ = service
    first = client.get("/wells?limit=1").json()
    second = client.get("/wells", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert [first["items"][0]["well_id"], second["items"][0]["well_id"]] == ["qa-a", "qa-b"]
    assert second["next_cursor"] is None
    assert_error(client.get("/alerts", params={"cursor": first["next_cursor"]}), 400, "INVALID_CURSOR")
    for key in ("a", "b", "c"):
        assert post(client, key=key).status_code == 200
    alerts = client.get("/alerts", params={"limit": 1, "well_id": "qa-well"}).json()
    assert_error(client.get("/alerts", params={"cursor": alerts["next_cursor"], "well_id": "another"}), 400)
    assert_error(client.get("/wells", params={"cursor": "!invalid!"}), 400)


@pytest.fixture(scope="module")
def frozen_registry_runtime():
    if os.environ.get("OILWELL_RUN_FROZEN_QA") != "1":
        pytest.skip("Explicit frozen-artifact integration flag is required")
    from backend.app.registry import Registry
    from backend.app.inference import Runtime
    registry = Registry(ROOT)
    registry.startup()
    runtime = Runtime(registry, ROOT)
    runtime.startup()
    return registry, runtime


def test_frozen_registry_excludes_test_and_labels_and_returns_defensive_windows(frozen_registry_runtime):
    registry, runtime = frozen_registry_runtime
    assignments = runtime.predictor.pipeline.state.split_manifest.assignments
    approved = {a.source.instance_id for a in assignments if a.partition in {"train", "validation"}}
    excluded = {a.source.instance_id for a in assignments if a.partition == "test"}
    assert set(registry.records) == approved and len(approved) == 10
    for source_id in excluded:
        with pytest.raises(ServiceError) as error:
            registry.record(source_id)
        assert error.value.status_code == 404
    for value in registry.records.values():
        assert tuple(value.frame.columns) == tuple(SENSOR_COLUMNS)
        assert "class" not in value.frame and "state" not in value.frame
    sid = sorted(approved)[0]
    _, window = registry.window(sid, 59)
    before = registry.records[sid].frame.iloc[0, 0]
    window.iloc[0, 0] = 987654321
    after = registry.records[sid].frame.iloc[0, 0]
    assert before == after or (pd.isna(before) and pd.isna(after))


def test_actual_api_registry_is_sensor_only_and_rejects_every_test_source(frozen_registry_runtime):
    registry, runtime = frozen_registry_runtime
    repository = MemoryRepository()  # Deliberate fixture injection, not PostgreSQL evidence.
    with TestClient(create_app(Settings(), runtime=runtime, registry=registry, repository=repository)) as client:
        page = client.get("/wells").json()
        assert len(page["items"]) == 10 and page["next_cursor"] is None
        exposed = {s["source_instance_id"] for w in page["items"] for s in w["source_instances"]}
        assignments = runtime.predictor.pipeline.state.split_manifest.assignments
        excluded = [a.source for a in assignments if a.partition == "test"]
        assert len(excluded) == 4 and not exposed.intersection(s.instance_id for s in excluded)
        for source in excluded:
            assert_error(post(client, key=uuid4().hex, source_instance_id=source.instance_id), 404, "SOURCE_NOT_FOUND")
            assert_error(client.get(f"/wells/{source.well_id}/telemetry",
                                    params={"source_instance_id": source.instance_id}), 404, "SOURCE_NOT_FOUND")
        approved = registry.records[sorted(exposed)[0]].source
        response = client.get(f"/wells/{approved.well_id}/telemetry",
                              params={"source_instance_id": approved.instance_id, "limit": 2})
        assert response.status_code == 200
        samples = response.json()["items"]
        assert len(samples) == 2 and all(set(s["sensors"]) == set(SENSOR_COLUMNS) for s in samples)
        assert "source_path" not in response.text and '"class"' not in response.text and '"state"' not in response.text
        assert_error(client.get(f"/wells/{approved.well_id}/telemetry",
                               params={"source_instance_id": approved.instance_id, "sensors": "state"}), 422)
        assert not repository.predictions and not repository.alerts


@pytest.mark.parametrize("mutation", ["value", "missing", "time", "well", "version"])
def test_real_source_provenance_rejects_forged_samples_and_scope(frozen_registry_runtime, mutation):
    registry, runtime = frozen_registry_runtime
    sid = sorted(registry.records)[0]
    source, window = registry.window(sid, 59)
    samples = [{"timestamp": t.isoformat(), "sensors": {name: None if pd.isna(v) else float(v)
                for name, v in row.items()}} for t, row in window.iterrows()]
    body = {"source_instance_id": sid, "endpoint_position": 59, "samples": samples}
    if mutation == "value":
        name = next(c for c in SENSOR_COLUMNS if samples[0]["sensors"][c] is not None)
        samples[0]["sensors"][name] += 1
    elif mutation == "missing":
        name = next(c for c in SENSOR_COLUMNS if samples[0]["sensors"][c] is None)
        samples[0]["sensors"][name] = 0.0
    elif mutation == "time":
        samples[0]["timestamp"] = (window.index[0] + pd.Timedelta(seconds=1)).isoformat()
    elif mutation == "well":
        with pytest.raises(ServiceError) as error:
            registry.telemetry("not-the-registered-well", sid, 0, 1)
        assert error.value.status_code == 404
        return
    else:
        body["model_version"] = "unregistered"
    with pytest.raises(ServiceError) as error:
        runtime.predict(PredictRequest.model_validate(body), uuid4(), datetime.now(timezone.utc))
    assert error.value.status_code == 422


def test_real_inference_preserves_version_provenance_short_history_and_frozen_files(frozen_registry_runtime):
    registry, runtime = frozen_registry_runtime
    paths = [ROOT / "reports/experiments/selection.json", ROOT / "reports/experiments/test_access.json",
             ROOT / "ml/predict.py"]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    sid = sorted(registry.records)[0]
    short = runtime.predict(PredictRequest(source_instance_id=sid, endpoint_position=10), uuid4(), datetime.now(timezone.utc))
    assert short.event_type == "unknown" and short.abstention_reason == "insufficient_history"
    assert short.abnormal_score is None and short.window.sample_count == 11
    full = runtime.predict(PredictRequest(source_instance_id=sid, endpoint_position=59), uuid4(), datetime.now(timezone.utc))
    assert full.model_version == "oilwell-binary-phase5-c4e1835a82620306778a"
    assert full.threshold == 1.1881945293311268e-14
    assert full.provenance.source_sha256 == registry.records[sid].source.sha256
    assert full.provenance.source_timestamp == registry.records[sid].frame.index[59].isoformat()
    assert len(full.sensor_evidence) == 27 and full.accepted_for_monitoring is False
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in hashes.items())


def test_missing_evidence_abstains_without_estimator_and_without_label_inputs(frozen_registry_runtime, monkeypatch):
    registry, runtime = frozen_registry_runtime
    source, original = registry.window(sorted(registry.records)[0], 59)
    # Explicit synthetic fixture at the trusted registry boundary, never saved as real telemetry.
    empty = pd.DataFrame(float("nan"), index=original.index, columns=original.columns)
    monkeypatch.setattr(registry, "window", lambda *_: (source, empty))
    monkeypatch.setattr(runtime.predictor.estimator, "predict_proba", lambda *_: pytest.fail("No retained evidence must abstain before scoring"))
    result = runtime.predict(PredictRequest(source_instance_id=source.instance_id, endpoint_position=59),
                             uuid4(), datetime.now(timezone.utc))
    assert result.abstention_reason == "missing_required_sensors"
    assert result.event_type == "unknown" and result.alert_status == "insufficient_data"
    assert result.confidence is None and result.abnormal_score is None
    assert result.quality.missing_fraction == 1 and all(e.value is None for e in result.sensor_evidence)


def test_real_request_never_calls_estimator_fit(frozen_registry_runtime, monkeypatch):
    registry, runtime = frozen_registry_runtime
    monkeypatch.setattr(runtime.predictor.estimator, "fit", lambda *_args, **_kwargs: pytest.fail("Inference must not fit"))
    result = runtime.predict(PredictRequest(source_instance_id=sorted(registry.records)[0], endpoint_position=59),
                             uuid4(), datetime.now(timezone.utc))
    assert result.model_version == runtime.info()["model_version"]


@pytest.fixture
def postgres():
    url = os.environ.get("OILWELL_QA_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated QA PostgreSQL database is required")
    import psycopg
    repo = PostgresRepository(Settings(database_url=url))
    repo.initialize()
    prefix = "qa-independent-" + uuid4().hex
    yield repo, prefix, url
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM oilwell_alerts WHERE prediction_id IN "
                           "(SELECT prediction_id FROM oilwell_predictions WHERE idempotency_key LIKE %s)", (prefix + "%",))
        connection.execute("DELETE FROM oilwell_predictions WHERE idempotency_key LIKE %s", (prefix + "%",))


def test_postgres_concurrent_idempotency_and_new_repository_reload(postgres):
    repo, prefix, url = postgres
    created = []
    def build():
        created.append(True)
        return prediction()
    with ThreadPoolExecutor(max_workers=4) as executor:
        values = list(executor.map(lambda _: repo.get_or_create(prefix, "a" * 64, build), range(4)))
    assert len(created) == 1 and sum(not replayed for _, replayed in values) == 1
    assert len({value.prediction_id for value, _ in values}) == 1
    restarted = PostgresRepository(Settings(database_url=url))
    loaded, replayed = restarted.get_or_create(prefix, "a" * 64, lambda: pytest.fail("Persisted retry must not infer"))
    assert replayed and loaded == values[0][0]
    with pytest.raises(ServiceError) as error:
        restarted.get_or_create(prefix, "b" * 64, lambda: pytest.fail("Conflicting retry must not infer"))
    assert error.value.status_code == 409
    with restarted._connect() as connection:
        assert connection.execute("SELECT count(*) FROM oilwell_alerts WHERE prediction_id=%s", (loaded.prediction_id,)).fetchone()[0] == 1


def test_postgres_failed_alert_insert_rolls_back_prediction_and_idempotency(postgres, monkeypatch):
    repo, prefix, _ = postgres
    import psycopg
    original = repo._connect
    class FailingConnection:
        def __init__(self):
            self.connection = original()
        def __enter__(self):
            self.connection.__enter__()
            return self
        def __exit__(self, *args):
            return self.connection.__exit__(*args)
        def execute(self, query, *args, **kwargs):
            if query.startswith("INSERT INTO oilwell_alerts"):
                raise psycopg.OperationalError(SECRET)
            return self.connection.execute(query, *args, **kwargs)
    monkeypatch.setattr(repo, "_connect", FailingConnection)
    with pytest.raises(ServiceError) as error:
        repo.get_or_create(prefix, "a" * 64, prediction)
    assert error.value.status_code == 503 and SECRET not in error.value.message
    monkeypatch.setattr(repo, "_connect", original)
    with repo._connect() as connection:
        assert connection.execute("SELECT count(*) FROM oilwell_predictions WHERE idempotency_key=%s", (prefix,)).fetchone()[0] == 0
    value, replayed = repo.get_or_create(prefix, "a" * 64, prediction)
    assert not replayed and value.alert_status == "alert"


def test_postgres_queries_treat_hostile_values_as_data_and_normal_predictions_have_no_alert(postgres):
    repo, prefix, _ = postgres
    key = prefix + "'; DROP TABLE oilwell_predictions;--"
    result, replayed = repo.get_or_create(key, "c" * 64, lambda: prediction(positive=False))
    assert not replayed and result.event_type == "normal"
    assert repo.list_alerts(None, 10, "'; DROP TABLE oilwell_alerts;--")["items"] == []
    with repo._connect() as connection:
        assert connection.execute("SELECT count(*) FROM oilwell_alerts WHERE prediction_id=%s", (result.prediction_id,)).fetchone()[0] == 0
    assert repo.health()
