"""Baseline behavior checks on explicitly synthetic fixtures, not model evidence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.train_baseline import (ISOLATION_PARAMETERS, LOGISTIC_PARAMETERS, PartitionData,
                               _load_local_models, _serialize_models, fit_models,
                               predict_models, sha256)
from ml.evaluate import false_alert_metrics


def partition(name: str = "train", size: int = 512) -> PartitionData:
    rng = np.random.default_rng(731)
    positive = np.arange(size) >= size // 2
    index = pd.Index([f"{name}-{i}" for i in range(size)], name="window_id")
    features = pd.DataFrame({"P-TPT__mean": positive.astype(float) * 2 + rng.normal(0, .4, size),
                             "P-TPT__trend": rng.normal(0, .3, size)}, index=index)
    targets = pd.DataFrame(index=index)
    targets["raw_class"] = pd.array(np.where(positive, 3, 0), dtype="Int16")
    targets["raw_state"] = pd.array(np.zeros(size, dtype=int), dtype="Int16")
    targets["event_family"] = targets.raw_class.copy()
    targets["phase"] = np.where(positive, "event", "normal")
    targets["supervised_eligible"] = True
    metadata = pd.DataFrame({"partition": name, "instance_id": f"fixture-{name}", "group_id": f"group-{name}",
                             "origin": "real", "well_id": "WELL-00001" if name == "train" else "WELL-00002",
                             "source_path": f"fixture/{name}", "sha256": "0" * 64,
                             "timestamp": pd.date_range("2020-01-01", periods=size, freq="10s"),
                             "window_start": pd.date_range("2019-12-31 23:59:01", periods=size, freq="10s"),
                             "endpoint_position": np.arange(size) * 10 + 59}, index=index)
    quality = pd.DataFrame({"P-TPT__observed_count": 60}, index=index)
    return PartitionData(features, targets, metadata, quality, pd.Series(True, index=index), name)


@pytest.fixture(scope="module")
def fitted():
    return fit_models(partition())


def test_fixed_parameters_and_normal_only_isolation(fitted):
    train = partition()
    normal_ids = tuple(train.targets.index[train.targets.event_family.eq(0)])
    assert fitted["isolation_forest"].fit_window_ids == normal_ids
    assert fitted["logistic_regression"].fit_window_ids == tuple(train.features.index)
    assert fitted["train_majority"].constant == 0
    assert fitted["always_normal"].constant == 0
    for key, value in LOGISTIC_PARAMETERS.items():
        assert fitted["logistic_regression"].estimator.get_params()[key] == value
    for key, value in ISOLATION_PARAMETERS.items():
        assert fitted["isolation_forest"].estimator.get_params()[key] == value
    assert fitted["isolation_forest"].threshold == -fitted["isolation_forest"].estimator.offset_
    assert fitted["isolation_forest"].comparison == "gt"
    assert fitted["logistic_regression"].comparison == "ge"


def test_unknown_training_targets_never_fit_estimators():
    train = partition(size=600)
    targets = train.targets.copy()
    targets.loc[targets.index[-20:], ["raw_class", "event_family"]] = pd.NA
    targets.loc[targets.index[-20:], "phase"] = "unknown"
    changed = replace(train, targets=targets)
    models = fit_models(changed)
    assert len(models["logistic_regression"].fit_window_ids) == 580
    assert len(models["isolation_forest"].fit_window_ids) == 300
    assert not set(targets.index[-20:]) & set(models["logistic_regression"].fit_window_ids)


def test_holdout_fitting_rejected():
    with pytest.raises(ValueError, match="train only"):
        fit_models(partition("validation"))


def test_test_partition_rejected_before_fit():
    with pytest.raises(ValueError, match="train or validation"):
        fit_models(partition("test"))


def test_prediction_is_validation_only(fitted):
    with pytest.raises(ValueError, match="validation only"):
        predict_models(fitted, partition("train"))


def test_unknown_validation_targets_still_get_continuity_scores(fitted):
    validation = partition("validation")
    targets = validation.targets.copy()
    targets.loc[targets.index[:10], ["raw_class", "event_family"]] = pd.NA
    targets.loc[targets.index[:10], "phase"] = "unknown"
    output = predict_models(fitted, replace(validation, targets=targets))
    unknown = output[output.event_family.isna()]
    assert len(unknown) == 40
    assert unknown.score.notna().all() and unknown.predicted.notna().all()
    assert not unknown.eligible.any()


def test_all_unavailable_validation_abstains(fitted):
    validation = partition("validation")
    quality = validation.quality.copy() * 0
    no_evidence = pd.Series(False, index=validation.features.index)
    output = predict_models(fitted, replace(validation, quality=quality, evidence_mask=no_evidence))
    assert output.score.isna().all() and output.predicted.isna().all()
    assert not output.eligible.any() and not output.has_input.any()


@pytest.mark.parametrize("column", ["class", "state", "well_id", "source_path", "timestamp"])
def test_metadata_columns_rejected_as_features(column):
    train = partition()
    features = train.features.rename(columns={"P-TPT__mean": column})
    with pytest.raises(ValueError, match="not allowed feature"):
        fit_models(replace(train, features=features))


def test_undocumented_target_rejected():
    train = partition()
    targets = train.targets.copy()
    targets.loc[targets.index[0], "raw_class"] = 103
    with pytest.raises(ValueError, match="Undocumented"):
        fit_models(replace(train, targets=targets))


def test_nonfinite_normalized_feature_rejected():
    train = partition()
    features = train.features.copy()
    features.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        fit_models(replace(train, features=features))


def test_validation_targets_cannot_change_predictions(fitted):
    original = partition("validation")
    first = predict_models(fitted, original)
    targets = original.targets.copy()
    mask = targets.event_family.eq(3)
    targets.loc[mask, ["event_family", "raw_class"]] = 7
    second = predict_models(fitted, replace(original, targets=targets))
    pd.testing.assert_frame_equal(first[["model", "window_id", "score", "predicted"]],
                                  second[["model", "window_id", "score", "predicted"]])


def test_fixed_seed_refit_is_deterministic(fitted):
    repeated = fit_models(partition())
    first = predict_models(fitted, partition("validation"))
    second = predict_models(repeated, partition("validation"))
    pd.testing.assert_frame_equal(first, second, check_exact=True)


def test_local_model_reload_reproduces_scores(fitted, tmp_path):
    path = tmp_path / "models.joblib"
    joblib.dump(_serialize_models(fitted), path, compress=3)
    restored = _load_local_models(path, sha256(path))
    pd.testing.assert_frame_equal(predict_models(fitted, partition("validation")),
                                  predict_models(restored, partition("validation")), check_exact=True)


def test_model_hash_checked_before_deserialization(fitted, tmp_path, monkeypatch):
    path = tmp_path / "models.joblib"
    joblib.dump(_serialize_models(fitted), path, compress=3)
    monkeypatch.setattr(joblib, "load", lambda _: pytest.fail("Unverified artifact was deserialized"))
    with pytest.raises(ValueError, match="hash mismatch"):
        _load_local_models(path, "0" * 64)


@pytest.mark.parametrize("cadence", [0.0, -1.0, np.nan, np.inf, True, "1"])
def test_false_alarm_accounting_rejects_invalid_cadence(fitted, cadence):
    rows = predict_models({"always_normal": fitted["always_normal"]}, partition("validation"))
    with pytest.raises(ValueError, match="positive stride/cadence"):
        false_alert_metrics(rows, {}, cadence_seconds=cadence)


@pytest.mark.parametrize("position", [-1, 0.25, np.nan])
def test_false_alarm_accounting_rejects_invalid_positions(fitted, position):
    rows = predict_models({"always_normal": fitted["always_normal"]}, partition("validation"))
    rows["endpoint_position"] = position
    with pytest.raises(ValueError, match="positions"):
        false_alert_metrics(rows, {})
