"""Validation-only binary detection metrics and offline alert-exposure accounting."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, auc, precision_recall_curve

from ml.data_pipeline.models import TRANSIENT_TO_FAMILY, VALID_CLASSES


def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    """Confusion counts use normal=0/abnormal=1; undefined ratios remain null."""
    y_true, y_pred, scores = np.asarray(y_true), np.asarray(y_pred), np.asarray(scores, dtype=float)
    if any(a.ndim != 1 for a in (y_true, y_pred, scores)) or not (len(y_true) == len(y_pred) == len(scores)):
        raise ValueError("Aligned one-dimensional target/prediction/score arrays required")
    if not np.isin(y_true, (0, 1)).all() or not np.isin(y_pred, (0, 1)).all() or not np.isfinite(scores).all():
        raise ValueError("Binary labels/predictions and finite scores required")
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    ratio = lambda a, b: float(a / b) if b else None
    both_classes = bool((tp + fn) and (tn + fp))
    if both_classes:
        precision_curve, recall_curve, _ = precision_recall_curve(y_true, scores)
        ap = float(average_precision_score(y_true, scores))
        trapezoid = float(auc(recall_curve, precision_curve))
    else:
        ap, trapezoid = None, None
    return {
        "status": "evaluated" if len(y_true) else "not_evaluated",
        "windows": len(y_true), "normal_windows": tn + fp, "abnormal_windows": tp + fn,
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "average_precision": ap, "pr_auc_trapezoidal": trapezoid,
        "false_positive_window_fraction": ratio(fp, tn + fp),
        "positive_prevalence": ratio(tp + fn, len(y_true)),
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "confusion_labels": ["normal", "abnormal"],
        "undefined": {
            "precision": "no positive predictions" if not tp + fp else None,
            "recall": "no abnormal target windows" if not tp + fn else None,
            "f1": "no positive targets or predictions" if not 2 * tp + fp + fn else None,
            "ranking_metrics": "both target classes required" if not both_classes else None,
        },
    }


def _validation_frame(frame: pd.DataFrame) -> None:
    required = {"model", "window_id", "instance_id", "partition", "origin", "well_id", "timestamp",
                "endpoint_position", "raw_class", "event_family", "phase", "has_input", "eligible",
                "score", "predicted"}
    if not required.issubset(frame):
        raise ValueError(f"Prediction columns missing: {sorted(required - set(frame))}")
    if frame.empty or not frame.partition.eq("validation").all():
        raise ValueError("Evaluation accepts nonempty validation rows only")
    if frame.duplicated(["model", "window_id"]).any():
        raise ValueError("Duplicate model/window prediction")
    if frame.duplicated(["model", "instance_id", "timestamp"]).any():
        raise ValueError("Repeated prediction timestamp within a source")
    if (not pd.api.types.is_integer_dtype(frame.endpoint_position.dtype)
            or pd.api.types.is_bool_dtype(frame.endpoint_position.dtype)
            or frame.endpoint_position.isna().any() or frame.endpoint_position.lt(0).any()):
        raise ValueError("Endpoint positions must be nonnegative integers")
    if frame.has_input.dtype != bool or frame.eligible.dtype != bool:
        raise ValueError("Strict Boolean availability and eligibility required")
    if not frame.raw_class.dropna().isin(VALID_CLASSES).all():
        raise ValueError("Undocumented raw endpoint label")
    for row in frame[["raw_class", "event_family", "phase"]].drop_duplicates().itertuples(index=False):
        if pd.isna(row.raw_class):
            if pd.notna(row.event_family) or row.phase != "unknown":
                raise ValueError("Unknown raw label must remain an unknown family/phase")
        else:
            expected = TRANSIENT_TO_FAMILY.get(int(row.raw_class), int(row.raw_class))
            phase = "transient" if int(row.raw_class) in TRANSIENT_TO_FAMILY else "normal" if expected == 0 else "event"
            if pd.isna(row.event_family) or row.event_family != expected or row.phase != phase:
                raise ValueError("Endpoint family/phase does not match documented raw label")
    available = frame.has_input.to_numpy(dtype=bool)
    if not np.isfinite(frame.loc[available, "score"].to_numpy(dtype=float)).all():
        raise ValueError("Available predictions require finite scores")
    if not frame.loc[available, "predicted"].isin((0, 1)).all():
        raise ValueError("Available predictions must be binary")
    if frame.loc[~available, ["score", "predicted"]].notna().any().any():
        raise ValueError("Unavailable predictions must abstain")
    if not frame.eligible.eq(frame.has_input & frame.event_family.notna()).all():
        raise ValueError("Supervised eligibility must equal retained input and known target")


def false_alert_metrics(predictions: pd.DataFrame, raw_validation: dict[str, pd.DataFrame],
                        stride_rows: int = 10, cadence_seconds: float = 1.0) -> dict[str, Any]:
    """Sample-and-hold source-time exposure; label changes never reset alert runs.

    A confirmed onset needs an immediately preceding available negative decision.
    A positive decision at a file/gap/abstention boundary is censored. Raw labels
    attribute time/onsets only, never change the predicted episode state.
    """
    _validation_frame(predictions)
    if (predictions.model.nunique() != 1 or type(stride_rows) is not int or stride_rows < 1
            or isinstance(cadence_seconds, (bool, np.bool_))
            or not isinstance(cadence_seconds, (int, float, np.integer, np.floating))
            or not np.isfinite(cadence_seconds) or cadence_seconds <= 0):
        raise ValueError("One model and positive stride/cadence required")
    counts = {"confirmed_false_onsets": 0, "confirmed_abnormal_onsets": 0,
              "unknown_label_onsets": 0, "censored_positive_starts": 0}
    times = {"monitored_seconds": 0.0, "normal_seconds": 0.0, "abnormal_seconds": 0.0,
             "unknown_seconds": 0.0, "normal_alarm_seconds": 0.0}
    expected_delta = stride_rows * cadence_seconds
    for instance_id, rows in predictions.groupby("instance_id", sort=True):
        if instance_id not in raw_validation:
            raise ValueError("Raw validation source missing for exposure accounting")
        raw = raw_validation[instance_id]
        if ("class" not in raw or not isinstance(raw.index, pd.DatetimeIndex) or raw.index.hasnans
                or not raw.index.is_unique or not raw.index.is_monotonic_increasing):
            raise ValueError("Valid original timestamps and class labels required")
        if not raw["class"].dropna().isin(VALID_CLASSES).all():
            raise ValueError("Undocumented raw source class")
        rows = rows.sort_values("timestamp", kind="stable")
        previous_time, previous_prediction, previous_position = None, None, None
        scheduled_positions = rows.endpoint_position.to_numpy(dtype=int)
        for row_number, (_, row) in enumerate(rows.iterrows()):
            position = int(row.endpoint_position)
            if position < 0 or position >= len(raw) or raw.index[position] != row.timestamp:
                raise ValueError("Prediction endpoint does not match original source")
            actual_class = raw["class"].iloc[position]
            if not ((pd.isna(actual_class) and pd.isna(row.raw_class))
                    or (pd.notna(actual_class) and pd.notna(row.raw_class) and int(actual_class) == int(row.raw_class))):
                raise ValueError("Prediction target differs from raw validation endpoint")
            contiguous = previous_time is not None and (row.timestamp - previous_time).total_seconds() == expected_delta
            if contiguous:
                raw_intervals = raw.index[previous_position + 1:position + 1] - raw.index[previous_position:position]
                contiguous = bool((raw_intervals.total_seconds() == cadence_seconds).all())
            if not row.has_input:
                previous_time, previous_prediction, previous_position = row.timestamp, None, position
                continue
            positive = bool(row.predicted)
            if positive:
                if not contiguous or previous_prediction is None:
                    counts["censored_positive_starts"] += 1
                elif not previous_prediction:
                    if pd.isna(actual_class):
                        counts["unknown_label_onsets"] += 1
                    elif int(actual_class) == 0:
                        counts["confirmed_false_onsets"] += 1
                    else:
                        counts["confirmed_abnormal_onsets"] += 1
            stop = min(position + stride_rows, len(raw))
            if row_number + 1 < len(rows):
                stop = min(stop, int(scheduled_positions[row_number + 1]))
            for next_position in range(position + 1, stop):
                if (raw.index[next_position] - raw.index[next_position - 1]).total_seconds() != cadence_seconds:
                    stop = next_position
                    break
            labels = raw["class"].iloc[position:stop]
            normal = int(labels.eq(0).fillna(False).sum())
            unknown = int(labels.isna().sum())
            abnormal = len(labels) - normal - unknown
            times["monitored_seconds"] += len(labels) * cadence_seconds
            times["normal_seconds"] += normal * cadence_seconds
            times["abnormal_seconds"] += abnormal * cadence_seconds
            times["unknown_seconds"] += unknown * cadence_seconds
            times["normal_alarm_seconds"] += normal * cadence_seconds if positive else 0.0
            previous_time, previous_prediction, previous_position = row.timestamp, positive, position
    normal_hours = times["normal_seconds"] / 3600
    replay_hours = times["monitored_seconds"] / 3600
    return {
        **counts, **times, "normal_hours": normal_hours, "monitored_replay_hours": replay_hours,
        "false_alerts_per_normal_hour": counts["confirmed_false_onsets"] / normal_hours if normal_hours else None,
        "false_alerts_per_monitored_replay_hour": counts["confirmed_false_onsets"] / replay_hours if replay_hours else None,
        "normal_alarm_occupancy_fraction": times["normal_alarm_seconds"] / times["normal_seconds"] if times["normal_seconds"] else None,
        "policy": "available prediction runs; normal 0-to-1 onsets; boundary starts censored; labels never reset runs",
        "exposure": "source-label seconds under causal stride-length sample-and-hold decisions; gaps bounded",
        "application_replay_executed": False,
    }


def evaluate_predictions(predictions: pd.DataFrame, train_families: set[int],
                         raw_validation: dict[str, pd.DataFrame], stride_rows: int = 10,
                         cadence_seconds: float = 1.0) -> dict[str, Any]:
    _validation_frame(predictions)
    models = {}
    expected_ids = None
    expected_context = None
    for model, rows in predictions.groupby("model", sort=True):
        selected = rows[rows.eligible]
        ids = tuple(sorted(selected.window_id))
        if expected_ids is None:
            expected_ids = ids
        elif ids != expected_ids:
            raise ValueError("All models must use identical eligible validation windows")
        context = rows.drop(columns=["model", "score", "predicted"]).sort_values("window_id").reset_index(drop=True)
        if expected_context is None:
            expected_context = context
        elif not context.equals(expected_context):
            raise ValueError("Models must share identical endpoint targets/provenance/availability")

        def metrics(data: pd.DataFrame) -> dict[str, Any]:
            return binary_metrics(data.event_family.gt(0).to_numpy(dtype=int),
                                  data.predicted.to_numpy(dtype=int), data.score.to_numpy(dtype=float))

        by_origin = {}
        for origin in ("real", "simulated", "drawn"):
            subset = selected[selected.origin.eq(origin)]
            value = metrics(subset)
            value["reason"] = None if len(subset) else "origin excluded from frozen real-only validation split"
            value["source_instances"] = int(subset.instance_id.nunique())
            value["well_ids"] = int(subset.well_id.nunique())
            by_origin[origin] = value
        by_family = []
        for family in range(1, 10):
            subset = selected[selected.event_family.eq(family)]
            count = len(subset)
            detected = int(subset.predicted.eq(1).sum())
            by_family.append({"event_family": family, "windows": count, "detected_windows": detected,
                              "missed_windows": count - detected,
                              "recall": detected / count if count else None,
                              "seen_in_training": family in train_families,
                              "source_instances": int(subset.instance_id.nunique()),
                              "well_ids": int(subset.well_id.nunique()),
                              "status": "evaluated_binary_detection" if count else "no_validation_support"})
        by_phase = []
        for phase in ("normal", "transient", "event"):
            subset = selected[selected.phase.eq(phase)]
            by_phase.append({"phase": phase, "windows": len(subset),
                             "positive_decisions": int(subset.predicted.eq(1).sum()),
                             "positive_fraction": float(subset.predicted.eq(1).mean()) if len(subset) else None})
        by_well = []
        for well, subset in selected.groupby("well_id", sort=True):
            by_well.append({"well_id": well, **metrics(subset)})
        models[model] = {
            "validation": metrics(selected), "by_origin": by_origin, "by_family": by_family,
            "by_phase": by_phase, "by_well": by_well,
            "false_alerts": false_alert_metrics(rows, raw_validation, stride_rows, cadence_seconds),
            "coverage": {"all_validation_endpoints": len(rows), "eligible_windows": len(selected),
                         "unknown_target_windows": int(rows.event_family.isna().sum()),
                         "unavailable_input_windows": int((~rows.has_input).sum())},
        }
    return {"task": "binary_normal_vs_documented_undesirable", "partition": "validation",
            "development_diagnostic": True, "models": models,
            "metric_definitions": {"average_precision": "noninterpolated average_precision_score",
                                   "pr_auc_trapezoidal": "trapezoidal area of precision-recall curve, reported separately",
                                   "confusion_matrix": "rows=true, columns=predicted; order normal, abnormal",
                                   "undefined": "null with denominator/status explanation; never invented zero support"}}


def failure_examples(predictions: pd.DataFrame, limit_per_kind_family: int = 3) -> pd.DataFrame:
    _validation_frame(predictions)
    records = []
    for model, rows in predictions[predictions.eligible].groupby("model", sort=True):
        for family, subset in rows.groupby("event_family", sort=True):
            error = subset.predicted.ne(int(family > 0))
            failed = subset[error].sort_values(["score", "instance_id", "timestamp"],
                                              ascending=[family > 0, True, True], kind="stable")
            for _, row in failed.head(limit_per_kind_family).iterrows():
                records.append({"model": model, "error": "false_negative" if family > 0 else "false_positive",
                                "event_family": int(family), "raw_class": int(row.raw_class),
                                "phase": row.phase, "score": float(row.score), "predicted": int(row.predicted),
                                "window_id": row.window_id, "well_id": row.well_id,
                                "instance_id": row.instance_id, "source_path": row.source_path,
                                "window_start": row.window_start.isoformat(), "timestamp": row.timestamp.isoformat()})
    return pd.DataFrame(records)
