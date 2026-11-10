"""Atomic PostgreSQL diagnostic predictions and per-prediction alert records."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import threading
from typing import Any, Callable
from uuid import uuid4

from backend.app.errors import ServiceError
from backend.app.pagination import decode_cursor, encode_cursor
from backend.app.schemas import Alert, DiagnosticPrediction
from backend.app.settings import Settings

PredictionFactory = Callable[[], DiagnosticPrediction]


def _alert(prediction: DiagnosticPrediction) -> dict[str, Any] | None:
    if prediction.alert_status != "alert":
        return None
    value = Alert(alert_id=uuid4(), prediction_id=prediction.prediction_id, well_id=prediction.well_id,
                  source_instance_id=prediction.provenance.source_instance_id,
                  timestamp=prediction.timestamp, generated_at=prediction.execution.generated_at,
                  model_version=prediction.model_version, abnormal_score=prediction.abnormal_score,
                  threshold=prediction.threshold)
    return value.model_dump(mode="json")


class PostgresRepository:
    """Connection-per-operation, bounded timeouts and no in-memory fallback."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _connect(self):
        if not self.settings.database_url:
            raise ServiceError("DATABASE_UNAVAILABLE", "Database is unavailable", 503)
        import psycopg
        return psycopg.connect(self.settings.database_url,
                               connect_timeout=self.settings.database_connect_timeout,
                               options=f"-c statement_timeout={self.settings.database_statement_timeout_ms} "
                                       f"-c lock_timeout={self.settings.database_statement_timeout_ms}")

    def initialize(self) -> None:
        import psycopg
        try:
            migration = Path(__file__).resolve().parents[1] / "migrations/001_diagnostic_predictions.sql"
            with self._connect() as connection:
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (64934935862810,))
                connection.execute(migration.read_text(encoding="utf-8"), prepare=False)
        except psycopg.Error as exc:
            raise ServiceError("DATABASE_UNAVAILABLE", "Database is unavailable", 503) from exc

    def health(self) -> bool:
        try:
            with self._connect() as connection:
                return connection.execute("SELECT version FROM oilwell_schema_migrations WHERE version=1").fetchone() == (1,)
        except Exception:
            return False

    def get_or_create(self, key: str, request_hash: str,
                      build: PredictionFactory) -> tuple[DiagnosticPrediction, bool]:
        import psycopg
        from psycopg.types.json import Jsonb
        lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
        try:
            with self._connect() as connection:
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
                existing = connection.execute(
                    "SELECT request_sha256,payload FROM oilwell_predictions WHERE idempotency_key=%s", (key,)).fetchone()
                if existing:
                    if existing[0] != request_hash:
                        raise ServiceError("IDEMPOTENCY_CONFLICT", "Idempotency key was used for another request", 409)
                    return DiagnosticPrediction.model_validate(existing[1]), True
                prediction = DiagnosticPrediction.model_validate(build())
                payload = prediction.model_dump(mode="json")
                connection.execute(
                    "INSERT INTO oilwell_predictions(prediction_id,idempotency_key,request_sha256,well_id,"
                    "source_instance_id,model_version,source_timestamp,generated_at,payload) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (prediction.prediction_id, key, request_hash, prediction.well_id,
                     prediction.provenance.source_instance_id, prediction.model_version, prediction.timestamp,
                     prediction.execution.generated_at, Jsonb(payload)))
                alert = _alert(prediction)
                if alert is not None:
                    connection.execute(
                        "INSERT INTO oilwell_alerts(alert_id,prediction_id,well_id,source_instance_id,model_version,"
                        "source_timestamp,generated_at,payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (alert["alert_id"], prediction.prediction_id, prediction.well_id,
                         prediction.provenance.source_instance_id, prediction.model_version,
                         prediction.timestamp, prediction.execution.generated_at, Jsonb(alert)))
                return prediction, False
        except psycopg.Error as exc:
            raise ServiceError("DATABASE_UNAVAILABLE", "Database is unavailable", 503) from exc

    def list_alerts(self, cursor: str | None, limit: int, well_id: str | None = None) -> dict[str, Any]:
        import psycopg
        after = decode_cursor(cursor, "alerts", well_id)
        try:
            with self._connect() as connection:
                if well_id is None:
                    rows = connection.execute(
                        "SELECT sequence,payload FROM oilwell_alerts WHERE sequence>%s ORDER BY sequence LIMIT %s",
                        (after, limit + 1)).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT sequence,payload FROM oilwell_alerts WHERE sequence>%s AND well_id=%s "
                        "ORDER BY sequence LIMIT %s", (after, well_id, limit + 1)).fetchall()
            selected = rows[:limit]
            return {"items": [row[1] for row in selected],
                    "next_cursor": encode_cursor("alerts", selected[-1][0], well_id) if len(rows) > limit else None}
        except psycopg.Error as exc:
            raise ServiceError("DATABASE_UNAVAILABLE", "Database is unavailable", 503) from exc


class MemoryRepository:
    """Explicitly injected fixture repository. Never selected by runtime settings."""

    def __init__(self):
        self.predictions: dict[str, tuple[str, dict[str, Any]]] = {}
        self.alerts: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def initialize(self) -> None:
        pass

    def health(self) -> bool:
        return True

    def get_or_create(self, key: str, request_hash: str,
                      build: PredictionFactory) -> tuple[DiagnosticPrediction, bool]:
        with self._lock:
            if key in self.predictions:
                previous_hash, prediction = self.predictions[key]
                if previous_hash != request_hash:
                    raise ServiceError("IDEMPOTENCY_CONFLICT", "Idempotency key was used for another request", 409)
                return DiagnosticPrediction.model_validate(deepcopy(prediction)), True
            value = DiagnosticPrediction.model_validate(build())
            alert = _alert(value)
            self.predictions[key] = (request_hash, value.model_dump(mode="json"))
            if alert:
                self.alerts.append(alert)
            return value, False

    def list_alerts(self, cursor: str | None, limit: int, well_id: str | None = None) -> dict[str, Any]:
        after = decode_cursor(cursor, "alerts", well_id)
        with self._lock:
            rows = [(i, deepcopy(row)) for i, row in enumerate(self.alerts, start=1)
                    if i > after and (well_id is None or row["well_id"] == well_id)]
        page = rows[:limit]
        return {"items": [row[1] for row in page],
                "next_cursor": encode_cursor("alerts", page[-1][0], well_id) if len(rows) > limit else None}
