"""Bounded validation selection and a separately released one-shot test audit."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import inspect
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import shutil
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss
from threadpoolctl import threadpool_limits

from ml.data_pipeline import CausalFeaturePipeline
from ml.data_pipeline.models import VALID_CLASSES, fingerprint
from ml.evaluate import binary_metrics, evaluate_predictions, failure_examples
from ml.predict import Predictor, estimator_scores, load_bundle
from ml.train_baseline import (BaselineData, FROZEN_SPLIT, PartitionData, ROOT, SEED,
                               _environment, _load_local_models, _verify_requirement_pins,
                               _write_json, load_training_data, load_validation_raw, sha256)

MAX_OCCUPANCY = 0.05
QUANTILE_POINTS = 201
PROTOCOL = "reports/experiments/PROTOCOL.md"
REPORTS = "reports/experiments"


def candidate_specs() -> list[dict[str, Any]]:
    specs = []
    for kind in ("catboost", "xgboost"):
        for depth in (3, 6):
            for rate in (.05, .1):
                common = {"depth": depth, "learning_rate": rate, "trees": 200,
                          "positive_weight": 2, "seed": SEED, "threads": 1}
                specs.append({"candidate_id": f"{kind}_d{depth}_lr{rate:g}", "kind": kind, "parameters": common})
    return specs


def fit_candidate(train: PartitionData, spec: dict[str, Any]) -> Any:
    train.validate()
    if train.partition != "train":
        raise ValueError("Candidate fitting requires train only")
    if spec not in candidate_specs():
        raise ValueError("Candidate outside bounded frozen search")
    x = train.features.loc[train.eligible]
    y = train.targets.loc[train.eligible, "event_family"].gt(0).astype(int)
    if set(y.unique()) != {0, 1}:
        raise ValueError("Both binary training classes required")
    params = spec["parameters"]
    if spec["kind"] == "xgboost":
        from xgboost import XGBClassifier
        estimator = XGBClassifier(n_estimators=params["trees"], max_depth=params["depth"],
                                  learning_rate=params["learning_rate"], scale_pos_weight=2,
                                  objective="binary:logistic", eval_metric="logloss", tree_method="hist",
                                  subsample=1.0, colsample_bytree=1.0, reg_lambda=1.0,
                                  random_state=SEED, n_jobs=1, verbosity=0)
    else:
        from catboost import CatBoostClassifier
        estimator = CatBoostClassifier(iterations=params["trees"], depth=params["depth"],
                                        learning_rate=params["learning_rate"], class_weights=[1, 2],
                                        loss_function="Logloss", random_seed=SEED, thread_count=1,
                                        l2_leaf_reg=3.0, bootstrap_type="No", random_strength=0,
                                        allow_writing_files=False, verbose=False)
    with threadpool_limits(limits=1):
        estimator.fit(x, y)
    return estimator


def choose_threshold(scores: np.ndarray, y: np.ndarray, normal_seconds: np.ndarray,
                     eligible: np.ndarray, max_occupancy: float = MAX_OCCUPANCY) -> dict[str, Any]:
    """Bounded quantile search, maximizing recall under exact normal exposure cap."""
    scores, y, weights = (np.asarray(v, dtype=float) for v in (scores, y, normal_seconds))
    eligible = np.asarray(eligible)
    if (scores.ndim != 1 or y.shape != scores.shape or weights.shape != scores.shape
            or eligible.shape != scores.shape or eligible.dtype != bool
            or not len(scores) or np.isinf(scores).any() or np.isinf(y).any()
            or not np.isfinite(weights).all() or (weights < 0).any()
            or not np.isfinite(max_occupancy) or not 0 <= max_occupancy <= 1):
        raise ValueError("Invalid threshold inputs")
    available = np.isfinite(scores)
    if (not np.array_equal(eligible, available & np.isfinite(y))
            or not np.isin(y[np.isfinite(y)], [0, 1]).all()
            or (weights[~available] != 0).any() or weights.sum() <= 0
            or not np.any(eligible & (y == 1))):
        raise ValueError("Eligibility/labels/exposure do not support threshold selection")
    finite = scores[available]
    upper = np.nextafter(finite.max(), np.inf)
    lower = np.nextafter(finite.min(), -np.inf)
    if not np.isfinite([lower, upper]).all():
        raise ValueError("Cannot construct finite boundary thresholds")
    grid = np.unique(np.r_[lower, np.quantile(finite, np.linspace(0, 1, QUANTILE_POINTS)), upper])
    rows = []
    for threshold in grid:
        positive = available & (scores >= threshold)
        truth = y[eligible].astype(int)
        predicted = positive[eligible]
        tp = int(((truth == 1) & predicted).sum()); fn = int(((truth == 1) & ~predicted).sum())
        fp = int(((truth == 0) & predicted).sum()); tn = int(((truth == 0) & ~predicted).sum())
        occupancy = float(weights[positive].sum() / weights.sum())
        rows.append({"threshold": float(threshold), "recall": tp / (tp + fn),
                     "normal_alarm_occupancy_fraction": occupancy,
                     "normal_alarm_seconds": float(weights[positive].sum()),
                     "normal_seconds": float(weights.sum()), "feasible": occupancy <= max_occupancy,
                     "tn": tn, "fp": fp, "fn": fn, "tp": tp})
    feasible = [row for row in rows if row["feasible"]]
    best = min(feasible, key=lambda row: (-row["recall"], row["normal_alarm_occupancy_fraction"], -row["threshold"]))
    return {"selected": best, "grid": rows, "max_occupancy": max_occupancy,
            "criterion": "maximum recall, then lower normal occupancy, then higher threshold"}


def rank_candidates(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records or len({row["candidate_id"] for row in records}) != len(records):
        raise ValueError("Unique candidate records required")
    for row in records:
        if (not all(np.isfinite(row[k]) for k in ("recall", "average_precision", "normal_alarm_occupancy_fraction"))
                or not 0 <= row["normal_alarm_occupancy_fraction"] <= MAX_OCCUPANCY
                or not 0 <= row["recall"] <= 1 or not 0 <= row["average_precision"] <= 1):
            raise ValueError("Candidate lacks feasible finite validation metrics")
    return min(records, key=lambda row: (-row["recall"], -row["average_precision"],
                                        row["normal_alarm_occupancy_fraction"], row["candidate_id"]))


def normal_exposure_weights(partition: PartitionData, raw: dict[str, pd.DataFrame],
                            stride_rows: int, cadence_seconds: float) -> pd.Series:
    """Attribute each decision's normal seconds, without using labels as inputs."""
    partition.validate()
    if (partition.partition != "validation" or type(stride_rows) is not int or stride_rows < 1
            or isinstance(cadence_seconds, bool) or not np.isfinite(cadence_seconds) or cadence_seconds <= 0):
        raise ValueError("Threshold exposure requires validation and positive stride")
    weights = pd.Series(0.0, index=partition.features.index)
    for source, rows in partition.metadata.groupby("instance_id", sort=True):
        frame = raw[source]
        if (not isinstance(frame.index, pd.DatetimeIndex) or not frame.index.is_unique
                or not frame.index.is_monotonic_increasing or frame.index.hasnans
                or "class" not in frame or not frame["class"].dropna().isin(VALID_CLASSES).all()
                or (np.diff(frame.index.as_unit("ns").asi8) < round(cadence_seconds * 1e9)).any()):
            raise ValueError("Ordered original timestamps required")
        rows = rows.sort_values("timestamp", kind="stable")
        positions = rows.endpoint_position.to_numpy(dtype=int)
        for i, (window_id, row) in enumerate(rows.iterrows()):
            start = int(row.endpoint_position)
            if start < 0 or start >= len(frame) or frame.index[start] != row.timestamp:
                raise ValueError("Exposure endpoint mismatch")
            actual, expected = frame["class"].iloc[start], partition.targets.loc[window_id, "raw_class"]
            if not ((pd.isna(actual) and pd.isna(expected)) or (pd.notna(actual) and pd.notna(expected) and actual == expected)):
                raise ValueError("Exposure target differs from original endpoint")
            if not partition.evidence_mask.loc[window_id]:
                continue
            stop = min(start + stride_rows, len(frame))
            if i + 1 < len(positions):
                stop = min(stop, positions[i + 1])
            for j in range(start + 1, stop):
                if (frame.index[j] - frame.index[j - 1]).total_seconds() != cadence_seconds:
                    stop = j
                    break
            weights.loc[window_id] = float(frame["class"].iloc[start:stop].eq(0).fillna(False).sum() * cadence_seconds)
    return weights


@dataclass(frozen=True)
class ExperimentalPartition:
    features: pd.DataFrame
    targets: pd.DataFrame
    metadata: pd.DataFrame
    quality: pd.DataFrame
    evidence_mask: pd.Series
    partition: str

    @property
    def eligible(self) -> pd.Series:
        return self.evidence_mask & self.targets.event_family.notna()

    def validate(self) -> None:
        if self.partition not in {"validation", "test"} or not self.metadata.partition.eq(self.partition).all():
            raise ValueError("Actual evaluation partition required")
        # The unchanged Phase 4 validator is deliberately validation-only.
        # This private copy reuses its feature/target/evidence invariants; it is
        # never persisted and cannot be passed to estimator fitting.
        alias = self.metadata.assign(partition="validation")
        PartitionData(self.features, self.targets, alias, self.quality, self.evidence_mask, "validation").validate()


def prediction_frame(partition: PartitionData | ExperimentalPartition, scores: np.ndarray,
                     threshold: float, candidate_id: str) -> pd.DataFrame:
    partition.validate()
    if partition.partition not in {"validation", "test"}:
        raise ValueError("Predictions require a holdout partition")
    scores = np.asarray(scores, dtype=float)
    if scores.shape != (int(partition.evidence_mask.sum()),) or not np.isfinite(scores).all() or not np.isfinite(threshold):
        raise ValueError("Scores must cover every available endpoint")
    rows = partition.metadata.copy()
    rows["window_id"] = rows.index
    for column in ("raw_class", "event_family", "phase"):
        rows[column] = partition.targets[column]
    rows["model"] = candidate_id
    rows["has_input"] = partition.evidence_mask
    rows["eligible"] = partition.eligible
    rows["score"] = np.nan
    rows["predicted"] = pd.Series(pd.NA, index=rows.index, dtype="Int8")
    rows.loc[partition.evidence_mask, "score"] = scores
    rows.loc[partition.evidence_mask, "predicted"] = (scores >= threshold).astype(np.int8)
    return rows.reset_index(drop=True)


def evaluate_partition(predictions: pd.DataFrame, train_families: set[int], raw: dict[str, pd.DataFrame],
                       partition: str, stride_rows: int = 10, cadence_seconds: float = 1.0) -> dict[str, Any]:
    if partition not in {"validation", "test"} or not predictions.partition.eq(partition).all():
        raise ValueError("Mixed or incorrect evaluation partition")
    result = evaluate_predictions(predictions.assign(partition="validation"), train_families, raw,
                                  stride_rows, cadence_seconds)
    result["partition"] = partition
    for value in result["models"].values():
        value[partition] = value.pop("validation") if partition == "test" else value["validation"]
        if partition == "test":
            value["coverage"]["all_test_endpoints"] = value["coverage"].pop("all_validation_endpoints")
            for row in value["by_family"]:
                if row["status"] == "no_validation_support":
                    row["status"] = "no_test_support"
            for row in value["by_origin"].values():
                if row["reason"]:
                    row["reason"] = "origin excluded from frozen real-only test split"
    return result


def probability_quality(y: np.ndarray, scores: np.ndarray, kind: str) -> dict[str, Any]:
    if kind == "isolation_forest":
        return {"brier": None, "log_loss": None, "reason": "anomaly scores are not probabilities"}
    return {"brier": float(brier_score_loss(y, scores)), "log_loss": float(log_loss(y, scores, labels=[0, 1])),
            "calibrated": False, "reason": "insufficient independent calibration groups; calibration deferred"}


def benchmark(estimator: Any, kind: str, features: pd.DataFrame) -> dict[str, Any]:
    if features.empty:
        raise ValueError("Latency measurement requires available validation features")
    results = {}
    for name, frame, repetitions in (("single", features.iloc[:1], 50), ("batch", features.iloc[:1024], 10)):
        for _ in range(5):
            estimator_scores(estimator, kind, frame)
        timings = []
        for _ in range(repetitions):
            start = time.perf_counter_ns()
            estimator_scores(estimator, kind, frame)
            timings.append((time.perf_counter_ns() - start) / 1e6)
        results[name] = {"rows": len(frame), "warmups": 5, "repetitions": repetitions,
                         "p50_ms": float(np.percentile(timings, 50)), "p95_ms": float(np.percentile(timings, 95)),
                         "rows_per_second_at_p50": float(len(frame) * 1000 / np.percentile(timings, 50)),
                         "measurements_ms": timings}
    results["scope"] = "feature-to-score estimator wrapper including validation and threadpool-limit context; excludes preprocessing/load"
    return results


def benchmark_raw(predictor: Predictor, root: Path, data: BaselineData) -> dict[str, Any]:
    source_id = sorted(data.validation.metadata.instance_id.unique())[0]
    source = data.split.assignment_for(source_id).source
    path = root / "data/raw/3w" / source.dataset_version / source.dataset_revision / source.source_path
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != source.sha256:
        raise ValueError("Raw latency source hash changed")
    sensors = pd.read_parquet(BytesIO(payload), columns=list(data.state.sensor_names)).iloc[:data.state.config.window_rows]
    expected_ids = data.validation.metadata.index[(data.validation.metadata.instance_id == source_id)
                                                 & (data.validation.metadata.endpoint_position == len(sensors) - 1)]
    actual = predictor.predict_instance(sensors)
    expected = predictor.predict_features(data.validation.features.loc[expected_ids], data.validation.evidence_mask.loc[expected_ids])
    if len(actual) != 1 or not np.array_equal(actual.score, expected.score, equal_nan=True):
        raise ValueError("Raw causal inference differs from frozen validation features")
    for _ in range(5):
        predictor.predict_instance(sensors)
    timings = []
    for _ in range(50):
        start = time.perf_counter_ns(); predictor.predict_instance(sensors)
        timings.append((time.perf_counter_ns() - start) / 1e6)
    return {"scope": "sensor-only validation window to binary result; includes features/imputation/scaling, excludes disk/model load",
            "source_instance_id": source_id, "source_sha256": source.sha256, "sensor_rows": len(sensors),
            "output_windows": 1, "warmups": 5, "repetitions": 50, "raw_vs_frozen_scores_exact": True,
            "p50_ms": float(np.percentile(timings, 50)), "p95_ms": float(np.percentile(timings, 95)),
            "measurements_ms": timings}


def _code_hashes(root: Path) -> dict[str, str]:
    paths = ["ml/training/phase5.py", "ml/predict.py", "ml/train_baseline.py", "ml/evaluate.py",
             "requirements-models.txt", "requirements-baseline.txt", "requirements-pipeline.txt", "requirements-data.txt"]
    return {name: sha256(root / name) for name in paths}


def _json_parameters(value: Any) -> Any:
    """Preserve nonfinite library-default sentinels as named strings, never JSON NaN."""
    if isinstance(value, dict):
        return {str(key): _json_parameters(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_parameters(item) for item in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return "NaN" if np.isnan(value) else "+Infinity" if value > 0 else "-Infinity"
    if isinstance(value, np.generic):
        return value.item()
    return value


def _fit_checkpoint(root: Path, data: BaselineData, spec: dict[str, Any], protocol_hash: str) -> tuple[Any, float]:
    """Persist each actual candidate fit immediately, permitting report/code repairs without refitting."""
    identity = {"protocol_sha256": protocol_hash, "data_provenance": data.provenance, "spec": spec,
                "fit_function_sha256": hashlib.sha256(inspect.getsource(fit_candidate).encode()).hexdigest(),
                "dependencies": {name: importlib.metadata.version(name) for name in ("xgboost", "catboost", "numpy", "pandas", "scikit-learn", "joblib")}}
    directory = root / "ml/artifacts/phase5/fit_checkpoints" / fingerprint(identity)
    directory.mkdir(parents=True, exist_ok=True)
    budget_path = root / "ml/artifacts/phase5/fit_budget.json"
    budget = json.loads(budget_path.read_text()) if budget_path.exists() else {}
    candidate_id = spec["candidate_id"]
    if candidate_id in budget and budget[candidate_id] != fingerprint(identity):
        raise ValueError("Fixed actual-fit budget forbids refitting a candidate under changed fit identity")
    if candidate_id not in budget:
        if len(budget) >= 8:
            raise ValueError("Actual boosted-fit budget exhausted")
        budget[candidate_id] = fingerprint(identity)
        _write_json(budget_path, budget)
    complete = directory / "complete.json"
    if complete.exists():
        metadata = json.loads(complete.read_text())
        if metadata["identity"] != identity or sha256(directory / "model.joblib") != metadata["model_sha256"]:
            raise ValueError("Fit checkpoint changed")
        return joblib.load(directory / "model.joblib"), metadata["fit_seconds"]
    started = directory / "started.json"
    with started.open("x", encoding="utf-8") as stream:
        json.dump({"candidate_id": spec["candidate_id"], "identity": identity}, stream, sort_keys=True)
        stream.write("\n")
    start = time.perf_counter()
    estimator = fit_candidate(data.train, spec)
    seconds = time.perf_counter() - start
    joblib.dump(estimator, directory / "model.joblib", compress=3)
    _write_json(complete, {"identity": identity, "model_sha256": sha256(directory / "model.joblib"), "fit_seconds": seconds})
    return estimator, seconds


def _baseline_models(root: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    manifest_path = root / "reports/baseline/experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = manifest["artifacts"]["models"]
    models = _load_local_models(root / entry["path"], entry["sha256"])
    predictions = manifest["artifacts"]["predictions"]
    if sha256(root / predictions["path"]) != predictions["sha256"]:
        raise ValueError("Frozen baseline predictions changed")
    return models, pd.read_parquet(root / predictions["path"])


def _aligned_saved_scores(frame: pd.DataFrame, partition: PartitionData, name: str) -> np.ndarray:
    rows = frame.loc[frame.model.eq(name)].set_index("window_id")
    if set(rows.index) != set(partition.features.index) or not rows.index.is_unique:
        raise ValueError("Baseline validation cohort mismatch")
    rows = rows.loc[partition.features.index]
    if not rows.partition.eq("validation").all() or not np.array_equal(rows.eligible, partition.eligible):
        raise ValueError("Baseline eligibility/partition mismatch")
    return rows.loc[partition.evidence_mask, "score"].to_numpy(dtype=float)


def _bundle(root: Path, directory: Path, data: BaselineData, selected: dict[str, Any], estimator: Any,
            identity: dict[str, Any], fit_ids: tuple[str, ...]) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    model_version = "oilwell-binary-phase5-" + fingerprint(identity)[:20]
    payload = {"estimator": estimator, "kind": selected["kind"], "threshold": selected["threshold"],
               "fit_window_ids_sha256": fingerprint(fit_ids), "fit_window_ids": fit_ids}
    joblib.dump(payload, directory / "model.joblib", compress=3)
    shutil.copyfile(root / data.provenance["artifacts"]["preprocessor"]["path"], directory / "preprocessor.json")
    shutil.copyfile(root / "data/manifests/development_split.json", directory / "split.json")
    manifest = {"schema_version": "1.0.0", "task": "binary_normal_vs_documented_undesirable",
                "model_version": model_version, "candidate_id": selected["candidate_id"],
                "estimator_kind": selected["kind"], "threshold": selected["threshold"], "comparison": "ge",
                "calibration": "none", "score_kind": "anomaly_score" if selected["kind"] == "isolation_forest" else "uncalibrated_probability",
                "preprocessor_fingerprint": data.state.fingerprint, "split_fingerprint": data.split.fingerprint,
                "fit_window_ids_sha256": fingerprint(fit_ids), "fit_windows": len(fit_ids),
                "feature_names": list(data.state.retained_features), "identity": identity,
                "inference_code_sha256": sha256(root / "ml/predict.py"),
                "model_dependency_versions": {name: importlib.metadata.version(name) for name in ("scikit-learn", "xgboost", "catboost", "joblib", "numpy", "pandas", "scipy", "threadpoolctl")},
                "artifact_sha256": {name: sha256(directory / name) for name in ("model.joblib", "preprocessor.json", "split.json")},
                "accepted_for_monitoring": False, "canonical_event_family_prediction": False}
    _write_json(directory / "manifest.json", manifest)
    return manifest


def run_search(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    report = root / REPORTS
    if (report / "test_access.json").exists():
        raise ValueError("Test access has begun; selection/search is permanently closed for this phase")
    protocol_hash = sha256(root / PROTOCOL)
    _verify_requirement_pins(root / "requirements-models.txt")
    data = load_training_data(root)
    if data.split.fingerprint != FROZEN_SPLIT:
        raise ValueError("Phase 5 requires unchanged frozen diagnostic split")
    raw = load_validation_raw(root, data)
    weights = normal_exposure_weights(data.validation, raw, data.state.config.stride_rows, data.state.config.cadence_seconds)
    baseline, baseline_predictions = _baseline_models(root)
    fit_ids = tuple(data.train.features.index[data.train.eligible].astype(str))
    train_families = set(int(v) for v in data.train.targets.loc[data.train.eligible, "event_family"])
    identity = {"protocol_sha256": protocol_hash, "code_sha256": _code_hashes(root), "seed": SEED,
                "provenance": data.provenance, "environment": _environment(root),
                "hardware": {"processor": platform.processor(), "machine": platform.machine(), "logical_cpu_count": os.cpu_count()},
                "candidate_specs": candidate_specs(), "calibration": "deferred", "max_normal_occupancy": MAX_OCCUPANCY}
    run_id = fingerprint(identity)[:20]
    artifact = root / "ml/artifacts/phase5" / run_id
    run = root / "ml/runs/phase5" / run_id
    report.mkdir(parents=True, exist_ok=True); run.mkdir(parents=True, exist_ok=True)
    available = data.validation.evidence_mask
    y = data.validation.targets.event_family.gt(0).astype("Float64").to_numpy(dtype=float, na_value=np.nan)
    y[data.validation.targets.event_family.isna()] = np.nan
    records, predictions, grids, fitted, fit_times = [], [], [], {}, {}
    specs = candidate_specs() + [{"candidate_id": name + "_retuned", "kind": name, "parameters": baseline[name].estimator.get_params()}
                                  for name in ("logistic_regression", "isolation_forest")]
    for spec in specs:
        name, kind = spec["candidate_id"], spec["kind"]
        baseline_score_max_absolute_difference = None
        if name.endswith("_retuned"):
            estimator = baseline[kind].estimator
            values = _aligned_saved_scores(baseline_predictions, data.validation, kind)
            recomputed = estimator_scores(estimator, kind, data.validation.features.loc[available])
            baseline_score_max_absolute_difference = float(np.max(np.abs(values - recomputed)))
            if not np.allclose(values, recomputed, rtol=0, atol=1e-14):
                raise ValueError("Saved baseline model does not reproduce its validation scores")
            # Phase 4 inference did not wrap BLAS thread limits. Reuse the
            # same fitted estimator under the now-fixed inference context;
            # preserve originals separately and disclose sub-ulp differences.
            values = recomputed
            fit_seconds = None
        else:
            estimator, fit_seconds = _fit_checkpoint(root, data, spec, protocol_hash)
            values = estimator_scores(estimator, kind, data.validation.features.loc[available])
        fitted[name] = estimator; fit_times[name] = fit_seconds
        all_scores = np.full(len(available), np.nan); all_scores[available.to_numpy()] = values
        choice = choose_threshold(all_scores, y, weights.to_numpy(), data.validation.eligible.to_numpy())
        threshold = choice["selected"]["threshold"]
        rows = prediction_frame(data.validation, values, threshold, name)
        metrics = binary_metrics(y[data.validation.eligible].astype(int),
                                 rows.loc[rows.eligible, "predicted"].to_numpy(dtype=int), all_scores[data.validation.eligible])
        record = {"candidate_id": name, "kind": kind, "threshold": threshold,
                  "recall": metrics["recall"], "average_precision": metrics["average_precision"],
                  "normal_alarm_occupancy_fraction": choice["selected"]["normal_alarm_occupancy_fraction"],
                  "parameters": _json_parameters(spec["parameters"]), "fit_seconds": fit_seconds,
                  "resolved_parameters": _json_parameters(estimator.get_all_params() if kind == "catboost" else estimator.get_params()),
                  "baseline_score_max_absolute_difference": baseline_score_max_absolute_difference,
                  "baseline_reload_absolute_tolerance": 1e-14 if name.endswith("_retuned") else None,
                  "latency": benchmark(estimator, kind, data.validation.features.loc[available]),
                  "probability_quality": probability_quality(y[data.validation.eligible].astype(int), all_scores[data.validation.eligible], kind)}
        records.append(record); predictions.append(rows)
        grids.extend({"candidate_id": name, **row} for row in choice["grid"])
    selected = rank_candidates(records)
    combined = pd.concat(predictions, ignore_index=True)
    metrics = evaluate_partition(combined, train_families, raw, "validation", data.state.config.stride_rows, data.state.config.cadence_seconds)
    for row in records:
        actual = metrics["models"][row["candidate_id"]]["false_alerts"]["normal_alarm_occupancy_fraction"]
        if actual != row["normal_alarm_occupancy_fraction"]:
            raise ValueError("Threshold weights disagree with exact temporal accounting")
    chosen_fit_ids = baseline["isolation_forest"].fit_window_ids if selected["kind"] == "isolation_forest" else fit_ids
    manifest = _bundle(root, artifact, data, selected, fitted[selected["candidate_id"]], identity, chosen_fit_ids)
    reloaded = load_bundle(artifact)
    raw_latency = benchmark_raw(reloaded, root, data)
    replay = reloaded.predict_features(data.validation.features, data.validation.evidence_mask)
    expected = combined.loc[combined.model.eq(selected["candidate_id"])].set_index("window_id").loc[data.validation.features.index]
    if (not np.array_equal(replay.score, expected.score, equal_nan=True)
            or not replay.predicted.equals(expected.predicted)):
        raise ValueError("Selected model reload differs from validation predictions")
    prediction_path = run / "validation_predictions.parquet"
    combined.to_parquet(prediction_path, index=False)
    if not pd.read_parquet(prediction_path).equals(combined):
        raise ValueError("Validation prediction Parquet roundtrip changed values")
    model_map_path = run / "candidate_models.joblib"
    joblib.dump(fitted, model_map_path, compress=3)
    pd.DataFrame(grids).to_csv(report / "threshold_search.csv", index=False, float_format="%.17g")
    weights.rename("normal_seconds").to_frame().to_csv(report / "normal_exposure_weights.csv", float_format="%.17g")
    failure_examples(combined).to_csv(report / "validation_failure_cases.csv", index=False, float_format="%.17g")
    _write_json(report / "validation_metrics.json", metrics)
    _write_json(report / "search.json", {"run_id": run_id, "identity": identity, "candidates": records,
                                         "selected_candidate": selected["candidate_id"],
                                         "candidate_model_sha256": sha256(model_map_path),
                                         "candidate_model_path": str(model_map_path.relative_to(root)).replace("\\", "/"),
                                         "threshold_search_sha256": sha256(report / "threshold_search.csv"),
                                         "normal_exposure_weights_sha256": sha256(report / "normal_exposure_weights.csv"),
                                         "selected_raw_pipeline_latency": raw_latency,
                                         "test_rows_used": 0, "fit_budget": 8})
    comparison = []
    original_metrics = json.loads((root / "reports/baseline/metrics.json").read_text())
    for name, value in original_metrics["models"].items():
        comparison.append(_comparison_row(name, "fixed_phase4_reference", value, None, False))
    for row in records:
        comparison.append(_comparison_row(row["candidate_id"], "validation_selected_threshold", metrics["models"][row["candidate_id"]], row,
                                          row["candidate_id"] == selected["candidate_id"]))
    pd.DataFrame(comparison).to_csv(root / "reports/model_comparison.csv", index=False, float_format="%.17g")
    selection = {"schema_version": "1.0.0", "run_id": run_id, "model_version": manifest["model_version"],
                 "candidate_id": selected["candidate_id"], "threshold": selected["threshold"],
                 "calibration": "deferred", "selection_criterion": "recall, AP, lower normal occupancy, stable candidate ID",
                 "max_normal_occupancy": MAX_OCCUPANCY, "test_rows_used": 0, "train_families": sorted(train_families),
                 "bundle_path": str(artifact.relative_to(root)).replace("\\", "/"),
                 "bundle_manifest_sha256": sha256(artifact / "manifest.json"),
                 "search_sha256": sha256(report / "search.json"), "protocol_sha256": protocol_hash,
                 "code_sha256": _code_hashes(root), "data_provenance": data.provenance,
                 "validation_predictions_path": str(prediction_path.relative_to(root)).replace("\\", "/"),
                 "validation_predictions_sha256": sha256(prediction_path), "reload_exact": True}
    _write_json(report / "selection.json", selection)
    if sha256(root / PROTOCOL) != protocol_hash or _code_hashes(root) != identity["code_sha256"]:
        raise ValueError("Protocol or code changed during search")
    return selection


def _comparison_row(name: str, role: str, value: dict[str, Any], candidate: dict[str, Any] | None,
                    selected: bool) -> dict[str, Any]:
    metrics, alarms = value["validation"], value["false_alerts"]
    return {"model": name, "partition": "validation", "role": role, "selected": selected,
            **{key: metrics[key] for key in ("windows", "precision", "recall", "f1", "average_precision", "pr_auc_trapezoidal", "tn", "fp", "fn", "tp")},
            **{key: alarms[key] for key in ("confirmed_false_onsets", "false_alerts_per_normal_hour", "false_alerts_per_monitored_replay_hour", "normal_alarm_occupancy_fraction")},
            "threshold": candidate["threshold"] if candidate else None,
            "single_p50_ms": candidate["latency"]["single"]["p50_ms"] if candidate else None,
            "single_p95_ms": candidate["latency"]["single"]["p95_ms"] if candidate else None,
            "batch1024_p50_ms": candidate["latency"]["batch"]["p50_ms"] if candidate else None,
            "fit_seconds": candidate["fit_seconds"] if candidate else None,
            "brier": candidate["probability_quality"]["brier"] if candidate else None,
            "log_loss": candidate["probability_quality"]["log_loss"] if candidate else None}


def acquire_test_gate(path: Path, selection_hash: str) -> dict[str, Any]:
    if len(selection_hash) != 64 or any(c not in "0123456789abcdef" for c in selection_hash):
        raise ValueError("Exact selection SHA-256 required")
    journal = {"schema_version": "1.0.0", "status": "STARTED", "selection_sha256": selection_hash,
               "started_at": datetime.now(timezone.utc).isoformat(), "test_attempts": 1}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(journal, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return journal


def _validate_selection(root: Path, selection: dict[str, Any]) -> Predictor:
    if selection["test_rows_used"] != 0 or selection["protocol_sha256"] != sha256(root / PROTOCOL):
        raise ValueError("Selection protocol/test-access mismatch")
    if selection["code_sha256"] != _code_hashes(root):
        raise ValueError("Selection code/dependency hashes changed")
    if selection["search_sha256"] != sha256(root / REPORTS / "search.json"):
        raise ValueError("Search record changed after selection")
    if selection["validation_predictions_sha256"] != sha256(root / selection["validation_predictions_path"]):
        raise ValueError("Validation predictions changed after selection")
    provenance = selection["data_provenance"]
    if (sha256(root / "data/manifests/development_split.json") != provenance["split_file_sha256"]
            or sha256(root / "reports/preprocessing_summary.json") != provenance["preprocessing_summary_sha256"]):
        raise ValueError("Frozen split or preprocessing summary changed")
    search = json.loads((root / REPORTS / "search.json").read_text())
    for name, key in [("threshold_search.csv", "threshold_search_sha256"), ("normal_exposure_weights.csv", "normal_exposure_weights_sha256")]:
        if sha256(root / REPORTS / name) != search[key]:
            raise ValueError("Selection threshold/exposure evidence changed")
    for item in selection["data_provenance"]["artifacts"].values():
        if sha256(root / item["path"]) != item["sha256"]:
            raise ValueError("Frozen preprocessing artifact changed")
    bundle = (root / selection["bundle_path"]).resolve()
    if not bundle.is_relative_to(root / "ml/artifacts/phase5") or sha256(bundle / "manifest.json") != selection["bundle_manifest_sha256"]:
        raise ValueError("Selected inference bundle changed")
    predictor = load_bundle(bundle)
    if predictor.threshold != selection["threshold"] or predictor.metadata["model_version"] != selection["model_version"]:
        raise ValueError("Selection and inference bundle disagree")
    return predictor


def _load_test_partition(root: Path, selection: dict[str, Any], predictor: Predictor) -> ExperimentalPartition:
    artifacts = selection["data_provenance"]["artifacts"]
    metadata = pd.read_parquet(root / artifacts["metadata"]["path"], filters=[("partition", "==", "test")])
    ids = metadata.index.tolist()
    tables = {name: pd.read_parquet(root / artifacts[name]["path"], filters=[("window_id", "in", ids)])
              for name in ("features", "targets", "quality")}
    state = predictor.pipeline.state
    assert state is not None
    expected_sources = {entry.source.instance_id for entry in state.split_manifest.assignments if entry.partition == "test"}
    summary = json.loads((root / "reports/preprocessing_summary.json").read_text())["partitions"]["test"]
    if (set(metadata.instance_id) != expected_sources or len(metadata) != summary["windows"]
            or metadata.group_id.nunique() != summary["connected_groups"]
            or set(metadata.well_id) != set(summary["real_well_ids"])):
        raise ValueError("Incomplete frozen test cohort")
    if tuple(tables["features"].columns) != state.retained_features:
        raise ValueError("Test feature schema differs from frozen pipeline")
    for source, rows in metadata.groupby("instance_id"):
        assignment = state.split_manifest.assignment_for(source)
        if assignment.partition != "test":
            raise ValueError("Non-test source in test frame")
        for name, expected in {"group_id": assignment.group_id, "origin": assignment.source.origin,
                               "well_id": assignment.source.well_id, "source_path": assignment.source.source_path,
                               "sha256": assignment.source.sha256}.items():
            if not rows[name].eq(expected).all():
                raise ValueError("Test source assignment mismatch")
    sensors = sorted({name.rsplit("__", 1)[0] for name in state.retained_features})
    mask = tables["quality"][[f"{sensor}__observed_count" for sensor in sensors]].sum(axis=1).gt(0)
    value = ExperimentalPartition(tables["features"], tables["targets"], metadata, tables["quality"], mask, "test")
    value.validate()
    if int(value.eligible.sum()) != summary["supervised_eligible_windows"] or int(value.targets.event_family.isna().sum()) != summary["unknown_endpoint_windows"]:
        raise ValueError("Test target support differs from frozen summary")
    return value


def _test_raw(root: Path, partition: ExperimentalPartition, predictor: Predictor) -> dict[str, pd.DataFrame]:
    frames = {}
    state = predictor.pipeline.state
    assert state is not None
    for source_id in sorted(partition.metadata.instance_id.unique()):
        assigned = state.split_manifest.assignment_for(source_id)
        if assigned.partition != "test":
            raise ValueError("Raw test boundary violated")
        source = assigned.source
        path = (root / "data/raw/3w" / source.dataset_version / source.dataset_revision / source.source_path).resolve()
        if not path.is_relative_to(root / "data/raw"):
            raise ValueError("Raw path escape")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != source.sha256:
            raise ValueError("Raw test source hash mismatch")
        frames[source_id] = pd.read_parquet(BytesIO(payload), columns=["class"], engine="pyarrow")
    return frames


def evaluate_test_once(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    report = root / REPORTS
    selection_path = report / "selection.json"
    selection_hash = sha256(selection_path)
    selection = json.loads(selection_path.read_text())
    release = json.loads((report / "TEST_RELEASE.json").read_text())
    if release.get("approved") is not True or release.get("selection_sha256") != selection_hash:
        raise ValueError("Root integrity approval must bind exact frozen selection")
    predictor = _validate_selection(root, selection)
    _verify_requirement_pins(root / "requirements-models.txt")
    journal_path = report / "test_access.json"
    journal = acquire_test_gate(journal_path, selection_hash)
    try:
        test = _load_test_partition(root, selection, predictor)
        scores = estimator_scores(predictor.estimator, predictor.kind, test.features.loc[test.evidence_mask])
        predictions = prediction_frame(test, scores, predictor.threshold, selection["candidate_id"])
        output = root / "ml/runs/phase5" / selection["run_id"] / "test_predictions.parquet"
        predictions.to_parquet(output, index=False)
        journal.update({"prediction_path": str(output.relative_to(root)).replace("\\", "/"),
                        "prediction_sha256": sha256(output)})
        _write_json(journal_path, journal)
        raw = _test_raw(root, test, predictor)
        state = predictor.pipeline.state
        assert state is not None
        metrics = evaluate_partition(predictions, set(selection["train_families"]), raw, "test",
                                     state.config.stride_rows, state.config.cadence_seconds)
        known = predictions[predictions.eligible]
        metrics["probability_quality"] = probability_quality(known.event_family.gt(0).to_numpy(dtype=int),
                                                             known.score.to_numpy(dtype=float), predictor.kind)
        metrics.update({"selection_sha256": selection_hash, "model_version": selection["model_version"],
                        "threshold": predictor.threshold, "test_evaluation_attempt": 1,
                        "protected_evaluation": False, "prior_eda_exposure": True})
        _write_json(report / "test_metrics.json", metrics)
        examples = failure_examples(predictions.assign(partition="validation"))
        examples["partition"] = "test"
        examples.to_csv(report / "test_failure_cases.csv", index=False, float_format="%.17g")
        journal.update({"status": "COMPLETE", "completed_at": datetime.now(timezone.utc).isoformat(),
                        "prediction_path": str(output.relative_to(root)).replace("\\", "/"),
                        "prediction_sha256": sha256(output), "metrics_sha256": sha256(report / "test_metrics.json")})
        _write_json(journal_path, journal)
        return metrics
    except Exception as exc:
        journal.update({"status": "FAILED_NO_RETRY", "error_type": type(exc).__name__})
        _write_json(journal_path, journal)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["search", "test-once"])
    args = parser.parse_args()
    result = run_search() if args.action == "search" else evaluate_test_once()
    print(json.dumps({"action": args.action, "model_version": result.get("model_version"),
                      "candidate_id": result.get("candidate_id"), "partition": result.get("partition")}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
