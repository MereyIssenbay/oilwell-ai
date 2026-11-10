"""Dashboard adapters expose stored results and completed-only original labels."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pandas as pd
import pytest
from pydantic import ValidationError

from backend.app import dashboard
from backend.app.dashboard_schemas import RetrospectivePage, RetrospectivePrediction
from backend.app.errors import ServiceError
from backend.app.main import create_app
from backend.app.registry import Registry
from backend.app.replay_schemas import CreateReplay, ReplayCommand
from backend.app.replay_repository import PostgresReplayRepository
from backend.app.repository import MemoryRepository
from backend.app.settings import Settings
from tests.backend.test_replay import components, drain, start, SOURCE

ROOT = Path(__file__).resolve().parents[2]


def labels_for(registry, _source_id):
    frame = registry.record(SOURCE).frame
    labels = pd.DataFrame({"class": pd.array([None] * len(frame), dtype="Int16"),
                           "state": pd.array([None] * len(frame), dtype="Int16")}, index=frame.index)
    for position, value in [(69, 0), (79, 102), (89, 999), (99, 2)]:
        if position < len(frame):
            labels.iloc[position, 0] = value
            labels.iloc[position, 1] = 1
    return labels, {0: {"family": 0, "name": "NORMAL", "phase": "normal"},
                    2: {"family": 2, "name": "SPURIOUS_CLOSURE_OF_DHSV", "phase": "event"},
                    102: {"family": 2, "name": "SPURIOUS_CLOSURE_OF_DHSV", "phase": "transient"}}


@pytest.fixture
def fixture_service(monkeypatch):
    registry, runtime, store, service = components(rows=100)
    registry.startup = lambda: None
    registry.units = {sensor: "fixture-unit" for sensor in registry.sensor_names}
    monkeypatch.setattr(dashboard, "_read_labels", labels_for)
    app = create_app(Settings(), registry=registry, runtime=runtime, repository=MemoryRepository(),
                     replay_repository=store, replay_worker_enabled=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, service, store, runtime


def test_catalog_and_completed_comparison_are_typed_and_preserve_unknowns(fixture_service, monkeypatch):
    client, service, store, runtime = fixture_service
    catalog = client.get("/sensors")
    assert catalog.status_code == 200
    assert len(catalog.json()["items"]) == 27
    snapshot = start(service)
    rid = snapshot["replay_id"]
    drain(service, rid)
    original = deepcopy(store.events(rid))
    monkeypatch.setattr(runtime, "predict", lambda *args, **kwargs: pytest.fail("Evaluation cannot infer"))
    response = client.get(f"/replays/{rid}/evaluation")
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["retrospective_only"] is True and page["simulated_playback"] is True
    assert page["accepted_for_monitoring"] is False
    rows = page["items"]
    assert [row["raw_class"] for row in rows] == [None, 0, 102, 999, 2]
    assert [row["actual_phase"] for row in rows] == ["unknown", "normal", "transient", "unknown", "event"]
    assert [row["actual_binary"] for row in rows] == [None, 0, 1, None, 1]
    assert [row["decision_matches"] for row in rows] == [None, False, True, None, True]
    assert [row["actual_event_family"] for row in rows] == [None, 0, 2, None, 2]
    assert "source_path" not in response.text
    assert store.events(rid) == original
    assert "raw_class" not in json.dumps(original)


@pytest.mark.parametrize("state", ["created", "running", "paused", "stopped", "failed"])
def test_no_labels_can_be_read_before_completion(fixture_service, monkeypatch, state):
    client, service, store, _ = fixture_service
    snapshot, _ = service.create(CreateReplay(source_instance_id=SOURCE), str(uuid4()))
    rid = snapshot["replay_id"]
    store.sessions[rid]["state"] = state
    monkeypatch.setattr(dashboard, "_read_labels", lambda *args: pytest.fail("Must not read labels"))
    response = client.get(f"/replays/{rid}/evaluation")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPLAY_NOT_COMPLETED"


def test_evaluation_pagination_and_invalid_boundaries(fixture_service):
    client, service, store, _ = fixture_service
    rid = start(service)["replay_id"]
    drain(service, rid)
    first = client.get(f"/replays/{rid}/evaluation?limit=2").json()
    second = client.get(f"/replays/{rid}/evaluation", params={"limit": 2, "after_sequence": first["next_after_sequence"]}).json()
    assert [r["source_position"] for r in first["items"] + second["items"]] == [59, 69, 79, 89]
    assert client.get(f"/replays/{rid}/evaluation?after_sequence=99999").status_code == 400
    assert client.get(f"/replays/{rid}/evaluation?limit=1001").status_code == 422
    assert client.get(f"/replays/{uuid4()}/evaluation").status_code == 404
    store.sessions[rid]["cursor_position"] = 59
    assert client.get(f"/replays/{rid}/evaluation").status_code == 503


def test_evaluation_rejects_tampered_stored_provenance(fixture_service):
    client, service, store, _ = fixture_service
    rid = start(service)["replay_id"]
    drain(service, rid)
    event = next(event for event in store.history[rid] if event["event_type"] == "prediction")
    event["payload"]["prediction"]["provenance"]["source_sha256"] = "c" * 64
    assert client.get(f"/replays/{rid}/evaluation").status_code == 503


def test_replay_listing_uses_stable_keyset_and_bounds(fixture_service):
    client, service, store, _ = fixture_service
    ids = []
    for _ in range(3):
        snapshot, _ = service.create(CreateReplay(source_instance_id=SOURCE), str(uuid4()))
        ids.append(snapshot["replay_id"])
        service.command(ids[-1], ReplayCommand(command="stop", expected_version=1), str(uuid4()))
    first = client.get("/replays?limit=2").json()
    assert [s["replay_id"] for s in first["items"]] == ids[::-1][:2]
    newer, _ = service.create(CreateReplay(source_instance_id=SOURCE), str(uuid4()))
    second = client.get("/replays", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [s["replay_id"] for s in second["items"]] == ids[:1]
    assert second["next_cursor"] is None
    assert client.get("/replays").json()["items"][0]["replay_id"] == newer["replay_id"]
    assert client.get("/replays?cursor=malformed").status_code == 400
    assert client.get("/replays?limit=101").status_code == 422


def test_retrospective_boolean_marker_cannot_be_numeric():
    with pytest.raises(ValidationError):
        RetrospectivePage.model_validate({"retrospective_only": 1})
    with pytest.raises(ValidationError):
        RetrospectivePrediction.model_validate({"actual_binary": True})


def test_real_labels_are_decoded_separately_without_test_sources():
    registry = Registry(ROOT)
    registry.startup()
    source_id = "3w:3b7750afe480cb1d04361795d4a5cded832ae3a05d5ef30f533d440c81bfb4cf"
    labels, meanings = dashboard._read_labels(registry, source_id)
    assert list(labels.columns) == ["class", "state"]
    assert pd.isna(labels.iloc[3599]["class"])
    assert labels.iloc[3600]["class"] == 0
    assert labels.iloc[5759]["class"] == 102
    assert meanings[102] == {"family": 2, "name": "SPURIOUS_CLOSURE_OF_DHSV", "phase": "transient"}
    assert "class" not in registry.record(source_id).frame.columns
    with pytest.raises(ServiceError):
        dashboard._read_labels(registry, "unregistered-source")


def test_actual_postgres_replay_list_and_retrospective_join(monkeypatch):
    url = os.environ.get("OILWELL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL test database required")
    store = PostgresReplayRepository(Settings(database_url=url))
    store.initialize()
    registry, runtime, _, service = components(store, rows=70)
    monkeypatch.setattr(dashboard, "_read_labels", labels_for)
    key = f"dashboard-{uuid4()}"
    snapshot, _ = service.create(CreateReplay(source_instance_id=SOURCE), key)
    rid = snapshot["replay_id"]
    try:
        service.command(rid, ReplayCommand(command="start", expected_version=1), key + "-start")
        drain(service, rid)
        page = store.list_replays(limit=1)
        assert page["items"][0]["replay_id"] == rid
        monkeypatch.setattr(runtime, "predict", lambda *args, **kwargs: pytest.fail("No retrospective inference"))
        result = dashboard.retrospective_page(service, UUID(rid), 0, 100)
        assert [row.actual_binary for row in result.items] == [None, 0]
        assert [row.decision_matches for row in result.items] == [None, False]
        restored = PostgresReplayRepository(store.settings)
        assert restored.list_replays(limit=1)["items"][0] == store.get(rid)
    finally:
        with store._connection() as connection:
            connection.execute("DELETE FROM oilwell_replay_events WHERE replay_id=%s", (rid,))
            connection.execute("DELETE FROM oilwell_replay_requests WHERE scope=%s OR (scope='create' AND key=%s)", (rid, key))
            connection.execute("DELETE FROM oilwell_replays WHERE replay_id=%s", (rid,))
