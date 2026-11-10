"""Read-only dashboard endpoints. Labels never enter replay or inference."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
import pandas as pd

from backend.app.dashboard_schemas import ReplayList, RetrospectivePage, SensorCatalog
from backend.app.errors import ServiceError
from backend.app.replay_schemas import ReplayPrediction
from backend.app.schemas import ErrorResponse


def encode_replay_cursor(stamp: datetime, replay_id: str) -> str:
    payload = ["replay-list-v1", stamp.astimezone(timezone.utc).isoformat(), str(replay_id)]
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_replay_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        if len(cursor) > 256:
            raise ValueError("Cursor length")
        raw = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if not isinstance(raw, list) or len(raw) != 3 or raw[0] != "replay-list-v1":
            raise ValueError("Cursor scope")
        stamp = datetime.fromisoformat(raw[1])
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("Cursor timezone")
        return stamp, UUID(raw[2])
    except (ValueError, TypeError, UnicodeDecodeError, AttributeError) as exc:
        raise ServiceError("INVALID_CURSOR", "Cursor is invalid for replay listing", 400) from exc


def replay_list_page(rows: list[tuple[datetime, str, dict[str, Any]]], limit: int) -> dict[str, Any]:
    page = rows[:limit]
    cursor = encode_replay_cursor(page[-1][0], page[-1][1]) if len(rows) > limit else None
    return {"items": [row[2] for row in page], "next_cursor": cursor}


def _read_labels(registry: Any, source_id: str) -> tuple[pd.DataFrame, dict[int, dict[str, Any]]]:
    """Verify bytes and decode only target columns, after the completed-state gate.

    One request retains at most one approved source label frame. Nothing is cached
    in Registry, Runtime, or the worker, and no endpoint accepts filesystem paths.
    """
    record = registry.record(source_id)
    source = record.source
    raw_root = (registry.root / "data/raw/3w").resolve()
    path = (raw_root / source.dataset_version / source.dataset_revision / source.source_path).resolve()
    try:
        if not path.is_relative_to(raw_root) or path.stat().st_size > 128 * 1024 * 1024:
            raise ValueError("Source boundary")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != source.sha256:
            raise ValueError("Source bytes changed")
        metadata_bytes = (registry.root / "data/manifests/dataset_metadata.json").read_bytes()
        if hashlib.sha256(metadata_bytes).hexdigest() != source.registry_sha256:
            raise ValueError("Label registry changed")
        metadata = json.loads(metadata_bytes)
        labels = pd.read_parquet(BytesIO(payload), columns=["class", "state"], engine="pyarrow")
        if not labels.index.equals(record.frame.index) or list(labels.columns) != ["class", "state"]:
            raise ValueError("Label alignment changed")
        meanings: dict[int, dict[str, Any]] = {}
        for event in metadata["events"]:
            base = event["label"]
            meanings[base] = {"family": base, "name": event["name"], "phase": "normal" if base == 0 else "event"}
            if event["transient_label"] is not None:
                meanings[event["transient_label"]] = {"family": base, "name": event["name"], "phase": "transient"}
        return labels, meanings
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ServiceError("EVALUATION_SOURCE_UNAVAILABLE", "Verified retrospective labels are unavailable", 503) from exc


def retrospective_page(service: Any, replay_id: UUID, after_sequence: int, limit: int) -> RetrospectivePage:
    snapshot = service.store.get(replay_id)
    if snapshot["state"] != "completed":
        raise ServiceError("REPLAY_NOT_COMPLETED", "Ground truth is available only after replay completion", 409)
    record = service.registry.record(snapshot["source_instance_id"])
    service._check_binding(snapshot, record, service.runtime.info())
    if snapshot["cursor_position"] != snapshot["end_position"]:
        raise ServiceError("EVALUATION_BOUNDARY_INVALID", "Completed replay boundary is inconsistent", 503)
    page = service.store.events(replay_id, after_sequence, limit, "prediction")
    items: list[dict[str, Any]] = []
    if page["items"]:
        labels, meanings = _read_labels(service.registry, snapshot["source_instance_id"])
        for event in page["items"]:
            envelope = ReplayPrediction.model_validate(event["payload"])
            prediction = envelope.prediction
            position = envelope.source_position
            if (str(envelope.replay_id) != str(replay_id)
                    or envelope.sequence != event["sequence"]
                    or not snapshot["start_position"] + 59 <= position <= snapshot["cursor_position"]
                    or position >= len(labels)
                    or prediction.provenance.source_instance_id != snapshot["source_instance_id"]
                    or prediction.provenance.source_sha256 != snapshot["source_sha256"]
                    or prediction.provenance.source_timestamp != labels.index[position].isoformat()):
                raise ServiceError("EVALUATION_BOUNDARY_INVALID", "Stored prediction does not match retrospective source boundary", 503)
            values = labels.iloc[position]
            raw_class = None if pd.isna(values["class"]) else int(values["class"])
            raw_state = None if pd.isna(values["state"]) else int(values["state"])
            meaning = meanings.get(raw_class)
            binary = None if meaning is None else int(meaning["family"] != 0)
            predicted = None if prediction.event_type == "unknown" else int(prediction.event_type == "undesirable_event")
            items.append({"sequence": envelope.sequence, "source_position": position,
                "prediction_id": prediction.prediction_id, "timestamp": prediction.provenance.source_timestamp,
                "abnormal_score": prediction.abnormal_score, "predicted_event_type": prediction.event_type,
                "raw_class": raw_class, "raw_state": raw_state,
                "actual_event_family": None if meaning is None else meaning["family"],
                "actual_event_name": None if meaning is None else meaning["name"],
                "actual_phase": "unknown" if meaning is None else meaning["phase"],
                "actual_binary": binary, "decision_matches": None if binary is None or predicted is None else binary == predicted})
    return RetrospectivePage(replay_id=replay_id, source_instance_id=snapshot["source_instance_id"],
        source_sha256=snapshot["source_sha256"], items=items, next_after_sequence=page["next_after_sequence"])


def dashboard_router(app: Any) -> APIRouter:
    router = APIRouter(tags=["historical dashboard"], responses={
        status: {"model": ErrorResponse} for status in (400, 404, 409, 422, 503)})

    def service() -> Any:
        if not getattr(app.state, "replay_ready", False):
            raise ServiceError("REPLAY_UNAVAILABLE", "Replay service is unavailable", 503)
        return app.state.replay_service

    @router.get("/replays", response_model=ReplayList)
    def list_replays(cursor: Annotated[str | None, Query(max_length=256)] = None,
                     limit: Annotated[int, Query(ge=1, le=100)] = 100) -> dict[str, Any]:
        return service().store.list_replays(cursor, limit)

    @router.get("/replays/{replay_id}/evaluation", response_model=RetrospectivePage)
    def evaluation(replay_id: UUID, after_sequence: Annotated[int, Query(ge=0)] = 0,
                   limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> RetrospectivePage:
        return retrospective_page(service(), replay_id, after_sequence, limit)

    @router.get("/sensors", response_model=SensorCatalog)
    def sensors() -> dict[str, Any]:
        if not getattr(app.state, "ready", {}).get("registry", False):
            raise ServiceError("REGISTRY_UNAVAILABLE", "Sensor registry is unavailable", 503)
        registry = app.state.registry
        return {"items": [{"name": name, "unit_or_domain": registry.units[name]} for name in registry.sensor_names]}

    return router
