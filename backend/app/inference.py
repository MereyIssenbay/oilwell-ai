"""Adapter from verified historical windows to the frozen diagnostic model."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Lock
from uuid import UUID

import numpy as np
import pandas as pd

from backend.app.errors import ServiceError
from backend.app.registry import Registry, trusted_selection
from backend.app.schemas import DiagnosticPrediction, PredictRequest
from ml.predict import load_bundle


class Runtime:
    def __init__(self, registry: Registry, root: Path, bundle_path: Path | None = None):
        self.registry = registry
        self.root = Path(root).resolve()
        self.bundle_path = bundle_path
        self.predictor = None
        self._lock = Lock()

    def startup(self) -> None:
        selection = trusted_selection(self.root)
        approved = (self.root / selection["bundle_path"]).resolve()
        path = approved if self.bundle_path is None else Path(self.bundle_path)
        path = (self.root / path).resolve() if not path.is_absolute() else path.resolve()
        if path != approved or hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest() != selection["bundle_manifest_sha256"]:
            raise ValueError("Selected model integrity failure")
        predictor = load_bundle(path)
        if (predictor.metadata["model_version"] != selection["model_version"]
                or predictor.threshold != selection["threshold"] or predictor.kind != "logistic_regression"):
            raise ValueError("Selected model mismatch")
        self.predictor = predictor

    def info(self) -> dict:
        if self.predictor is None:
            raise ServiceError("MODEL_UNAVAILABLE", "Frozen model is unavailable", 503)
        p = self.predictor
        state = p.pipeline.state
        return {"schema_version": "diagnostic-1.0.0", "model_version": p.metadata["model_version"],
            "task": "binary_normal_vs_documented_undesirable", "supported_labels": ["normal", "undesirable_event"],
            "calibration": "none", "status": "diagnostic_only_rejected_for_monitoring",
            "diagnostic_only": True, "accepted_for_monitoring": False, "threshold": p.threshold,
            "comparison": "ge", "sensor_names": list(state.sensor_names),
            "window_rows": state.config.window_rows, "stride_rows": state.config.stride_rows,
            "preprocessor_fingerprint": state.fingerprint,
            "model_artifact_sha256": p.metadata["artifact_sha256"]["model.joblib"],
            "limitations": ["Selected model alarmed throughout normal diagnostic test time",
                "Binary detection only; event-family identity is unavailable", "Probabilities are uncalibrated",
                "EDA-exposed cohort; no protected generalization claim", "Historical source timezone is unverified",
                "Only registered train/validation real sources are served"]}

    def predict(self, request: PredictRequest, prediction_id: UUID, generated_at: datetime) -> DiagnosticPrediction:
        info = self.info()
        if request.model_version is not None and request.model_version != info["model_version"]:
            raise ServiceError("MODEL_VERSION_MISMATCH", "Requested model version is unavailable", 422)
        source, sensors = self.registry.window(request.source_instance_id, request.endpoint_position)
        if request.samples is not None:
            if len(request.samples) != len(sensors):
                raise ServiceError("SOURCE_WINDOW_MISMATCH", "Samples must match the registered source window", 422)
            for sample, (timestamp, values) in zip(request.samples, sensors.iterrows()):
                parsed = pd.Timestamp(sample.timestamp)
                if parsed.tzinfo is not None or parsed != timestamp or set(sample.sensors) != set(sensors.columns):
                    raise ServiceError("SOURCE_WINDOW_MISMATCH", "Samples must match the registered source window", 422)
                for name, expected in values.items():
                    actual = sample.sensors[name]
                    if (actual is None) != bool(pd.isna(expected)) or (actual is not None and float(actual) != float(expected)):
                        raise ServiceError("SOURCE_WINDOW_MISMATCH", "Samples must match the registered source window", 422)
        with self._lock:
            result = self.predictor.predict_instance(sensors)
        state = self.predictor.pipeline.state
        timestamp = sensors.index[-1].to_pydatetime().replace(tzinfo=timezone.utc)
        start = sensors.index[0].to_pydatetime().replace(tzinfo=timezone.utc)
        reason = "insufficient_history" if result.empty else result.iloc[-1].abstention_reason
        unavailable = reason is not None
        score = None if unavailable else float(result.iloc[-1].score)
        positive = False if unavailable else bool(result.iloc[-1].predicted)
        evidence = []
        for sensor in state.sensor_names:
            values = sensors[sensor].to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            evidence.append({"evidence_id": f"{prediction_id}:{sensor}:mean", "sensor_name": sensor,
                "statistic": "mean", "value": float(finite.mean()) if len(finite) else None,
                "unit": self.registry.units[sensor], "window_start": start, "window_end": timestamp,
                "missing_fraction": float(1 - len(finite) / len(values)), "method": "observed_summary"})
        window_payload = [{"timestamp": t.isoformat(), "sensors": {
            name: None if pd.isna(v) else float(v) for name, v in row.items()}} for t, row in sensors.iterrows()]
        window_hash = hashlib.sha256(json.dumps(window_payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        missing = float(sensors.isna().to_numpy().mean())
        data = {"schema_version": "diagnostic-1.0.0", "prediction_id": prediction_id,
            "timestamp": timestamp, "well_id": source.well_id,
            "event_type": "unknown" if unavailable else "undesirable_event" if positive else "normal",
            "confidence": None if unavailable else score if positive else 1.0 - score,
            "confidence_kind": "unavailable" if unavailable else "raw_probability", "abnormal_score": score,
            "threshold": self.predictor.threshold, "model_version": info["model_version"],
            "feature_spec_version": state.config.version, "policy_version": "phase5-threshold-ge-diagnostic-v1",
            "diagnostic_only": True, "accepted_for_monitoring": False, "sensor_evidence": evidence,
            "alert_status": "insufficient_data" if unavailable else "alert" if positive else "normal",
            "abstention_reason": reason, "window": {"start": start, "end": timestamp,
                "sample_count": len(sensors), "expected_sample_count": state.config.window_rows},
            "quality": {"status": "invalid" if unavailable else "degraded" if missing else "valid",
                "missing_fraction": missing, "warnings": ["diagnostic_model_rejected_for_monitoring", "uncalibrated_probability", "source_timezone_unverified"]},
            "provenance": {"dataset_name": "3W", "dataset_version": source.dataset_version,
                "dataset_revision": source.dataset_revision, "source_instance_id": source.instance_id,
                "source_sha256": source.sha256, "source_kind": "real", "well_identity_kind": "anonymized_well",
                "source_timestamp": sensors.index[-1].isoformat(), "time_basis": "source_naive_assumed_utc",
                "preprocessor_fingerprint": state.fingerprint, "model_artifact_sha256": info["model_artifact_sha256"],
                "request_window_sha256": window_hash},
            "execution": {"mode": "historical_inference", "generated_at": generated_at}}
        return DiagnosticPrediction.model_validate(data)
