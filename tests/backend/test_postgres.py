"""Actual PostgreSQL transaction checks; require an explicit isolated test DSN."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import threading
from uuid import uuid4

import pytest

from backend.app.errors import ServiceError
from backend.app.repository import PostgresRepository
import backend.app.repository as repository_module
from backend.app.settings import Settings
from tests.backend.test_api import prediction


@pytest.fixture
def repository():
    dsn = os.environ.get("OILWELL_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set OILWELL_TEST_DATABASE_URL to an isolated PostgreSQL database")
    value = PostgresRepository(Settings(database_url=dsn))
    value.initialize()
    return value


def test_postgres_atomic_idempotency_and_restart_read(repository):
    key = "test-" + str(uuid4())
    count = []
    def build():
        count.append(1)
        return prediction(uuid4(), datetime.now(timezone.utc))
    first, replayed = repository.get_or_create(key, "a" * 64, build)
    assert not replayed and len(count) == 1
    fresh = PostgresRepository(repository.settings)
    second, replayed = fresh.get_or_create(key, "a" * 64, build)
    assert replayed and second == first and len(count) == 1
    with pytest.raises(ServiceError) as exc:
        fresh.get_or_create(key, "b" * 64, build)
    assert exc.value.status_code == 409
    with repository._connect() as connection:
        assert connection.execute("SELECT count(*) FROM oilwell_alerts WHERE prediction_id=%s", (first.prediction_id,)).fetchone()[0] == 1


def test_postgres_concurrent_same_key_calls_build_once(repository):
    key = "test-" + str(uuid4()); lock = threading.Lock(); calls = []
    def build():
        with lock:
            calls.append(1)
        return prediction(uuid4(), datetime.now(timezone.utc))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repository.get_or_create(key, "c" * 64, build), range(4)))
    assert len(calls) == 1 and sum(not replayed for _, replayed in results) == 1
    assert len({value.prediction_id for value, _ in results}) == 1


def test_postgres_builder_failure_rolls_back_and_permits_retry(repository):
    key = "test-" + str(uuid4())
    def fail():
        raise ValueError("synthetic failure")
    with pytest.raises(ValueError):
        repository.get_or_create(key, "d" * 64, fail)
    with repository._connect() as connection:
        assert connection.execute("SELECT count(*) FROM oilwell_predictions WHERE idempotency_key=%s", (key,)).fetchone()[0] == 0
    value, replayed = repository.get_or_create(key, "d" * 64, lambda: prediction(uuid4(), datetime.now(timezone.utc)))
    assert not replayed and value.alert_status == "alert"


def test_postgres_alert_failure_rolls_back_inserted_prediction(repository, monkeypatch):
    key = "test-" + str(uuid4())
    def fail_after_prediction_insert(_):
        raise RuntimeError("synthetic alert publication failure")
    with monkeypatch.context() as context:
        context.setattr(repository_module, "_alert", fail_after_prediction_insert)
        with pytest.raises(RuntimeError):
            repository.get_or_create(key, "f" * 64, lambda: prediction(uuid4(), datetime.now(timezone.utc)))
    with repository._connect() as connection:
        assert connection.execute("SELECT count(*) FROM oilwell_predictions WHERE idempotency_key=%s", (key,)).fetchone()[0] == 0
    value, replayed = repository.get_or_create(key, "f" * 64, lambda: prediction(uuid4(), datetime.now(timezone.utc)))
    assert not replayed and value.alert_status == "alert"


def test_postgres_alert_cursor_filter_and_boundaries(repository):
    unique_well = "test-well-" + str(uuid4())
    ids = []
    for _ in range(3):
        def build():
            value = prediction(uuid4(), datetime.now(timezone.utc))
            return value.model_copy(update={"well_id": unique_well})
        value, _ = repository.get_or_create("test-" + str(uuid4()), "e" * 64, build)
        ids.append(str(value.prediction_id))
    first = repository.list_alerts(None, 2, unique_well)
    second = repository.list_alerts(first["next_cursor"], 2, unique_well)
    assert [r["prediction_id"] for r in first["items"] + second["items"]] == ids
    assert second["next_cursor"] is None
    with pytest.raises(ServiceError):
        repository.list_alerts(first["next_cursor"], 2, "another-well")
