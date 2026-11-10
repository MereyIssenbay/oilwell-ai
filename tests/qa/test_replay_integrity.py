"""Independent Phase 7 replay checks; fixture outputs are not model-quality evidence."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.errors import ServiceError
from backend.app.main import create_app
from backend.app.registry import Registry, RegisteredSource
from backend.app.repository import MemoryRepository
from backend.app.replay import ReplayService, ReplayWorker
from backend.app.replay_repository import MemoryReplayRepository, PostgresReplayRepository
from backend.app.replay_schemas import CreateReplay, ReplayCommand
from backend.app.schemas import DiagnosticPrediction
from backend.app.settings import Settings
from ml.data_pipeline.models import SENSOR_COLUMNS
from tests.qa.test_backend_integrity import prediction, FixtureRuntime


ROOT = Path(__file__).resolve().parents[2]


class ReplayFixtureRegistry(Registry):
    """In-memory declared fixture; no actual source path or raw writes."""
    def __init__(self):
        super().__init__(ROOT)
        source = SimpleNamespace(instance_id="qa-source", well_id="qa-well", sha256="0" * 64)
        frame = pd.DataFrame(1.0, index=pd.date_range("2026-01-01", periods=150, freq="s"), columns=SENSOR_COLUMNS)
        self.records = {"qa-source": RegisteredSource(source, frame)}
        self.sensor_names = tuple(SENSOR_COLUMNS)
        self.ready = True

    def startup(self):
        pass


class ReplayFixtureRuntime(FixtureRuntime):
    def __init__(self, registry):
        super().__init__()
        self.registry = registry
        self.statuses = {69: "insufficient_data", 89: "normal"}

    def predict(self, request, prediction_id, generated_at):
        self.calls.append(request.endpoint_position)
        p = request.endpoint_position
        frame = self.registry.records["qa-source"].frame
        end = frame.index[p].isoformat()
        start = frame.index[p - 59].isoformat() + "Z"
        status = self.statuses.get(p, "alert")
        value = prediction(prediction_id, generated_at, positive=status != "normal").model_dump(mode="json")
        value["timestamp"] = end + "Z"
        value["provenance"]["source_timestamp"] = end
        value["window"].update(start=start, end=end + "Z")
        value["sensor_evidence"][0].update(window_start=start, window_end=end + "Z")
        if status == "insufficient_data":
            value.update(event_type="unknown", confidence=None, confidence_kind="unavailable",
                         abnormal_score=None, alert_status=status, abstention_reason="missing_required_sensors")
            value["quality"]["status"] = "invalid"
        return DiagnosticPrediction.model_validate(value)


@pytest.fixture
def replay():
    registry = ReplayFixtureRegistry()
    runtime = ReplayFixtureRuntime(registry)
    store = MemoryReplayRepository()
    return ReplayService(registry, runtime, store)


def create_running(service, *, start=0, end=109, speed=1.0):
    s, _ = service.create(CreateReplay(source_instance_id="qa-source", start_position=start,
                                     end_position=end, speed_multiplier=speed), uuid4().hex)
    s, _ = service.command(s["replay_id"], ReplayCommand(command="start", expected_version=s["version"]), uuid4().hex)
    return s["replay_id"]


def advance(service, rid, count):
    for _ in range(count):
        assert service.step(rid, ignore_schedule=True)


def events(service, rid, kind=None):
    return service.store.events(rid, 0, 1000, kind)["items"]


def test_episode_dedup_abstention_resolution_and_past_snapshots(replay):
    rid = create_running(replay)
    advance(replay, rid, 110)
    predictions = [e["payload"] for e in events(replay, rid, "prediction")]
    transitions = [e["payload"] for e in events(replay, rid, "alert_episode")]
    assert [p["source_position"] for p in predictions] == [59, 69, 79, 89, 99, 109]
    assert [e["transition"] for e in transitions] == ["opened", "updated", "updated", "resolved", "opened", "updated"]
    assert len({e["episode_id"] for e in transitions}) == 2
    first = predictions[0]["alert_episode"]
    assert first["last_data_status"] == "alert"
    assert first["last_prediction_id"] == predictions[0]["prediction"]["prediction_id"]
    assert predictions[1]["alert_episode"]["episode_id"] == first["episode_id"]
    assert predictions[1]["alert_episode"]["last_data_status"] == "insufficient_data"
    assert predictions[3]["alert_episode"] is None
    assert predictions[4]["alert_episode"]["episode_id"] != first["episode_id"]
    assert replay.store.get(rid)["alert_episode"]["episode_id"] == predictions[-1]["alert_episode"]["episode_id"]
    assert len(events(replay, rid, "telemetry")) == 110
    all_events = events(replay, rid)
    assert [e["sequence"] for e in all_events] == list(range(1, len(all_events) + 1))
    for e in all_events:
        assert e["mode"] == "historical_replay" and e["simulated_playback"] is True
        assert e["diagnostic_only"] is True and e["accepted_for_monitoring"] is False
        assert not {"class", "source_path", "ground_truth"}.intersection(e["payload"])
    assert [e["payload"]["source_position"] for e in events(replay, rid, "telemetry")] == list(range(110))


def test_pause_resume_stop_idempotency_version_and_nonzero_start(replay):
    rid = create_running(replay, start=13, end=149)
    advance(replay, rid, 59)
    assert replay.runtime.calls == []
    snap = replay.store.get(rid)
    pause = ReplayCommand(command="pause", expected_version=snap["version"])
    saved, repeated = replay.command(rid, pause, "pause-key")
    assert not repeated and not replay.step(rid, ignore_schedule=True)
    assert replay.store.get(rid) == saved
    with pytest.raises(ServiceError) as conflict:
        replay.command(rid, ReplayCommand(command="resume", expected_version=snap["version"]), "stale")
    assert conflict.value.status_code == 409
    replay.command(rid, ReplayCommand(command="resume", expected_version=saved["version"]), "resume")
    original, repeated = replay.command(rid, pause, "pause-key")
    assert repeated and original == saved and replay.store.get(rid)["state"] == "running"
    advance(replay, rid, 8)
    assert replay.runtime.calls == [79]
    state = replay.store.get(rid)
    stop, _ = replay.command(rid, ReplayCommand(command="stop", expected_version=state["version"]), "stop")
    assert stop["cursor_position"] == 79
    assert not replay.step(rid, ignore_schedule=True)
    assert replay.store.get(rid) == stop


@pytest.mark.parametrize("change", ["source", "model", "threshold", "preprocessor"])
def test_changed_frozen_binding_rolls_back_before_any_new_observation(replay, change, monkeypatch):
    rid = create_running(replay)
    advance(replay, rid, 2)
    before = replay.store.get(rid)
    before_events = events(replay, rid)
    if change == "source":
        replay.registry.records["qa-source"].source.sha256 = "1" * 64
    else:
        info = replay.runtime.info()
        field = {"model": "model_version", "threshold": "threshold", "preprocessor": "preprocessor_fingerprint"}[change]
        info[field] = .75 if change == "threshold" else "changed"
        monkeypatch.setattr(replay.runtime, "info", lambda: info)
    with pytest.raises(ServiceError) as failure:
        replay.step(rid, ignore_schedule=True)
    assert failure.value.code == "REPLAY_BINDING_CHANGED"
    assert replay.store.get(rid) == before and events(replay, rid) == before_events


@pytest.fixture
def replay_api(replay):
    app = create_app(Settings(), runtime=replay.runtime, registry=replay.registry,
                     repository=MemoryRepository(), replay_repository=replay.store, replay_worker_enabled=False)
    with TestClient(app) as client:
        yield client, app.state.replay_service


def test_sse_reconnect_drains_exact_persisted_suffix_and_rejects_foreign_cursor(replay_api):
    client, service = replay_api
    rid = create_running(service, end=69)
    advance(service, rid, 70)
    saved = events(service, rid)
    cut = 61
    response = client.get(f"/replays/{rid}/events", headers={"Last-Event-ID": f"{rid}:{cut}"})
    assert response.status_code == 200 and "text/event-stream" in response.headers["content-type"]
    data = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    ids = [line[4:] for line in response.text.splitlines() if line.startswith("id: ")]
    assert data == [e for e in saved if e["sequence"] > cut]
    assert ids == [f"{rid}:{e['sequence']}" for e in data]
    assert client.get(f"/replays/{rid}/events", headers={"Last-Event-ID": f"{rid}:{len(saved)}"}).text == ""
    for cursor in (f"{uuid4()}:1", f"{rid}:999999", f"{rid}:-1", "1"):
        rejected = client.get(f"/replays/{rid}/events", headers={"Last-Event-ID": cursor})
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "INVALID_CURSOR"
    assert client.get(f"/replays/{rid}/event-history", params={"limit": 1001}).status_code == 422


def test_stream_failure_is_sanitized_and_reconnect_uses_last_durable_id(replay_api, monkeypatch):
    client, service = replay_api
    rid = create_running(service, end=0)
    advance(service, rid, 1)
    original = service.store.events
    count = 0
    def fail_after_preflight(*args, **kwargs):
        nonlocal count
        count += 1
        if count > 1:
            raise RuntimeError("qa-secret-password C:\\private\\path")
        return original(*args, **kwargs)
    monkeypatch.setattr(service.store, "events", fail_after_preflight)
    response = client.get(f"/replays/{rid}/events")
    assert response.status_code == 200 and "event: stream_error" in response.text
    assert "STREAM_UNAVAILABLE" in response.text
    assert "qa-secret-password" not in response.text and "private" not in response.text
    assert "id:" not in response.text


def test_replay_initialization_failure_is_degraded_and_has_no_memory_fallback(replay):
    class UnavailableStore(MemoryReplayRepository):
        def initialize(self):
            raise RuntimeError("qa-secret-password C:\\private\\path")
    app = create_app(Settings(), runtime=replay.runtime, registry=replay.registry,
                     repository=MemoryRepository(), replay_repository=UnavailableStore(), replay_worker_enabled=False)
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        health = client.get("/health")
        assert health.status_code == 503 and health.json()["status"] == "degraded"
        response = client.post("/replays", json={"source_instance_id": "qa-source"}, headers={"Idempotency-Key": "unavailable"})
        assert response.status_code == 503 and response.json()["error"]["code"] == "REPLAY_UNAVAILABLE"
        assert "qa-secret-password" not in response.text and "private" not in response.text


@pytest.fixture
def postgres_replay():
    url = os.environ.get("OILWELL_QA_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated QA PostgreSQL database is required")
    store = PostgresReplayRepository(Settings(database_url=url))
    store.initialize()
    registry = ReplayFixtureRegistry()
    service = ReplayService(registry, ReplayFixtureRuntime(registry), store)
    prefix = "qa-replay-" + uuid4().hex
    s, _ = service.create(CreateReplay(source_instance_id="qa-source", end_position=109), prefix)
    rid = s["replay_id"]
    service.command(rid, ReplayCommand(command="start", expected_version=s["version"]), prefix + "-start")
    try:
        yield service, rid, url
    finally:
        with store._connect() as c:
            c.execute("DELETE FROM oilwell_replay_events WHERE replay_id=%s", (rid,))
            c.execute("DELETE FROM oilwell_replay_requests WHERE scope=%s OR (scope='create' AND key=%s)", (rid, prefix))
            c.execute("DELETE FROM oilwell_replays WHERE replay_id=%s", (rid,))


def test_real_postgres_restart_and_concurrent_workers_do_not_duplicate_cursor_or_alert(postgres_replay):
    service, rid, url = postgres_replay
    advance(service, rid, 59)
    # One due row. All competing workers must observe the same transaction cursor/due state.
    with service.store._connect() as c:
        c.execute("UPDATE oilwell_replays SET due_at=now()-interval '1 second' WHERE replay_id=%s", (rid,))
    with ThreadPoolExecutor(max_workers=4) as pool:
        stepped = list(pool.map(lambda _: service.step(rid), range(4)))
    assert sum(stepped) == 1
    assert service.runtime.calls == [59]
    before = service.store.get(rid)
    history = events(service, rid)
    restarted = ReplayService(service.registry, service.runtime, PostgresReplayRepository(Settings(database_url=url)))
    assert restarted.store.get(rid) == before and events(restarted, rid) == history
    advance(restarted, rid, 10)
    assert restarted.store.get(rid)["cursor_position"] == 69
    assert service.runtime.calls == [59, 69]
    assert len([e for e in events(restarted, rid, "alert_episode") if e["payload"]["transition"] == "opened"]) == 1
    assert len(events(restarted, rid, "telemetry")) == 70


def test_real_postgres_partial_event_insert_rolls_back_cursor_prediction_and_episode(postgres_replay, monkeypatch):
    import psycopg
    service, rid, _ = postgres_replay
    advance(service, rid, 59)
    before = service.store.get(rid)
    history = events(service, rid)
    original = service.store._append
    def failing_append(connection, snapshot, batch):
        original(connection, snapshot, batch[:1])
        raise psycopg.OperationalError("qa-secret-password")
    monkeypatch.setattr(service.store, "_append", failing_append)
    with pytest.raises(ServiceError) as error:
        service.step(rid, ignore_schedule=True)
    assert error.value.status_code == 503 and "qa-secret-password" not in error.value.message
    assert service.store.get(rid) == before and events(service, rid) == history
    monkeypatch.setattr(service.store, "_append", original)
    assert service.step(rid, ignore_schedule=True)
    assert service.store.get(rid)["cursor_position"] == 59
    assert len(events(service, rid, "prediction")) == len(events(service, rid, "alert_episode")) == 1


def test_actual_worker_thread_restart_resumes_committed_postgres_cursor(postgres_replay):
    service, rid, url = postgres_replay
    before = events(service, rid)
    def wait_for_cursor(store, position):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = store.get(rid)["cursor_position"]
            if current is not None and current >= position:
                return
            time.sleep(.02)
        pytest.fail("Replay worker did not advance within five seconds")
    worker = ReplayWorker(service)
    worker.start()
    try:
        wait_for_cursor(service.store, 0)
    finally:
        worker.stop()
    assert not worker.thread.is_alive()
    committed = service.store.get(rid)
    first_history = events(service, rid)
    assert first_history[:len(before)] == before
    restarted = ReplayService(service.registry, service.runtime, PostgresReplayRepository(Settings(database_url=url)))
    next_worker = ReplayWorker(restarted)
    next_worker.start()
    try:
        wait_for_cursor(restarted.store, committed["cursor_position"] + 1)
    finally:
        next_worker.stop()
    after = events(restarted, rid)
    assert after[:len(first_history)] == first_history
    positions = [e["payload"]["source_position"] for e in after if e["event_type"] == "telemetry"]
    assert positions == list(range(len(positions)))


def test_replay_preserves_originals_selected_artifacts_and_single_test_access():
    """Hash raw bytes only: never decode or infer on frozen test observations."""
    def sha(path):
        return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

    subset = json.loads((ROOT / "data/manifests/subset.json").read_text())
    originals = subset["files"] + subset["metadata"]
    assert len(originals) == 31
    for item in originals:
        assert sha(item["local_path"]) == item["sha256"]
    assert sha("reports/experiments/selection.json") == "dfbe88250db8808d58730ab6f0010da3c548cb4b1c26715ba4a4b78057e7130b"
    selection = json.loads((ROOT / "reports/experiments/selection.json").read_text())
    for path, expected in selection["code_sha256"].items():
        assert sha(path) == expected
    for item in selection["data_provenance"]["artifacts"].values():
        assert sha(item["path"]) == item["sha256"]
    bundle = Path(selection["bundle_path"])
    assert sha(bundle / "manifest.json") == selection["bundle_manifest_sha256"]
    manifest = json.loads((ROOT / bundle / "manifest.json").read_text())
    assert manifest["accepted_for_monitoring"] is False
    for path, expected in manifest["artifact_sha256"].items():
        assert sha(bundle / path) == expected
    journal = json.loads((ROOT / "reports/experiments/test_access.json").read_text())
    assert journal["status"] == "COMPLETE" and journal["test_attempts"] == 1
    assert sha(journal["prediction_path"]) == journal["prediction_sha256"]
    assert sha("reports/experiments/test_metrics.json") == journal["metrics_sha256"]
