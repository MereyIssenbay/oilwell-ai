"""Frozen-split diagnostic baselines; no test predictions or hyperparameter search."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.metadata
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any
import uuid
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.data_pipeline import CausalFeaturePipeline, SENSOR_COLUMNS, SplitManifest
from ml.data_pipeline.io import read_json
from ml.data_pipeline.models import TRANSIENT_TO_FAMILY, VALID_CLASSES, fingerprint
from ml.evaluate import evaluate_predictions, failure_examples
from ml.features.constants import FEATURES

FROZEN_SPLIT = "643ecb9867ceaf6daff093f11a2e1b0a2b3066cbe2ce614b4ad1ecf81ff82062"
SEED = 42
LOGISTIC_PARAMETERS = dict(C=1.0, solver="liblinear", l1_ratio=0.0, class_weight={0: 1, 1: 2},
                           max_iter=2000, tol=1e-4, random_state=SEED)
ISOLATION_PARAMETERS = dict(n_estimators=200, max_samples=256, contamination=0.05,
                            max_features=1.0, bootstrap=False, random_state=SEED, n_jobs=1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class PartitionData:
    features: pd.DataFrame
    targets: pd.DataFrame
    metadata: pd.DataFrame
    quality: pd.DataFrame
    evidence_mask: pd.Series
    partition: str

    def validate(self) -> None:
        if self.partition not in ("train", "validation") or self.features.empty:
            raise ValueError("Only nonempty train or validation partitions are accepted")
        if any(not self.features.index.equals(t.index) for t in
               (self.targets, self.metadata, self.quality, self.evidence_mask)) or not self.features.index.is_unique:
            raise ValueError("Partition tables must have unique aligned window IDs")
        if not self.metadata.partition.eq(self.partition).all():
            raise ValueError("Partition metadata does not match requested partition")
        allowed = {f"{s}__{f}" for s in SENSOR_COLUMNS for f in FEATURES}
        if not self.features.columns.is_unique or set(self.features) - allowed:
            raise ValueError("Labels and metadata are not allowed feature columns")
        if not np.isfinite(self.features.to_numpy(dtype=float)).all():
            raise ValueError("Normalized feature values must be finite")
        if not self.metadata.origin.eq("real").all():
            raise ValueError("This experiment requires real-only training and validation")
        if not {"raw_class", "event_family", "phase"}.issubset(self.targets):
            raise ValueError("Raw class, family and phase targets required")
        if not self.targets.raw_class.dropna().isin(VALID_CLASSES).all():
            raise ValueError("Undocumented raw class target")
        for row in self.targets[["raw_class", "event_family", "phase"]].drop_duplicates().itertuples(index=False):
            if pd.isna(row.raw_class):
                if pd.notna(row.event_family) or row.phase != "unknown":
                    raise ValueError("Unknown target must stay unknown")
            else:
                family = TRANSIENT_TO_FAMILY.get(int(row.raw_class), int(row.raw_class))
                phase = "transient" if int(row.raw_class) in TRANSIENT_TO_FAMILY else "normal" if family == 0 else "event"
                if pd.isna(row.event_family) or row.event_family != family or row.phase != phase:
                    raise ValueError("Target family/phase contradicts raw class")
        if self.evidence_mask.dtype != bool:
            raise ValueError("Boolean retained-evidence mask required")
        sensors = sorted({name.rsplit("__", 1)[0] for name in self.features.columns})
        columns = [f"{sensor}__observed_count" for sensor in sensors]
        if not set(columns).issubset(self.quality):
            raise ValueError("Retained-sensor observed counts required")
        values = self.quality[columns].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any() or not np.equal(values, np.floor(values)).all():
            raise ValueError("Observed counts must be finite nonnegative integers")
        if not self.evidence_mask.equals(self.quality[columns].sum(axis=1).gt(0)):
            raise ValueError("Evidence mask differs from retained-sensor observations")

    @property
    def eligible(self) -> pd.Series:
        return self.evidence_mask & self.targets.event_family.notna()


@dataclass(frozen=True)
class BaselineData:
    train: PartitionData
    validation: PartitionData
    state: Any
    split: SplitManifest
    provenance: dict[str, Any]


@dataclass
class FittedBaseline:
    name: str
    estimator: Any | None
    threshold: float
    comparison: str
    constant: int | None
    fit_window_ids: tuple[str, ...]


def select_training_partitions(features: pd.DataFrame, targets: pd.DataFrame,
                               metadata: pd.DataFrame, quality: pd.DataFrame,
                               retained_features: tuple[str, ...], split: SplitManifest
                               ) -> tuple[PartitionData, PartitionData]:
    """Filter test rows before numeric validation, fitting or metric calculations."""
    if tuple(features.columns) != tuple(retained_features):
        raise ValueError("Normalized feature schema differs from frozen preprocessing")
    selected_metadata = metadata[metadata.partition.isin(("train", "validation"))].copy()
    ids = selected_metadata.index
    if not ids.is_unique:
        raise ValueError("Repeated selected window ID")
    selected_features = features.loc[ids].copy()
    selected_targets = targets.loc[ids].copy()
    selected_quality = quality.loc[ids].copy()
    for source_id, rows in selected_metadata.groupby("instance_id", sort=False):
        assignment = split.assignment_for(source_id)
        expected = {"partition": assignment.partition, "group_id": assignment.group_id,
                    "origin": assignment.source.origin, "well_id": assignment.source.well_id,
                    "source_path": assignment.source.source_path, "sha256": assignment.source.sha256}
        for column, value in expected.items():
            if not rows[column].eq(value).all():
                raise ValueError(f"Frozen source assignment mismatch: {column}")
    retained_sensors = sorted({name.rsplit("__", 1)[0] for name in retained_features})
    evidence_columns = [f"{name}__observed_count" for name in retained_sensors]
    if not set(evidence_columns).issubset(selected_quality):
        raise ValueError("Retained-sensor evidence counts missing")
    evidence = selected_quality[evidence_columns].sum(axis=1).gt(0)
    result = []
    for partition in ("train", "validation"):
        mask = selected_metadata.partition.eq(partition)
        value = PartitionData(selected_features.loc[mask].copy(), selected_targets.loc[mask].copy(),
                              selected_metadata.loc[mask].copy(), selected_quality.loc[mask].copy(),
                              evidence.loc[mask].copy(), partition)
        value.validate()
        result.append(value)
    train, validation = result
    for column in ("instance_id", "well_id", "group_id"):
        if set(train.metadata[column]) & set(validation.metadata[column]):
            raise ValueError(f"Train/validation overlap: {column}")
    return train, validation


def load_training_data(root: Path) -> BaselineData:
    root = Path(root).resolve()
    report_path = root / "reports/preprocessing_summary.json"
    report = read_json(report_path)
    split_path = root / "data/manifests/development_split.json"
    split = SplitManifest.model_validate(read_json(split_path))
    if report["split_fingerprint"] != split.fingerprint:
        raise ValueError("Preprocessing report and split fingerprints differ")
    paths = {}
    for name in ("preprocessor", "features", "targets", "metadata", "quality"):
        entry = report["artifacts"][name]
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root / "data/processed") or sha256(path) != entry["sha256"]:
            raise ValueError(f"Invalid or changed preprocessing artifact: {name}")
        paths[name] = path
    preprocessing = CausalFeaturePipeline.load(paths["preprocessor"])
    state = preprocessing.state
    assert state is not None
    if state.split_manifest.fingerprint != split.fingerprint or state.fingerprint != report["preprocessor_fingerprint"]:
        raise ValueError("Frozen preprocessing belongs to another split/state")
    # Metadata predicate selects approved rows. Other tables are read with those
    # exact window IDs; test values never reach the estimator/evaluation arrays.
    metadata = pd.read_parquet(paths["metadata"], filters=[("partition", "in", ["train", "validation"])])
    ids = metadata.index.tolist()
    tables = {name: pd.read_parquet(paths[name], filters=[("window_id", "in", ids)])
              for name in ("features", "targets", "quality")}
    train, validation = select_training_partitions(tables["features"], tables["targets"], metadata,
                                                   tables["quality"], state.retained_features, split)
    return BaselineData(train, validation, state, split,
                        {"preprocessing_summary_sha256": sha256(report_path), "split_file_sha256": sha256(split_path),
                         "artifacts": report["artifacts"], "dataset": report["source"],
                         "preprocessing_source_provenance": report["provenance"],
                         "split_fingerprint": split.fingerprint, "preprocessor_fingerprint": state.fingerprint})


def fit_models(train: PartitionData) -> dict[str, FittedBaseline]:
    train.validate()
    if train.partition != "train":
        raise ValueError("Estimator fitting accepts train only")
    eligible = train.eligible
    x = train.features.loc[eligible]
    y = train.targets.loc[eligible, "event_family"].gt(0).astype(int)
    if set(y.unique()) != {0, 1}:
        raise ValueError("Binary baseline fitting needs known normal and abnormal train windows")
    normal_ids = y.index[y.eq(0)]
    if len(normal_ids) < 2:
        raise ValueError("Isolation Forest needs at least two known-normal training windows")
    majority = int(int(y.eq(1).sum()) > int(y.eq(0).sum()))
    logistic = LogisticRegression(**LOGISTIC_PARAMETERS)
    isolation = IsolationForest(**ISOLATION_PARAMETERS)
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        logistic.fit(x, y)
        isolation.fit(x.loc[normal_ids])
    fit_ids = tuple(str(v) for v in x.index)
    return {
        "always_normal": FittedBaseline("always_normal", None, 0.5, "ge", 0, ()),
        "train_majority": FittedBaseline("train_majority", None, 0.5, "ge", majority, fit_ids),
        "logistic_regression": FittedBaseline("logistic_regression", logistic, 0.5, "ge", None, fit_ids),
        "isolation_forest": FittedBaseline("isolation_forest", isolation, float(-isolation.offset_), "gt", None,
                                            tuple(str(v) for v in normal_ids)),
    }


def predict_models(models: dict[str, FittedBaseline], validation: PartitionData) -> pd.DataFrame:
    validation.validate()
    if validation.partition != "validation":
        raise ValueError("This experiment predicts validation only")
    all_rows = []
    available = validation.evidence_mask
    x = validation.features.loc[available]
    for name, model in sorted(models.items()):
        if name != model.name or model.comparison not in ("ge", "gt") or not np.isfinite(model.threshold):
            raise ValueError("Invalid model descriptor")
        if model.constant is not None and model.constant not in (0, 1):
            raise ValueError("Naive constant must be binary")
        if not len(x):
            values = np.empty(0, dtype=float)
        elif model.constant is not None:
            values = np.full(len(x), model.constant, dtype=float)
        elif name == "logistic_regression":
            values = model.estimator.predict_proba(x)[:, list(model.estimator.classes_).index(1)]
        elif name == "isolation_forest":
            values = -model.estimator.score_samples(x)
        else:
            raise ValueError("Unknown fitted baseline")
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite model output")
        decisions = values >= model.threshold if model.comparison == "ge" else values > model.threshold
        rows = validation.metadata.copy()
        rows["window_id"] = rows.index
        for column in ("raw_class", "event_family", "phase"):
            rows[column] = validation.targets[column]
        rows["model"] = name
        rows["has_input"] = available
        rows["eligible"] = validation.eligible
        rows["score"] = np.nan
        rows["predicted"] = pd.Series(pd.NA, index=rows.index, dtype="Int8")
        rows.loc[available, "score"] = values
        rows.loc[available, "predicted"] = decisions.astype(np.int8)
        all_rows.append(rows.reset_index(drop=True))
    return pd.concat(all_rows, ignore_index=True)


def load_validation_raw(root: Path, data: BaselineData) -> dict[str, pd.DataFrame]:
    frames = {}
    for source_id in sorted(data.validation.metadata.instance_id.unique()):
        source = data.split.assignment_for(source_id).source
        if data.split.partition_for(source_id) != "validation":
            raise ValueError("Raw exposure accounting may read only validation instances")
        path = (root / "data/raw/3w" / source.dataset_version / source.dataset_revision / source.source_path).resolve()
        if not path.is_relative_to(root / "data/raw"):
            raise ValueError("Raw validation path escapes data/raw")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != source.sha256:
            raise ValueError("Raw validation source hash mismatch")
        frame = pd.read_parquet(BytesIO(payload), columns=["class"], engine="pyarrow")
        if not frame["class"].dropna().isin(VALID_CLASSES).all():
            raise ValueError("Unknown raw validation label")
        frames[source_id] = frame
    return frames


def _write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _serialize_models(models: dict[str, FittedBaseline]) -> dict[str, Any]:
    return {name: {"estimator": value.estimator, "threshold": value.threshold,
                   "comparison": value.comparison, "constant": value.constant,
                   "fit_window_ids": value.fit_window_ids} for name, value in models.items()}


def _load_local_models(path: Path, expected_sha256: str) -> dict[str, FittedBaseline]:
    """Only call on this run's locally generated, hash-verified trusted joblib."""
    if sha256(path) != expected_sha256:
        raise ValueError("Model artifact hash mismatch")
    payload = joblib.load(path)
    return {name: FittedBaseline(name=name, **value) for name, value in payload.items()}


def _environment(root: Path) -> dict[str, Any]:
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return {"python": platform.python_version(), "platform": platform.platform(),
            "base_git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
            "dependencies": dict(sorted((dist.metadata["Name"], dist.version) for dist in importlib.metadata.distributions())),
            "thread_limit_during_fit": 1, "seed": SEED}


def _verify_requirement_pins(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("-r "):
            _verify_requirement_pins(path.parent / line[3:].strip())
        elif line and not line.startswith("#"):
            if "==" not in line:
                raise ValueError("Baseline environment must use exact dependency pins")
            name, version = line.split("==")
            if importlib.metadata.version(name) != version:
                raise ValueError(f"Installed dependency does not match pin: {name}")


def _plots_and_tables(report_dir: Path, metrics: dict[str, Any], predictions: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = ("always_normal", "train_majority", "logistic_regression", "isolation_forest")
    titles = ("Always normal", "Train majority", "Logistic Regression", "Isolation Forest")
    figure, axes = plt.subplots(2, 2, figsize=(10, 8), layout="constrained")
    maximum_count = max(max(max(row) for row in metrics["models"][name]["validation"]["confusion_matrix"]) for name in order)
    for axis, name, title in zip(axes.flat, order, titles):
        matrix = np.asarray(metrics["models"][name]["validation"]["confusion_matrix"])
        axis.imshow(matrix, cmap="Blues", vmin=0, vmax=maximum_count)
        for i in range(2):
            for j in range(2):
                axis.text(j, i, f"{matrix[i,j]:,}", ha="center", va="center",
                          color="white" if matrix[i,j] > maximum_count * .6 else "black", fontsize=14)
        axis.set_xticks([0, 1], ["Normal", "Abnormal"])
        axis.set_yticks([0, 1], ["Normal", "Abnormal"])
        axis.set_xlabel("Predicted"); axis.set_ylabel("True")
        axis.set_title(title, weight="bold")
    figure.suptitle("Frozen real validation: binary detection confusion matrices\nDevelopment diagnostics; no test evaluation", weight="bold")
    figure.savefig(report_dir / "confusion_matrices.png", dpi=150)
    plt.close(figure)
    figure, axis = plt.subplots(figsize=(10, 6), layout="constrained")
    records = []
    for name, title in zip(order, titles):
        rows = predictions[predictions.model.eq(name) & predictions.eligible]
        p, r, threshold = precision_recall_curve(rows.event_family.gt(0).astype(int), rows.score)
        ap = metrics["models"][name]["validation"]["average_precision"]
        curve, = axis.step(r, p, where="post", label=f"{title} | AP {ap:.4f}")
        operating = metrics["models"][name]["validation"]
        if operating["precision"] is not None:
            axis.scatter(operating["recall"], operating["precision"], color=curve.get_color(), s=45, zorder=5)
        chosen = np.unique(np.linspace(0, len(p) - 1, min(501, len(p)), dtype=int))
        for index in chosen:
            records.append({"model": name, "recall": r[index], "precision": p[index],
                            "threshold": threshold[index] if index < len(threshold) else None})
    prevalence = metrics["models"]["always_normal"]["validation"]["positive_prevalence"]
    axis.axhline(prevalence, color="gray", ls="--", label=f"Positive prevalence {prevalence:.4f}")
    axis.set(xlabel="Recall", ylabel="Precision", xlim=(0, 1), ylim=(0, 1.02),
             title="Precision-recall ranking on the same real validation windows\nSteps: noninterpolated AP; dots: fixed operating points; naive curves overlap")
    axis.legend(loc="lower left", fontsize=9)
    figure.savefig(report_dir / "precision_recall.png", dpi=150)
    plt.close(figure)
    pd.DataFrame(records).to_csv(report_dir / "pr_curve_points.csv", index=False, float_format="%.17g")
    table = []
    for name in order:
        result = metrics["models"][name]
        table.append({"model": name, **{k: result["validation"][k] for k in
                     ("tn", "fp", "fn", "tp", "precision", "recall", "f1", "average_precision", "pr_auc_trapezoidal")},
                     **{k: result["false_alerts"][k] for k in ("confirmed_false_onsets", "false_alerts_per_normal_hour",
                        "false_alerts_per_monitored_replay_hour", "normal_alarm_occupancy_fraction")}})
    pd.DataFrame(table).to_csv(report_dir / "model_comparison.csv", index=False, float_format="%.17g")
    family_table = [{"model": name, **row} for name, model in metrics["models"].items() for row in model["by_family"]]
    pd.DataFrame(family_table).to_csv(report_dir / "minority_events.csv", index=False, float_format="%.17g")


def run_experiment(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    data = load_training_data(root)
    if data.split.fingerprint != FROZEN_SPLIT or data.state.config.transient_policy != "family":
        raise ValueError("Phase 4 CLI requires the predeclared Phase 3 split and family policy")
    protocol_path = root / "reports/baseline/PROTOCOL.md"
    dependency_path = root / "requirements-baseline.txt"
    _verify_requirement_pins(dependency_path)
    protocol_hash = sha256(protocol_path)
    input_hashes = {str(root / entry["path"]): entry["sha256"] for entry in data.provenance["artifacts"].values()}
    input_hashes[str(root / "reports/preprocessing_summary.json")] = data.provenance["preprocessing_summary_sha256"]
    input_hashes[str(root / "data/manifests/development_split.json")] = data.provenance["split_file_sha256"]
    environment = _environment(root)
    code_files = [root / "ml/train_baseline.py", root / "ml/evaluate.py"]
    identity = {"protocol_sha256": protocol_hash, "code_sha256": {str(p.relative_to(root)): sha256(p) for p in code_files},
                "requirements_sha256": sha256(dependency_path), "environment": environment,
                "data": data.provenance, "logistic_parameters": LOGISTIC_PARAMETERS,
                "isolation_parameters": ISOLATION_PARAMETERS, "naive": ["always_normal", "train_majority_ties_normal"]}
    run_id = fingerprint(identity)[:20]
    artifact_dir = root / "ml/artifacts/baseline" / run_id
    run_dir = root / "ml/runs/baseline" / run_id
    report_dir = root / "reports/baseline"
    for path in (artifact_dir, run_dir, report_dir):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Output directory escapes repository")
        path.mkdir(parents=True, exist_ok=True)
    models = fit_models(data.train)
    predictions = predict_models(models, data.validation)
    raw_validation = load_validation_raw(root, data)
    for source_id in sorted(data.validation.metadata.instance_id.unique()):
        source = data.split.assignment_for(source_id).source
        path = root / "data/raw/3w" / source.dataset_version / source.dataset_revision / source.source_path
        input_hashes[str(path)] = source.sha256
    train_families = set(int(v) for v in data.train.targets.loc[data.train.eligible, "event_family"].unique())
    metrics = evaluate_predictions(predictions, train_families, raw_validation,
                                   data.state.config.stride_rows, data.state.config.cadence_seconds)
    model_path = artifact_dir / "models.joblib"
    joblib.dump(_serialize_models(models), model_path, compress=3)
    model_hash = sha256(model_path)
    restored = _load_local_models(model_path, model_hash)
    restored_predictions = predict_models(restored, data.validation)
    if not predictions.equals(restored_predictions):
        raise ValueError("Model reload changed validation predictions")
    prediction_path = run_dir / "validation_predictions.parquet"
    predictions.to_parquet(prediction_path, engine="pyarrow", index=False)
    if not pd.read_parquet(prediction_path).equals(predictions):
        raise ValueError("Prediction Parquet round trip failed")
    source_state = root / data.provenance["artifacts"]["preprocessor"]["path"]
    shutil.copyfile(source_state, artifact_dir / "preprocessor.json")
    _write_json(artifact_dir / "split.json", data.split.model_dump(mode="json"))
    descriptors = {}
    for name, model in models.items():
        descriptors[name] = {"threshold": model.threshold, "comparison": model.comparison,
                             "constant": model.constant, "fit_windows": len(model.fit_window_ids),
                             "fit_window_ids_sha256": fingerprint(model.fit_window_ids),
                             "parameters": model.estimator.get_params() if model.estimator is not None else {},
                             "score_semantics": "negative score_samples; larger=more anomalous, not probability" if name == "isolation_forest"
                             else "uncalibrated positive-class probability" if name == "logistic_regression" else "constant decision score"}
        if name == "logistic_regression":
            descriptors[name]["fit_status"] = {"converged": True, "n_iter": model.estimator.n_iter_.tolist(),
                                               "classes": model.estimator.classes_.tolist(),
                                               "n_features": int(model.estimator.n_features_in_)}
        elif name == "isolation_forest":
            descriptors[name]["fit_status"] = {"trees": len(model.estimator.estimators_),
                                               "effective_max_samples": int(model.estimator.max_samples_),
                                               "n_features": int(model.estimator.n_features_in_),
                                               "reference": "known-normal estimator fit; shared preprocessing fitted on all train endpoints"}
    if sha256(protocol_path) != protocol_hash or any(sha256(Path(path)) != expected for path, expected in input_hashes.items()):
        raise ValueError("Protocol or source/preprocessing inputs changed during experiment")
    manifest = {"schema_version": "1.0.0", "run_id": run_id, "identity": identity, "models": descriptors,
                "feature_names": list(data.state.retained_features), "train_event_families": sorted(train_families),
                "validation_event_families": sorted(int(v) for v in data.validation.targets.loc[data.validation.eligible, "event_family"].unique()),
                "training_windows": int(data.train.eligible.sum()), "validation_windows": int(data.validation.eligible.sum()),
                "test_rows_used": 0, "test_predictions_generated": 0, "hyperparameter_search": False,
                "validation_threshold_tuning": False, "model_reload_predictions_exact": True,
                "source_and_preprocessing_hashes_unchanged": True, "installed_dependency_pins_verified": True,
                "artifacts": {"models": {"path": str(model_path.relative_to(root)).replace("\\", "/"), "sha256": model_hash},
                              "preprocessor": {"path": str((artifact_dir / 'preprocessor.json').relative_to(root)).replace("\\", "/"), "sha256": sha256(artifact_dir / 'preprocessor.json')},
                              "predictions": {"path": str(prediction_path.relative_to(root)).replace("\\", "/"), "sha256": sha256(prediction_path)}}}
    metrics.update({"run_id": run_id, "split_fingerprint": data.split.fingerprint,
                    "preprocessor_fingerprint": data.state.fingerprint, "model_parameters": descriptors,
                    "training_families": sorted(train_families), "readiness": {
                        "software_baseline_experiment_complete": True, "accepted_detector": False,
                        "reason": "Diagnostic exposed cohort; validation abnormal families absent from training and insufficient independent support; no declared operational false-alarm budget"}})
    _plots_and_tables(report_dir, metrics, predictions)
    failure_examples(predictions).to_csv(report_dir / "failure_cases.csv", index=False, float_format="%.17g")
    _write_json(artifact_dir / "manifest.json", manifest)
    _write_json(report_dir / "experiment_manifest.json", manifest)
    _write_json(report_dir / "metrics.json", metrics)
    _write_readme(report_dir, metrics, manifest)
    if sha256(protocol_path) != protocol_hash or any(sha256(Path(path)) != expected for path, expected in input_hashes.items()):
        raise ValueError("Protocol or source/preprocessing inputs changed during experiment")
    return metrics


def _write_readme(report_dir: Path, metrics: dict[str, Any], manifest: dict[str, Any]) -> None:
    lines = ["# Phase 4 diagnostic baseline results", "", "Fixed protocol: [PROTOCOL.md](PROTOCOL.md). No hyperparameter or threshold tuning; no test predictions or metrics.", "",
             f"Run `{manifest['run_id']}` uses split `{metrics['split_fingerprint']}` and the frozen Phase 3 preprocessing state.", "",
             "The task is binary normal-versus-documented-undesirable detection. Training contains event families 3, 4, 5 and 7; validation contains 2 and 8, both absent from training. This is a cross-family development diagnostic, not an accepted event-family classifier or a pristine evaluation.", "",
             "| Model | Precision | Recall | F1 | AP | PR-AUC trapezoidal | False onsets/normal hour | Normal alarm occupancy |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    number = lambda v: "undefined" if v is None else f"{v:.9f}"
    for name, model in metrics["models"].items():
        value, alarm = model["validation"], model["false_alerts"]
        vals = [value[k] for k in ("precision", "recall", "f1", "average_precision", "pr_auc_trapezoidal")]
        vals += [alarm["false_alerts_per_normal_hour"], alarm["normal_alarm_occupancy_fraction"]]
        lines.append("| " + name + " | " + " | ".join(number(v) for v in vals) + " |")
    logistic = metrics["models"]["logistic_regression"]
    isolation = metrics["models"]["isolation_forest"]
    majority = metrics["models"]["train_majority"]
    lines += ["", "Exact full-precision values and denominators: [metrics.json](metrics.json), [model_comparison.csv](model_comparison.csv).",
              "", "![Validation confusion matrices](confusion_matrices.png)", "", "![Precision-recall curves](precision_recall.png)", "",
              "## Interpretation and failures", "",
              f"Logistic Regression has AP {logistic['validation']['average_precision']:.9f}, above the constant-score references, but the fixed operating point misses {logistic['validation']['fn']:,} of {logistic['validation']['abnormal_windows']:,} abnormal windows. Isolation Forest detects all {isolation['validation']['tp']:,} abnormal windows while falsely flagging {isolation['validation']['fp']:,} of {isolation['validation']['normal_windows']:,} normal windows. Its F1 ({isolation['validation']['f1']:.9f}) is only slightly above the always-abnormal training-majority reference ({majority['validation']['f1']:.9f}); high recall alone would hide the alarm burden.", "",
              "| Model | Family | Detected / supported windows | Misses | Detection recall | Seen in train |",
              "| --- | ---: | ---: | ---: | ---: | --- |"]
    for name, model in metrics["models"].items():
        for row in model["by_family"]:
            if row["windows"]:
                lines.append(f"| {name} | {row['event_family']} | {row['detected_windows']} / {row['windows']} | {row['missed_windows']} | {row['recall']:.9f} | {row['seen_in_training']} |")
    lines += ["",
              "Family 2 has only 152 validation windows from one well; family 8 has 8,642 from one well. The dominant event supplies most abnormal windows, so pooled recall/F1 cannot replace the minority slice. Neither family occurs in the fitting labels.", "",
              f"All {logistic['validation']['fp']} Logistic Regression false-positive endpoints occur on WELL-00011, covering all 215 evaluable normal endpoints on that well. Its positive episode began at censored coverage, so the confirmed new-false-onset count is {logistic['false_alerts']['confirmed_false_onsets']} despite {logistic['false_alerts']['normal_alarm_seconds']:.0f} normal seconds under alarm. This is not zero false-alarm exposure. Isolation Forest falsely alarms on all normal endpoints from WELL-00006 and WELL-00029 and on 112/215 normal endpoints from WELL-00011.", "",
              f"Across {logistic['false_alerts']['normal_hours']:.9f} monitored normal hours and {logistic['false_alerts']['monitored_replay_hours']:.9f} total covered source hours, Logistic Regression's normal alarm occupancy is {100*logistic['false_alerts']['normal_alarm_occupancy_fraction']:.6f}%; Isolation Forest's is {100*isolation['false_alerts']['normal_alarm_occupancy_fraction']:.6f}%. Isolation Forest has {isolation['false_alerts']['confirmed_false_onsets']} confirmed false onsets, or {isolation['false_alerts']['false_alerts_per_monitored_replay_hour']:.9f} per covered replay hour. The majority reference occupies 100% of normal time even with no confirmed new false onsets.", "",
              "All four models use the same eligible validation windows. Unknown endpoint targets are excluded from classification metrics but their available predictions preserve alert continuity. Naive constant scores have tied rankings: AP equals validation positive prevalence; trapezoidal interpolation yields a different area and must not be confused with AP.", "",
              "The Isolation Forest estimator fits only known-normal training windows. Its shared frozen preprocessing was fitted on all training endpoints, including abnormal and unknown-label windows. This common preprocessing is intentional for comparison; the entire Isolation Forest pipeline is therefore not normal-only fitted.", "",
              "Per-origin metrics are explicit: real is evaluated; simulated/drawn are absent from the frozen real-only validation split and have null unsupported metrics. [Minority-event recalls](minority_events.csv) describe binary detection, not predicted event identities. Every absent family remains unsupported. [Failure examples](failure_cases.csv) list deterministic false positives/negatives with source timestamps and scores, without inferred physical causes.", "",
              "False-alert onsets are observed negative-to-positive decisions starting on a normal raw label. A positive start at a file/time-gap/abstention boundary is censored; unknown target labels never reset predicted episodes. Exact raw-label seconds under stride-length sample-and-hold decisions define monitored normal and total replay exposure. This is offline accounting, not an executed backend replay. Normal alarm occupancy and false-positive window fraction accompany onset rates: an always-positive detector can have no confirmed onsets and still alarm throughout normal operation.", "",
              "## Reproduce and artifacts", "", "```powershell", ".\\.venv\\Scripts\\python.exe -m ml.train_baseline", "```", "",
              "Install the root `requirements-baseline.txt` first. [Experiment manifest](experiment_manifest.json) records environment, seeds, fixed parameters, source/preprocessing/split/code hashes and artifact paths. Full validation predictions and model binaries remain ignored under `ml/runs/baseline/<run_id>/` and `ml/artifacts/baseline/<run_id>/`. The bundle includes the frozen preprocessing state and split. Model joblib is executable serialization: load only the locally generated trusted artifact after its recorded hash matches. Save/reload and Parquet round trips were checked exactly in the training command.", "",
              "The plotted curves use full validation score ranks. [CSV curve points](pr_curve_points.csv) are deterministic display samples of at most 501 points per model; exact AP/area metrics use all points. No threshold was selected from these curves.", "",
              "## Readiness", "", "The reproducible baseline software is available for further approved experiments. The detector is **not accepted for monitoring claims**: current data is EDA-exposed, validation has only three published well IDs and both abnormal families are unseen during training, event support is inadequate, and no operational false-alarm/recall budget has been approved. Window counts are correlated, not independent replications. Future work needs an adequate protected cohort and a declared evidence/alert policy before model acceptance.", "",
              "Attribution: Petrobras and the 3W contributors, dataset v2.0.0 at the pinned acquisition revision, CC BY 4.0. Derived diagnostics imply no endorsement.", ""]
    (report_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = run_experiment(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Baseline failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"run_id": result["run_id"], "models": {name: values["validation"] for name, values in result["models"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
