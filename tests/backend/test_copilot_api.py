"""Copilot HTTP boundary and saved-prediction lookup, using explicit fixtures."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from backend.app.main import create_app
from backend.app.registry import Registry, RegisteredSource
from backend.app.repository import MemoryRepository
from backend.app.schemas import DiagnosticPrediction
from backend.app.settings import Settings
from ml.data_pipeline.models import SENSOR_COLUMNS
from tests.backend.test_api import FixtureRuntime, SOURCE, WELL, prediction


def saved_fixture():
    """Exact synthetic sensor history and persisted output; never a model result."""
    frame = pd.DataFrame({name: np.arange(80, dtype=float) for name in SENSOR_COLUMNS},
                         index=pd.date_range("2020-01-01", periods=80, freq="s"))
    frame.loc[frame.index[59], SENSOR_COLUMNS[0]] = np.nan
    source = SimpleNamespace(well_id=WELL, sha256="b" * 64, instance_id=SOURCE,
                             dataset_version="2.0.0", dataset_revision="a" * 40)
    registry = Registry(Settings().root)
    registry.ready = True
    registry.sensor_names = tuple(SENSOR_COLUMNS)
    registry.units = {name: "%" for name in SENSOR_COLUMNS}
    registry.records = {SOURCE: RegisteredSource(source, frame)}
    registry.startup = lambda: None
    p = prediction(uuid4(), datetime.now(timezone.utc)).model_dump(mode="json")
    window = frame.iloc[:60]
    p["sensor_evidence"] = [{"evidence_id": f"original-{i}", "sensor_name": name,
        "value": float(window[name].mean()), "unit": "%", "window_start": p["window"]["start"],
        "window_end": p["window"]["end"], "missing_fraction": float(1 - window[name].count() / 60)}
        for i, name in enumerate(SENSOR_COLUMNS)]
    rows = [{"timestamp": stamp.isoformat(), "sensors": {
        name: None if pd.isna(value) else float(value) for name, value in row.items()}}
        for stamp, row in window.iterrows()]
    p["provenance"]["request_window_sha256"] = hashlib.sha256(json.dumps(
        rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    value = DiagnosticPrediction.model_validate(p)
    repo = MemoryRepository()
    repo.get_or_create("saved-fixture", "fixture-hash", lambda: value)
    runtime = FixtureRuntime()
    runtime.predict = lambda *args, **kwargs: pytest.fail("Explanation must never execute inference")
    return registry, runtime, repo, value


@pytest.fixture
def fixture_api(tmp_path):
    from llm.service import CopilotService
    registry, runtime, repo, value = saved_fixture()
    service = CopilotService.from_environment(tmp_path)
    app = create_app(Settings(), registry=registry, runtime=runtime, repository=repo,
                     copilot_service=service, replay_worker_enabled=False)
    with TestClient(app) as client:
        yield client, registry, repo, value


def test_saved_prediction_explained_without_inference_or_mutation(fixture_api):
    client, registry, repo, value = fixture_api
    before = json.dumps(repo.predictions, sort_keys=True)
    response = client.post(f"/predictions/{value.prediction_id}/explanation", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "fallback" and result["provider"] == "none"
    assert result["evidence"]["sensors"][0]["latest"] is None
    assert result["evidence"]["sensors"][0]["trend_per_second"] == pytest.approx(1.0)
    assert result["evidence"]["episode_state"] == "unknown"
    assert result["accepted_for_monitoring"] is False
    assert json.dumps(repo.predictions, sort_keys=True) == before
    for forbidden in ("fixture-source", "fixture-well", "original-", "request_window_sha256"):
        assert forbidden not in response.text
    for source in result["citations"]:
        fetched = client.get(f"/copilot/sources/{source['source_id']}")
        assert fetched.status_code == 200 and fetched.json() == source


@pytest.mark.parametrize("body", [{"question": "x" * 501}, {"use_provider": "true"},
                                  {"question": 4}, {"class": 2}, {"evidence": {}},
                                  {"model_version": "override"}])
def test_client_cannot_inject_evidence_or_unbounded_input(fixture_api, body):
    client, _, _, value = fixture_api
    response = client.post(f"/predictions/{value.prediction_id}/explanation", json=body)
    assert response.status_code == 422
    assert set(response.json()["error"]) == {"code", "message", "details", "request_id"}


def test_missing_prediction_and_source_return_structured_404(fixture_api):
    client, *_ = fixture_api
    for path in (f"/predictions/{uuid4()}/explanation", "/copilot/sources/no-such-source"):
        result = client.post(path, json={}) if "explanation" in path else client.get(path)
        assert result.status_code == 404
        assert "traceback" not in result.text.lower()


def test_changed_history_is_withheld_before_provider(fixture_api):
    client, registry, _, value = fixture_api
    registry.record(SOURCE).frame.iloc[10, 0] += 1000
    result = client.post(f"/predictions/{value.prediction_id}/explanation", json={"use_provider": True})
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "EVIDENCE_CONFLICT"


def test_future_rows_do_not_change_explanation_evidence(fixture_api):
    client, registry, _, value = fixture_api
    path = f"/predictions/{value.prediction_id}/explanation"
    before = client.post(path, json={}).json()
    registry.record(SOURCE).frame.iloc[60:, :] = 1e20
    after = client.post(path, json={}).json()
    assert before["evidence_hash"] == after["evidence_hash"]
    assert before["observations"] == after["observations"]
