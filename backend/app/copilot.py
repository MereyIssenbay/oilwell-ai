"""Explain immutable predictions; never execute inference or read target labels."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from typing import Annotated
from uuid import UUID

import numpy as np
import pandas as pd
from fastapi import APIRouter, Path, Request
from pydantic import ValidationError

from backend.app.errors import ServiceError
from backend.app.schemas import DiagnosticPrediction, ErrorResponse
from backend.app.replay_schemas import ReplayEvent, ReplayPrediction
from llm.schemas import EvidencePacket, Explanation, ExplanationRequest, SensorEvidence, Source

LOGGER = logging.getLogger("oilwell.api")


def _conflict() -> ServiceError:
    return ServiceError("EVIDENCE_CONFLICT", "Saved prediction and verified historical evidence disagree; explanation withheld", 409)


def build_evidence(registry, runtime, prediction: DiagnosticPrediction, *,
                   endpoint_position: int | None = None,
                   episode_state: str = "unknown") -> EvidencePacket:
    """Independently bind saved facts to the exact causal source window.

    Only this field allowlist reaches llm/. Source identities stay in this adapter.
    Latest is the final observation, not the most recent non-null observation.
    Trend is descriptive OLS on finite observations, never feature attribution.
    """
    try:
        p = DiagnosticPrediction.model_validate(prediction)
        info = runtime.info()  # metadata only; never runtime.predict()
        record = registry.record(p.provenance.source_instance_id)
        source = record.source
        if (source.sha256 != p.provenance.source_sha256 or source.well_id != p.well_id
                or source.dataset_revision != p.provenance.dataset_revision
                or source.dataset_version != p.provenance.dataset_version
                or info["model_version"] != p.model_version
                or info["threshold"] != p.threshold
                or info["model_artifact_sha256"] != p.provenance.model_artifact_sha256
                or info["preprocessor_fingerprint"] != p.provenance.preprocessor_fingerprint):
            raise _conflict()
        if endpoint_position is None:
            endpoint_position = int(record.frame.index.get_loc(pd.Timestamp(p.provenance.source_timestamp)))
        _, window = registry.window(p.provenance.source_instance_id, endpoint_position)
        if (len(window) != p.window.sample_count or len(window) > 60
                or list(window.columns) != list(registry.sensor_names)
                or window.index[0].isoformat() != p.window.start.replace(tzinfo=None).isoformat()
                or window.index[-1].isoformat() != p.provenance.source_timestamp):
            raise _conflict()
        payload = [{"timestamp": t.isoformat(), "sensors": {
            name: None if pd.isna(v) else float(v) for name, v in row.items()}}
            for t, row in window.iterrows()]
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if digest != p.provenance.request_window_sha256:
            raise _conflict()
        stored = {e.sensor_name: e for e in p.sensor_evidence}
        if set(stored) != set(registry.sensor_names):
            raise _conflict()
        seconds = (window.index - window.index[0]).total_seconds().to_numpy(dtype=float)
        sensors = []
        for index, name in enumerate(registry.sensor_names, start=1):
            values = window[name].to_numpy(dtype=float)
            mask = np.isfinite(values)
            count = int(mask.sum())
            mean = float(values[mask].mean()) if count else None
            missing = float(1 - count / len(values))
            e = stored[name]
            if ((mean is None) != (e.value is None)
                    or (mean is not None and not math.isclose(mean, e.value, rel_tol=1e-12, abs_tol=1e-12))
                    or not math.isclose(missing, e.missing_fraction, rel_tol=0, abs_tol=1e-15)
                    or e.unit != registry.units[name]
                    or e.window_start != p.window.start or e.window_end != p.window.end):
                raise _conflict()
            trend = None
            if count >= 2:
                x = seconds[mask] - seconds[mask].mean()
                denominator = float(np.dot(x, x))
                if denominator > 0:
                    trend = float(np.dot(x, values[mask] - mean) / denominator)
            sensors.append(SensorEvidence(evidence_id=f"e{index}", sensor=name, unit=e.unit,
                mean=e.value, latest=float(values[-1]) if mask[-1] else None,
                trend_per_second=trend, missing_fraction=missing, observed_count=count))
        return EvidencePacket(model_version=p.model_version, event_type=p.event_type,
            confidence=p.confidence, abnormal_score=p.abnormal_score, threshold=p.threshold,
            alert_status=p.alert_status, episode_state=episode_state,
            source_origin=p.provenance.source_kind, source_time_basis=p.provenance.time_basis,
            window_start=window.index[0].isoformat(), window_end=window.index[-1].isoformat(),
            sample_count=len(window), expected_sample_count=p.window.expected_sample_count,
            sensors=sensors, abstention_reason=p.abstention_reason)
    except ServiceError:
        raise
    except (ValueError, KeyError, TypeError, IndexError, ValidationError) as exc:
        raise _conflict() from exc


def saved_replay_prediction(store, replay_id: UUID, sequence: int) -> ReplayPrediction:
    rows = store.events(str(replay_id), after_sequence=sequence - 1, limit=1)["items"]
    if not rows or rows[0]["sequence"] != sequence or rows[0]["event_type"] != "prediction":
        raise ServiceError("PREDICTION_NOT_FOUND", "No saved prediction at this replay sequence", 404)
    try:
        event = ReplayEvent.model_validate(rows[0])
        value = event.payload
        if (not isinstance(value, ReplayPrediction) or event.replay_id != replay_id
                or value.replay_id != replay_id or value.sequence != sequence):
            raise _conflict()
        return value
    except ValidationError as exc:
        raise _conflict() from exc


def copilot_router(app) -> APIRouter:
    from llm.service import CopilotService

    router = APIRouter(tags=["copilot"])
    slots = threading.BoundedSemaphore(2)
    errors = {code: {"model": ErrorResponse} for code in (400, 404, 409, 422, 429, 503)}

    def service():
        value = getattr(app.state, "copilot_service", None)
        if value is None:
            # Construction is lazy, under a separate lock to prevent duplicate budgets.
            with app.state.copilot_init_lock:
                value = getattr(app.state, "copilot_service", None)
                if value is None:
                    value = CopilotService.from_environment(app.state.settings.root)
                    app.state.copilot_service = value
        return value

    def ready():
        if not all(getattr(app.state, "ready", {}).get(k, False) for k in ("registry", "model", "database")):
            raise ServiceError("COPILOT_UNAVAILABLE", "Historical evidence dependencies are unavailable", 503)

    def explain(request, body, prediction, position=None, episode="unknown"):
        ready()
        if not slots.acquire(blocking=False):
            raise ServiceError("COPILOT_BUSY", "Explanation concurrency limit reached", 429)
        try:
            packet = build_evidence(app.state.registry, app.state.runtime, prediction,
                                    endpoint_position=position, episode_state=episode)
            result = service().explain(packet, body.question, use_provider=body.use_provider)
            LOGGER.info(json.dumps({"event": "copilot_explanation", "request_id": request.state.request_id,
                "prediction_id": str(prediction.prediction_id), "status": result.status,
                "evidence_hash": result.evidence_hash}, allow_nan=False))
            return result
        finally:
            slots.release()

    @router.post("/replays/{id}/predictions/{sequence}/explanation", response_model=Explanation, responses=errors)
    def replay_explanation(request: Request, id: UUID, sequence: Annotated[int, Path(ge=1)],
                           body: ExplanationRequest):
        ready()
        if not getattr(app.state, "replay_ready", False):
            raise ServiceError("REPLAY_UNAVAILABLE", "Replay evidence is unavailable", 503)
        value = saved_replay_prediction(app.state.replay_service.store, id, sequence)
        return explain(request, body, value.prediction, value.source_position,
                       "open" if value.alert_episode is not None else "none")

    @router.post("/predictions/{id}/explanation", response_model=Explanation, responses=errors)
    def prediction_explanation(request: Request, id: UUID, body: ExplanationRequest):
        ready()
        value = app.state.repository.get_prediction(id)
        return explain(request, body, value)

    @router.get("/copilot/sources/{source_id}", response_model=Source, responses=errors)
    def source_content(source_id: Annotated[str, Path(pattern=r"^[a-z0-9-]{1,64}$")]):
        try:
            return service().get_source(source_id)
        except KeyError as exc:
            raise ServiceError("SOURCE_NOT_FOUND", "Curated knowledge source not found", 404) from exc

    return router
