"""Loopback diagnostic FastAPI service. No fitting occurs in this module."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import threading
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from backend.app.errors import ServiceError
from backend.app.pagination import decode_cursor, encode_cursor
from backend.app.repository import PostgresRepository
from backend.app.schemas import (AlertPage, DiagnosticPrediction, ErrorResponse,
                                  Health, ModelInfo, PredictRequest, TelemetryPage, WellPage)
from backend.app.settings import Settings

LOGGER = logging.getLogger("oilwell.api")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(_handler)


def _log(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, sort_keys=True, allow_nan=False))


def _error(request_id: str, code: str, message: str, status: int,
           details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details or {},
                                   "request_id": request_id}}, status_code=status,
                        headers={"X-Request-ID": request_id})


class RequestBoundary:
    """Cap actual received bytes, generate request IDs, and sanitize exceptions."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        headers = dict(scope.get("headers", []))
        try:
            if b"content-length" in headers:
                length = int(headers[b"content-length"])
                if length < 0:
                    raise ValueError("Invalid length")
                if length > self.max_bytes:
                    return await _error(request_id, "PAYLOAD_TOO_LARGE", "Request body exceeds limit", 413)(scope, receive, send)
        except ValueError:
            return await _error(request_id, "INVALID_REQUEST", "Invalid content length", 400)(scope, receive, send)
        chunks = []
        size = 0
        while True:
            part = await receive()
            if part["type"] == "http.disconnect":
                return
            chunk = part.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                return await _error(request_id, "PAYLOAD_TOO_LARGE", "Request body exceeds limit", 413)(scope, receive, send)
            chunks.append(chunk)
            if not part.get("more_body", False):
                break
        body = b"".join(chunks)
        consumed = False
        started = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        async def identified_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, bounded_receive, identified_send)
        except Exception:
            _log("request_failed", request_id=request_id, error_code="INTERNAL_ERROR")
            if not started:
                await _error(request_id, "INTERNAL_ERROR", "Request could not be completed", 500)(scope, receive, identified_send)


def create_app(settings: Settings | None = None, *, runtime=None, registry=None, repository=None,
               replay_repository=None, replay_worker_enabled: bool = True) -> FastAPI:
    settings = settings or Settings.from_environment()
    if registry is None:
        from backend.app.registry import Registry
        registry = Registry(settings.root)
    if runtime is None:
        from backend.app.inference import Runtime
        runtime = Runtime(registry, root=settings.root, bundle_path=settings.bundle_path)
    repository = repository if repository is not None else PostgresRepository(settings)
    prediction_slots = threading.BoundedSemaphore(settings.max_concurrent_predictions)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = {"registry": False, "model": False, "database": False}
        for name, operation in (("registry", registry.startup), ("model", runtime.startup),
                                ("database", repository.initialize)):
            try:
                await run_in_threadpool(operation)
                app.state.ready[name] = True
                _log("dependency_ready", dependency=name)
            except Exception:
                _log("dependency_unavailable", dependency=name)
        app.state.replay_ready = False
        worker = None
        if all(app.state.ready.values()) and (replay_repository is not None or isinstance(repository, PostgresRepository)):
            from backend.app.replay import ReplayService, ReplayWorker
            from backend.app.replay_repository import PostgresReplayRepository
            store = replay_repository if replay_repository is not None else PostgresReplayRepository(settings)
            try:
                await run_in_threadpool(store.initialize)
                app.state.replay_service = ReplayService(registry, runtime, store)
                app.state.replay_ready = True
                if replay_worker_enabled:
                    worker = ReplayWorker(app.state.replay_service)
                    worker.start()
            except Exception:
                _log("dependency_unavailable", dependency="replay")
        try:
            yield
        finally:
            if worker is not None:
                await run_in_threadpool(worker.stop)

    app = FastAPI(title="OilWell AI diagnostic inference", version="diagnostic-1.0.0",
                  description="Historical binary diagnostic inference. The selected model is rejected for monitoring; "
                              "no event-family diagnosis or operational reliability is implied.", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.registry = registry
    app.state.repository = repository
    app.state.settings = settings
    app.add_middleware(RequestBoundary, max_bytes=settings.max_request_bytes)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        _log("request_rejected", request_id=request.state.request_id, error_code=exc.code)
        return _error(request.state.request_id, exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"location": [str(v)[:64] for v in error["loc"][:4]], "type": error["type"]}
                  for error in exc.errors()[:12]]
        return _error(request.state.request_id, "VALIDATION_ERROR", "Request failed validation", 422,
                      {"errors": fields})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return _error(request.state.request_id, "HTTP_ERROR", "Requested operation is unavailable", exc.status_code)

    errors = {status: {"model": ErrorResponse} for status in (400, 404, 409, 413, 422, 429, 500, 503)}

    def require(name: str) -> None:
        if not getattr(app.state, "ready", {}).get(name, False):
            raise ServiceError(f"{name.upper()}_UNAVAILABLE", f"{name.capitalize()} is unavailable", 503)

    @app.get("/health", response_model=Health, responses={503: {"model": Health}}, tags=["service"])
    def health(response: Response):
        readiness = getattr(app.state, "ready", {"registry": False, "model": False, "database": False}).copy()
        readiness["database"] = readiness["database"] and repository.health()
        replay_expected = replay_repository is not None or isinstance(repository, PostgresRepository)
        ok = all(readiness.values()) and (not replay_expected or getattr(app.state, "replay_ready", False))
        response.status_code = 200 if ok else 503
        return Health(status="ok" if ok else "degraded",
                      **{name: "ready" if ready else "unavailable" for name, ready in readiness.items()})

    @app.get("/wells", response_model=WellPage, responses=errors, tags=["telemetry"])
    def wells(cursor: Annotated[str | None, Query(max_length=256)] = None,
              limit: Annotated[int, Query(ge=1, le=100)] = 100):
        require("registry")
        after = decode_cursor(cursor, "wells")
        rows = sorted(registry.list_wells(), key=lambda row: row["well_id"])
        if after > len(rows):
            raise ServiceError("INVALID_CURSOR", "Cursor is outside the registered well page", 400)
        items = rows[after:after + limit]
        return {"items": items, "next_cursor": encode_cursor("wells", after + limit) if after + limit < len(rows) else None}

    @app.get("/wells/{id}/telemetry", response_model=TelemetryPage, responses=errors, tags=["telemetry"])
    def telemetry(id: str, source_instance_id: Annotated[str, Query(min_length=1, max_length=128)],
                  offset: Annotated[int, Query(ge=0)] = 0,
                  limit: Annotated[int, Query(ge=1, le=1000)] = 100,
                  sensors: Annotated[list[str] | None, Query(max_length=27)] = None):
        require("registry")
        return registry.telemetry(id, source_instance_id, offset, limit, sensors)

    @app.post("/predict", response_model=DiagnosticPrediction, responses=errors, tags=["inference"])
    def predict(request: Request, body: PredictRequest, response: Response,
                idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", idempotency_key):
            raise ServiceError("INVALID_IDEMPOTENCY_KEY", "Idempotency key contains unsupported characters", 422)
        require("registry"); require("model"); require("database")
        if not prediction_slots.acquire(blocking=False):
            raise ServiceError("INFERENCE_BUSY", "Prediction concurrency limit reached", 429)
        try:
            request_hash = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True,
                                                   separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            value, replayed = repository.get_or_create(
                idempotency_key, request_hash,
                lambda: runtime.predict(body, prediction_id=uuid4(), generated_at=datetime.now(timezone.utc)))
            response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
            _log("prediction_replayed" if replayed else "prediction_persisted",
                 request_id=request.state.request_id, prediction_id=str(value.prediction_id),
                 model_version=value.model_version, event_type=value.event_type, alert_status=value.alert_status)
            if value.alert_status == "alert" and not replayed:
                _log("diagnostic_alert_persisted", request_id=request.state.request_id,
                     prediction_id=str(value.prediction_id), model_version=value.model_version)
            return value
        finally:
            prediction_slots.release()

    @app.get("/alerts", response_model=AlertPage, responses=errors, tags=["alerts"])
    def alerts(cursor: Annotated[str | None, Query(max_length=256)] = None,
               limit: Annotated[int, Query(ge=1, le=1000)] = 100,
               well_id: Annotated[str | None, Query(max_length=128)] = None):
        require("database")
        return repository.list_alerts(cursor, limit, well_id)

    @app.get("/models/info", response_model=ModelInfo, responses=errors, tags=["inference"])
    def model_info():
        require("model")
        return runtime.info()

    from backend.app.replay import replay_router
    app.include_router(replay_router(app))
    from backend.app.dashboard import dashboard_router
    app.include_router(dashboard_router(app))
    return app


app = create_app()
