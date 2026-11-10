"""Integrity-checked binary inference with frozen causal preprocessing.

This internal result is not the canonical event-family API prediction. Joblib
is executable serialization: load only locally generated trusted bundles.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from ml.data_pipeline import CausalFeaturePipeline
from ml.features import feature_names, summarize_windows


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def estimator_scores(estimator: Any, kind: str, features: pd.DataFrame) -> np.ndarray:
    """Scores oriented toward abnormality; Isolation Forest is not probability."""
    if not len(features):
        return np.empty(0, dtype=float)
    with threadpool_limits(limits=1):
        if kind == "isolation_forest":
            values = -estimator.score_samples(features)
        elif kind in {"logistic_regression", "xgboost", "catboost"}:
            classes = list(estimator.classes_)
            if set(classes) != {0, 1}:
                raise ValueError("Binary normal/abnormal estimator required")
            values = estimator.predict_proba(features)[:, classes.index(1)]
        else:
            raise ValueError("Unknown estimator kind")
    values = np.asarray(values, dtype=float)
    if values.shape != (len(features),) or not np.isfinite(values).all():
        raise ValueError("Invalid estimator scores")
    if kind != "isolation_forest" and ((values < 0) | (values > 1)).any():
        raise ValueError("Probability scores outside [0,1]")
    return values


@dataclass(frozen=True)
class Predictor:
    estimator: Any
    kind: str
    threshold: float
    pipeline: CausalFeaturePipeline
    metadata: dict[str, Any]

    def predict_features(self, features: pd.DataFrame, evidence_mask: pd.Series) -> pd.DataFrame:
        """Internal normalized-input API; callers must supply trusted quality-derived evidence.

        Raw observations cannot be reconstructed from imputed features. Use
        predict_instance for the public sensor-input boundary, which derives
        evidence counts directly rather than trusting an external mask.
        """
        state = self.pipeline.state
        if state is None or tuple(features.columns) != state.retained_features:
            raise ValueError("Exact frozen feature names/order required")
        if not features.index.is_unique or not features.index.equals(evidence_mask.index):
            raise ValueError("Unique aligned feature/evidence rows required")
        if evidence_mask.dtype != bool:
            raise ValueError("Strict Boolean input-evidence mask required")
        if not np.isfinite(features.to_numpy(dtype=float)).all():
            raise ValueError("Normalized features must be finite")
        if not np.isfinite(self.threshold):
            raise ValueError("Finite frozen threshold required")
        output = pd.DataFrame(index=features.index)
        output["has_input"] = evidence_mask
        output["score"] = np.nan
        output["predicted"] = pd.Series(pd.NA, index=features.index, dtype="Int8")
        scores = estimator_scores(self.estimator, self.kind, features.loc[evidence_mask])
        output.loc[evidence_mask, "score"] = scores
        output.loc[evidence_mask, "predicted"] = (scores >= self.threshold).astype(np.int8)
        output["abstention_reason"] = np.where(evidence_mask, None, "missing_required_sensors")
        output["model_version"] = self.metadata["model_version"]
        output["score_kind"] = "anomaly_score" if self.kind == "isolation_forest" else "uncalibrated_probability"
        return output

    def predict_instance(self, sensors: pd.DataFrame) -> pd.DataFrame:
        """One ordered source instance, exact sensors only, no labels/identifiers.

        Gaps reset history and stride. Short segments emit no windows; callers
        must represent insufficient history explicitly rather than normality.
        Timestamps retain their input time basis and never enter model features.
        """
        state = self.pipeline.state
        if state is None:
            raise ValueError("Frozen preprocessing required")
        if (not sensors.columns.is_unique or set(sensors.columns) != set(state.sensor_names)
                or not isinstance(sensors.index, pd.DatetimeIndex)
                or sensors.index.hasnans or not sensors.index.is_unique
                or not sensors.index.is_monotonic_increasing):
            raise ValueError("Exact sensor-only schema and ordered unique timestamps required")
        if any(not pd.api.types.is_numeric_dtype(sensors[c]) or pd.api.types.is_bool_dtype(sensors[c])
               for c in sensors):
            raise ValueError("Sensors must be numeric, excluding Boolean values")
        values = sensors.loc[:, state.sensor_names].to_numpy(dtype=float, na_value=np.nan)
        if np.isinf(values).any():
            raise ValueError("Infinite sensor values are invalid")
        cadence_ns = round(state.config.cadence_seconds * 1e9)
        differences = np.diff(sensors.index.as_unit("ns").asi8)
        if (differences < cadence_ns).any():
            raise ValueError("Finer-than-configured cadence is unsupported")
        cuts = np.r_[0, np.flatnonzero(differences != cadence_ns) + 1, len(sensors)]
        blocks, counts, endpoints = [], [], []
        for start, stop in zip(cuts, cuts[1:]):
            positions = np.arange(start + state.config.window_rows - 1, stop, state.config.stride_rows)
            if not len(positions):
                continue
            block, observed = summarize_windows(values, positions, state.config.window_rows,
                                                state.config.cadence_seconds)
            blocks.append(block); counts.append(observed); endpoints.extend(positions.tolist())
        index = pd.DatetimeIndex(sensors.index[endpoints], name="timestamp")
        raw_features = pd.DataFrame(np.concatenate(blocks) if blocks else np.empty((0, len(state.input_feature_names))),
                                    index=index, columns=feature_names(state.sensor_names))
        retained = raw_features.loc[:, state.retained_features].to_numpy(dtype=float)
        normalized = (np.where(np.isnan(retained), state.medians, retained) - state.means) / state.scales
        features = pd.DataFrame(normalized, index=index, columns=state.retained_features)
        observed = np.concatenate(counts) if counts else np.empty((0, len(state.sensor_names)))
        retained_sensors = {name.rsplit("__", 1)[0] for name in state.retained_features}
        included = [i for i, sensor in enumerate(state.sensor_names) if sensor in retained_sensors]
        evidence = pd.Series(observed[:, included].sum(axis=1) > 0, index=index)
        output = self.predict_features(features, evidence)
        output["window_start"] = sensors.index[np.asarray(endpoints, dtype=int) - state.config.window_rows + 1]
        output["endpoint_position"] = np.asarray(endpoints, dtype=int)
        output.attrs["empty_reason"] = "insufficient_history" if output.empty else None
        return output


def load_bundle(directory: Path) -> Predictor:
    """Verify trusted local bytes before deserialization; reject drifted state."""
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0.0" or manifest.get("task") != "binary_normal_vs_documented_undesirable":
        raise ValueError("Unsupported inference bundle")
    if not manifest.get("model_version") or not np.isfinite(manifest.get("threshold", np.nan)):
        raise ValueError("Versioned finite threshold required")
    dependencies = manifest.get("model_dependency_versions", {})
    if not dependencies:
        raise ValueError("Pinned model runtime dependencies required")
    for package, version in dependencies.items():
        if importlib.metadata.version(package) != version:
            raise ValueError(f"Model runtime dependency mismatch: {package}")
    for name in ("model.joblib", "preprocessor.json", "split.json"):
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or file_hash(path) != manifest["artifact_sha256"][name]:
            raise ValueError(f"Inference artifact hash mismatch: {name}")
    if file_hash(Path(__file__)) != manifest["inference_code_sha256"]:
        raise ValueError("Inference implementation differs from bundle")
    pipeline = CausalFeaturePipeline.load(directory / "preprocessor.json")
    state = pipeline.state
    if state is None or state.fingerprint != manifest["preprocessor_fingerprint"]:
        raise ValueError("Preprocessor fingerprint mismatch")
    if (tuple(manifest["feature_names"]) != state.retained_features
            or manifest["split_fingerprint"] != state.split_manifest.fingerprint
            or manifest.get("comparison") != "ge" or manifest.get("calibration") != "none"):
        raise ValueError("Inference schema/policy differs from frozen state")
    expected_kind = "anomaly_score" if manifest["estimator_kind"] == "isolation_forest" else "uncalibrated_probability"
    if manifest.get("score_kind") != expected_kind:
        raise ValueError("Inconsistent score meaning")
    split = json.loads((directory / "split.json").read_text())
    if split != state.split_manifest.model_dump(mode="json"):
        raise ValueError("Frozen split differs from preprocessing state")
    payload = joblib.load(directory / "model.joblib")
    if (payload["kind"] != manifest["estimator_kind"] or payload["threshold"] != manifest["threshold"]
            or payload["fit_window_ids_sha256"] != manifest["fit_window_ids_sha256"]):
        raise ValueError("Model payload and metadata disagree")
    return Predictor(payload["estimator"], payload["kind"], float(payload["threshold"]), pipeline, manifest)
