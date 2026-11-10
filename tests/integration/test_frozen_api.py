"""Integration against the immutable selected model and an explicit test PostgreSQL."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def service():
    dsn = os.environ.get("OILWELL_INTEGRATION_DATABASE_URL")
    if not dsn:
        pytest.skip("Explicit isolated PostgreSQL integration DSN required")
    settings = Settings(root=ROOT, database_url=dsn)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        yield app, client, settings


def test_startup_docs_and_registry_do_not_expose_test_or_labels(service):
    app, client, _ = service
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {"/health", "/wells", "/wells/{id}/telemetry", "/predict", "/alerts", "/models/info"}
    info = client.get("/models/info").json()
    assert info["model_version"] == "oilwell-binary-phase5-c4e1835a82620306778a"
    assert info["threshold"] == 1.1881945293311268e-14
    assert info["accepted_for_monitoring"] is False and info["calibration"] == "none"
    state = app.state.runtime.predictor.pipeline.state
    allowed = {a.source.instance_id for a in state.split_manifest.assignments if a.partition in {"train", "validation"}}
    assert set(app.state.registry.records) == allowed and len(allowed) == 10
    wells = client.get("/wells").json()["items"]
    assert len(wells) == 10
    assert {s["source_instance_id"] for w in wells for s in w["source_instances"]} == allowed
    denied = next(a.source.instance_id for a in state.split_manifest.assignments if a.partition == "test")
    response = client.post("/predict", json={"source_instance_id": denied, "endpoint_position": 59},
                           headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 404
    source = next(iter(allowed))
    well = app.state.registry.record(source).source.well_id
    page = client.get(f"/wells/{well}/telemetry", params={"source_instance_id": source, "limit": 60}).json()
    assert len(page["items"]) == 60 and page["next_offset"] == 60
    assert set(page["items"][0]["sensors"]) == set(info["sensor_names"])
    assert "class" not in json.dumps(page) and '"state"' not in json.dumps(page)


def test_real_api_scores_match_saved_validation_and_persist_atomically(service):
    app, client, settings = service
    selection = json.loads((ROOT / "reports/experiments/selection.json").read_text())
    path = ROOT / selection["validation_predictions_path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == selection["validation_predictions_sha256"]
    saved = pd.read_parquet(path, filters=[("model", "==", selection["candidate_id"])])
    checked = []
    for sid, rows in saved.groupby("instance_id"):
        expected = rows.sort_values("timestamp").iloc[0]
        key = f"real-frozen-{uuid4()}"
        payload = {"source_instance_id": sid, "endpoint_position": int(expected.endpoint_position)}
        response = client.post("/predict", json=payload, headers={"Idempotency-Key": key})
        assert response.status_code == 200, response.text
        value = response.json()
        assert np.isclose(value["abnormal_score"], expected.score, atol=1e-14, rtol=0)
        assert (value["event_type"] == "undesirable_event") == bool(expected.predicted)
        assert len(value["sensor_evidence"]) == 27
        assert value["execution"]["mode"] == "historical_inference"
        assert value["provenance"]["source_sha256"] == app.state.registry.record(sid).source.sha256
        with psycopg.connect(settings.database_url) as connection:
            prediction_count = connection.execute("SELECT count(*) FROM oilwell_predictions WHERE prediction_id=%s", (value["prediction_id"],)).fetchone()[0]
            alert_count = connection.execute("SELECT count(*) FROM oilwell_alerts WHERE prediction_id=%s", (value["prediction_id"],)).fetchone()[0]
        assert prediction_count == 1 and alert_count == int(value["alert_status"] == "alert")
        again = client.post("/predict", json=payload, headers={"Idempotency-Key": key})
        assert again.json() == value and again.headers["Idempotency-Replayed"] == "true"
        checked.append(sid)
    assert len(checked) == 3


def test_registered_samples_are_validated_and_never_forge_provenance(service):
    app, client, _ = service
    source = next(iter(app.state.registry.records))
    record = app.state.registry.record(source)
    page = client.get(f"/wells/{record.source.well_id}/telemetry",
                      params={"source_instance_id": source, "limit": 60}).json()
    payload = {"source_instance_id": source, "endpoint_position": 59, "samples": page["items"]}
    valid = client.post("/predict", json=payload, headers={"Idempotency-Key": str(uuid4())})
    assert valid.status_code == 200
    wrong = deepcopy(payload)
    sensor = next(k for k, v in wrong["samples"][0]["sensors"].items() if v is not None)
    wrong["samples"][0]["sensors"][sensor] += 1
    changed = client.post("/predict", json=wrong, headers={"Idempotency-Key": str(uuid4())})
    assert changed.status_code == 422 and changed.json()["error"]["code"] == "SOURCE_WINDOW_MISMATCH"
    for value in [True, "1.0", "SECRET_SENSOR_VALUE"]:
        wrong = deepcopy(payload); wrong["samples"][0]["sensors"][sensor] = value
        response = client.post("/predict", json=wrong, headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 422 and "SECRET_SENSOR_VALUE" not in response.text
    wrong = deepcopy(payload); wrong["samples"][0]["sensors"]["class"] = 8
    assert client.post("/predict", json=wrong, headers={"Idempotency-Key": str(uuid4())}).status_code == 422


def test_insufficient_history_is_persisted_without_alert_and_survives_restart(service):
    app, client, settings = service
    source = next(iter(app.state.registry.records))
    key = f"short-prefix-{uuid4()}"
    payload = {"source_instance_id": source, "endpoint_position": 0}
    response = client.post("/predict", json=payload, headers={"Idempotency-Key": key})
    assert response.status_code == 200
    value = response.json()
    assert value["event_type"] == "unknown" and value["abnormal_score"] is None
    assert value["abstention_reason"] == "insufficient_history"
    with TestClient(create_app(settings), raise_server_exceptions=False) as restarted:
        again = restarted.post("/predict", json=payload, headers={"Idempotency-Key": key})
        assert again.json() == value and again.headers["Idempotency-Replayed"] == "true"
    with psycopg.connect(settings.database_url) as connection:
        assert connection.execute("SELECT count(*) FROM oilwell_alerts WHERE prediction_id=%s", (value["prediction_id"],)).fetchone()[0] == 0
