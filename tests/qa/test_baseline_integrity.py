"""Independent Phase 4 metric, chronology and estimator-boundary checks.

Fixtures are explicitly synthetic and are not reported as dataset performance.
"""
from __future__ import annotations

from dataclasses import replace
import importlib
import hashlib
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.evaluate import binary_metrics, evaluate_predictions, false_alert_metrics  # noqa: E402


def raw_source(labels: list, seconds: list[int] | None = None) -> pd.DataFrame:
    seconds = list(range(len(labels))) if seconds is None else seconds
    index = pd.DatetimeIndex(pd.Timestamp("2020-01-01") + pd.to_timedelta(seconds, unit="s"),
                             name="timestamp")
    return pd.DataFrame({"class": pd.array(labels, dtype="Int16")}, index=index)


def decisions(raw: pd.DataFrame, positions: list[int], predictions: list[int | None],
              *, source: str = "instance-a", model: str = "fixture") -> pd.DataFrame:
    records = []
    transients = {101: 1, 102: 2, 105: 5, 106: 6, 107: 7, 108: 8, 109: 9}
    for position, predicted in zip(positions, predictions, strict=True):
        label = raw["class"].iloc[position]
        family = pd.NA if pd.isna(label) else transients.get(int(label), int(label))
        phase = ("unknown" if pd.isna(label) else "transient" if int(label) in transients
                 else "normal" if int(label) == 0 else "event")
        available = predicted is not None
        records.append({"model": model, "window_id": f"{source}:{position}",
                        "instance_id": source, "partition": "validation", "origin": "real",
                        "well_id": "WELL-00001", "timestamp": raw.index[position],
                        "window_start": raw.index[position], "endpoint_position": position,
                        "source_path": f"fixture/{source}.parquet", "sha256": "1" * 64,
                        "raw_class": label, "event_family": family, "phase": phase,
                        "has_input": available, "eligible": available and pd.notna(family),
                        "score": 0.8 if predicted == 1 else 0.2 if predicted == 0 else np.nan,
                        "predicted": predicted if available else pd.NA})
    frame = pd.DataFrame(records)
    for name in ("raw_class", "event_family", "predicted"):
        frame[name] = pd.array(frame[name], dtype="Int16")
    return frame


def test_metric_arithmetic_and_two_distinct_pr_areas():
    result = binary_metrics(np.array([0, 0, 1, 1]), np.array([0, 1, 0, 1]),
                            np.array([0.1, 0.8, 0.2, 0.9]))
    assert result["confusion_matrix"] == [[1, 1], [1, 1]]
    assert result["precision"] == result["recall"] == result["f1"] == 0.5
    assert result["average_precision"] == pytest.approx(5 / 6)
    assert result["pr_auc_trapezoidal"] == pytest.approx(19 / 24)


def test_constant_score_has_prevalence_ap_not_ranking_skill():
    result = binary_metrics(np.array([0, 0, 0, 1]), np.ones(4, dtype=int), np.ones(4))
    assert result["precision"] == 0.25
    assert result["recall"] == 1.0
    assert result["f1"] == 0.4
    assert result["average_precision"] == 0.25
    assert result["pr_auc_trapezoidal"] == 0.625


def test_no_positive_decisions_does_not_fabricate_precision():
    result = binary_metrics(np.array([0, 1]), np.array([0, 0]), np.zeros(2))
    assert result["precision"] is None
    assert result["recall"] == result["f1"] == 0.0
    assert result["undefined"]["precision"] == "no positive predictions"


@pytest.mark.parametrize("labels", [[], [0, 0], [1, 1]])
def test_absent_target_class_has_undefined_ranking_metrics(labels):
    result = binary_metrics(np.array(labels, dtype=int), np.zeros(len(labels), dtype=int),
                            np.zeros(len(labels)))
    assert result["average_precision"] is None
    assert result["pr_auc_trapezoidal"] is None
    if not labels:
        assert result["status"] == "not_evaluated"
        assert result["precision"] is result["recall"] is result["f1"] is None


@pytest.mark.parametrize("truth,predicted,scores", [
    ([0], [0, 1], [0.2]), ([2], [0], [0.2]), ([0], [2], [0.2]),
    ([0], [0], [float("nan")]), ([0], [0], [float("inf")]),
    ([[0]], [0], [0.2]),
])
def test_malformed_metric_arrays_rejected(truth, predicted, scores):
    with pytest.raises(ValueError):
        binary_metrics(np.asarray(truth), np.asarray(predicted), np.asarray(scores))


def test_observed_false_onset_and_exact_partial_tail_exposure():
    raw = raw_source([0] * 23)
    rows = decisions(raw, [0, 10, 20], [0, 1, 0])
    result = false_alert_metrics(rows, {"instance-a": raw})
    assert result["confirmed_false_onsets"] == 1
    assert result["normal_seconds"] == result["monitored_seconds"] == 23
    assert result["normal_alarm_seconds"] == 10
    assert result["false_alerts_per_normal_hour"] == pytest.approx(3600 / 23)


def test_always_positive_is_censored_but_has_full_normal_alarm_occupancy():
    raw = raw_source([0] * 20)
    result = false_alert_metrics(decisions(raw, [0, 10], [1, 1]), {"instance-a": raw})
    assert result["confirmed_false_onsets"] == 0
    assert result["censored_positive_starts"] == 1
    assert result["normal_alarm_seconds"] == result["normal_seconds"] == 20
    assert result["normal_alarm_occupancy_fraction"] == 1.0


def test_unknown_target_does_not_reset_positive_episode():
    raw = raw_source([0] * 10 + [pd.NA] * 10 + [0] * 10)
    result = false_alert_metrics(decisions(raw, [0, 10, 20], [0, 1, 1]), {"instance-a": raw})
    assert result["unknown_label_onsets"] == 1
    assert result["confirmed_false_onsets"] == result["censored_positive_starts"] == 0
    assert result["normal_alarm_seconds"] == 10
    assert result["normal_alarm_occupancy_fraction"] == 0.5


def test_target_recovery_does_not_invent_a_false_alert_onset():
    raw = raw_source([1] * 10 + [0] * 20)
    result = false_alert_metrics(decisions(raw, [0, 10, 20], [1, 1, 1]), {"instance-a": raw})
    assert result["confirmed_false_onsets"] == 0
    assert result["censored_positive_starts"] == 1
    assert result["normal_alarm_occupancy_fraction"] == 1.0


def test_unavailable_input_censors_next_positive_and_excludes_unmonitored_time():
    raw = raw_source([0] * 30)
    result = false_alert_metrics(decisions(raw, [0, 10, 20], [0, None, 1]), {"instance-a": raw})
    assert result["monitored_seconds"] == 20
    assert result["normal_alarm_seconds"] == 10
    assert result["confirmed_false_onsets"] == 0
    assert result["censored_positive_starts"] == 1


def test_no_evidence_has_no_measurable_false_alert_rate():
    raw = raw_source([0] * 20)
    result = false_alert_metrics(decisions(raw, [0, 10], [None, None]), {"instance-a": raw})
    assert result["monitored_seconds"] == 0
    assert result["false_alerts_per_normal_hour"] is None
    assert result["false_alerts_per_monitored_replay_hour"] is None


def test_source_boundary_never_connects_alert_state():
    raw = raw_source([0] * 20)
    rows = pd.concat([decisions(raw, [0, 10], [0, 0], source="a"),
                      decisions(raw, [0, 10], [1, 1], source="b")], ignore_index=True)
    result = false_alert_metrics(rows, {"a": raw, "b": raw})
    assert result["confirmed_false_onsets"] == 0
    assert result["censored_positive_starts"] == 1
    assert result["normal_seconds"] == 40


def test_hold_interval_stops_at_next_decision_without_double_counting():
    raw = raw_source([0] * 15)
    result = false_alert_metrics(decisions(raw, [0, 5], [1, 0]), {"instance-a": raw})
    assert result["monitored_seconds"] == 15
    assert result["normal_alarm_seconds"] == 5


def test_internal_raw_gap_censors_despite_nominal_endpoint_spacing():
    raw = raw_source([0] * 15, list(range(5)) + list(range(6, 16)))
    result = false_alert_metrics(decisions(raw, [0, 9], [0, 1]), {"instance-a": raw})
    assert result["monitored_seconds"] == 11
    assert result["confirmed_false_onsets"] == 0
    assert result["censored_positive_starts"] == 1


@pytest.mark.parametrize("column,value", [
    ("partition", "test"), ("event_family", 9), ("phase", "event"),
    ("eligible", False), ("has_input", "yes"), ("raw_class", 104),
])
def test_prediction_contract_rejects_silent_target_or_mask_changes(column, value):
    raw = raw_source([0] * 10)
    rows = decisions(raw, [0], [0])
    if column == "has_input":
        rows[column] = rows[column].astype(object)
    rows.loc[0, column] = value
    with pytest.raises(ValueError):
        evaluate_predictions(rows, {0, 1}, {"instance-a": raw})


def test_models_must_share_unknown_windows_as_well_as_eligible_windows():
    raw = raw_source([pd.NA] * 10 + [0] * 10)
    first = decisions(raw, [0, 10], [0, 0], model="first")
    second = decisions(raw, [10], [0], model="second")
    with pytest.raises(ValueError):
        evaluate_predictions(pd.concat([first, second], ignore_index=True), {0, 1}, {"instance-a": raw})


def test_models_cannot_reassign_well_identity_for_same_window():
    raw = raw_source([0] * 10)
    first = decisions(raw, [0], [0], model="first")
    second = decisions(raw, [0], [0], model="second")
    second["well_id"] = "WELL-00099"
    with pytest.raises(ValueError):
        evaluate_predictions(pd.concat([first, second], ignore_index=True), {0, 1}, {"instance-a": raw})


def test_source_and_family_absence_remain_not_evaluated():
    raw = raw_source([0] * 10 + [102] * 10)
    result = evaluate_predictions(decisions(raw, [0, 10], [0, 0]), {0, 3}, {"instance-a": raw})
    model = result["models"]["fixture"]
    for origin in ("simulated", "drawn"):
        assert model["by_origin"][origin]["windows"] == 0
        assert model["by_origin"][origin]["status"] == "not_evaluated"
        assert model["by_origin"][origin]["recall"] is None
    family = {row["event_family"]: row for row in model["by_family"]}
    assert family[2]["windows"] == 1 and family[2]["recall"] == 0.0
    assert family[2]["seen_in_training"] is False
    assert family[3]["recall"] is None and family[3]["status"] == "no_validation_support"


@pytest.fixture(scope="module")
def partition_inputs():
    """Build a small genuine preprocessing boundary with synthetic sources."""
    from ml.data_pipeline import (CausalFeaturePipeline, Instance, PipelineConfig,
                                  SourceMetadata, SplitConfig, make_split)
    instances = []
    for number in range(1, 4):
        frame = pd.DataFrame({"P-TPT": np.linspace(0, 1, 20) + number,
                              "class": pd.array([0] * 10 + [1] * 8 + [pd.NA] * 2, dtype="Int16"),
                              "state": pd.array([0] * 20, dtype="Int16")},
                             index=pd.date_range("2020-01-01", periods=20, freq="s", name="timestamp"))
        source = SourceMetadata(instance_id=f"qa-instance-{number}", source_path=f"fixture/{number}",
                                sha256=hashlib.sha256(str(number).encode()).hexdigest(),
                                origin="real", well_id=f"WELL-{number:05d}")
        instances.append(Instance(source, frame))
    split = make_split(instances, SplitConfig(seed=42, required_families=(0, 1)))
    pipeline = CausalFeaturePipeline(PipelineConfig(window_rows=2, stride_rows=1), ("P-TPT",))
    batch = pipeline.build(instances, split)
    pipeline.fit(batch.subset("train"), split)
    features = pipeline.transform(batch, split)
    return features, batch, split


def selected_partitions(partition_inputs):
    module = importlib.import_module("ml.train_baseline")
    features, batch, split = partition_inputs
    return module.select_training_partitions(features, batch.targets, batch.metadata,
                                               batch.quality, tuple(features.columns), split)


def quiet_fixture_fit(train):
    module = importlib.import_module("ml.train_baseline")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="max_samples .*", category=UserWarning)
        return module.fit_models(train)


@pytest.fixture(scope="module")
def fitted_fixture(partition_inputs):
    train, validation = selected_partitions(partition_inputs)
    return train, validation, quiet_fixture_fit(train)


def test_test_values_are_discarded_before_numeric_validation_and_estimator_access(partition_inputs):
    module = importlib.import_module("ml.train_baseline")
    features, batch, split = partition_inputs
    train, validation = selected_partitions(partition_inputs)
    poisoned_features = features.copy()
    poisoned_targets = batch.targets.copy()
    poisoned_quality = batch.quality.copy()
    test = batch.metadata.partition.eq("test")
    poisoned_features.loc[test] = np.inf
    poisoned_targets.loc[test, "event_family"] = 999
    for column in poisoned_quality:
        if pd.api.types.is_bool_dtype(poisoned_quality[column]):
            poisoned_quality.loc[test, column] = ~poisoned_quality.loc[test, column]
        else:
            poisoned_quality.loc[test, column] = -999
    after_train, after_validation = module.select_training_partitions(
        poisoned_features, poisoned_targets, batch.metadata, poisoned_quality,
        tuple(features.columns), split)
    for before, after in ((train, after_train), (validation, after_validation)):
        pd.testing.assert_frame_equal(before.features, after.features)
        pd.testing.assert_frame_equal(before.targets, after.targets)
        pd.testing.assert_frame_equal(before.quality, after.quality)
    first = quiet_fixture_fit(train)
    second = quiet_fixture_fit(after_train)
    pd.testing.assert_frame_equal(module.predict_models(first, validation),
                                  module.predict_models(second, after_validation), check_exact=True)
    assert set(first["logistic_regression"].fit_window_ids).isdisjoint(batch.metadata.index[test])
    assert set(first["isolation_forest"].fit_window_ids).isdisjoint(batch.metadata.index[test])


def test_estimator_fit_row_ids_match_labeled_train_and_known_normal_only(fitted_fixture):
    train, _, models = fitted_fixture
    expected_lr = tuple(str(i) for i in train.features.index[train.eligible])
    expected_if = tuple(str(i) for i in train.features.index[train.eligible & train.targets.event_family.eq(0)])
    assert models["logistic_regression"].fit_window_ids == expected_lr
    assert models["isolation_forest"].fit_window_ids == expected_if
    assert len(expected_lr) > len(expected_if) >= 2
    assert set(expected_lr).isdisjoint(train.features.index[train.targets.event_family.isna()])
    assert models["always_normal"].fit_window_ids == ()


def test_isolation_fit_receives_only_the_independently_selected_normal_rows(partition_inputs, monkeypatch):
    module = importlib.import_module("ml.train_baseline")
    train, _ = selected_partitions(partition_inputs)
    observed = []
    original = module.IsolationForest.fit

    def capture(estimator, values, *args, **kwargs):
        observed.append(tuple(values.index))
        return original(estimator, values, *args, **kwargs)

    monkeypatch.setattr(module.IsolationForest, "fit", capture)
    quiet_fixture_fit(train)
    expected = tuple(train.features.index[train.evidence_mask & train.targets.raw_class.eq(0)])
    assert observed == [expected]


def test_validation_is_rejected_by_fit_and_test_is_rejected_by_prediction(fitted_fixture):
    module = importlib.import_module("ml.train_baseline")
    _, validation, models = fitted_fixture
    with pytest.raises(ValueError):
        module.fit_models(validation)
    poisoned = validation.metadata.copy()
    poisoned["partition"] = "test"
    with pytest.raises(ValueError):
        module.predict_models(models, replace(validation, metadata=poisoned, partition="test"))


@pytest.mark.parametrize("column", ["class", "state", "well_id", "timestamp", "source_path"])
def test_sensor_feature_boundary_rejects_labels_and_metadata(partition_inputs, column):
    train, _ = selected_partitions(partition_inputs)
    features = train.features.copy()
    features[column] = 0.0
    with pytest.raises(ValueError):
        quiet_fixture_fit(replace(train, features=features))


@pytest.mark.parametrize("column,value", [("event_family", 0), ("phase", "normal")])
def test_training_target_mapping_cannot_be_forged_independently_of_raw_label(partition_inputs, column, value):
    train, _ = selected_partitions(partition_inputs)
    targets = train.targets.copy()
    row = targets.index[targets.raw_class.eq(1)][0]
    targets.loc[row, column] = value
    with pytest.raises(ValueError):
        quiet_fixture_fit(replace(train, targets=targets))


def test_fabricated_evidence_mask_is_rejected(partition_inputs):
    train, _ = selected_partitions(partition_inputs)
    quality = train.quality.copy()
    quality["P-TPT__observed_count"] = 0
    with pytest.raises(ValueError):
        quiet_fixture_fit(replace(train, quality=quality))


def test_all_unavailable_validation_returns_abstentions_without_estimator_calls(fitted_fixture, monkeypatch):
    module = importlib.import_module("ml.train_baseline")
    _, validation, models = fitted_fixture
    quality = validation.quality.copy()
    quality["P-TPT__observed_count"] = 0
    unavailable = replace(validation, quality=quality,
                          evidence_mask=pd.Series(False, index=validation.features.index))

    def forbidden(*args, **kwargs):
        raise AssertionError("Estimator must not receive a zero-evidence prediction batch")

    monkeypatch.setattr(models["logistic_regression"].estimator, "predict_proba", forbidden)
    monkeypatch.setattr(models["isolation_forest"].estimator, "score_samples", forbidden)
    rows = module.predict_models(models, unavailable)
    assert len(rows) == len(validation.features) * len(models)
    assert rows.predicted.isna().all() and rows.score.isna().all()
    assert not rows.has_input.any() and not rows.eligible.any()


def test_unknown_validation_targets_still_receive_predictions_for_continuity(fitted_fixture):
    module = importlib.import_module("ml.train_baseline")
    _, validation, models = fitted_fixture
    rows = module.predict_models(models, validation)
    unknown = rows.raw_class.isna()
    assert unknown.any()
    assert rows.loc[unknown, "predicted"].notna().all()
    assert rows.loc[unknown, "has_input"].all() and not rows.loc[unknown, "eligible"].any()


def test_validation_target_and_status_changes_do_not_change_model_scores(fitted_fixture):
    module = importlib.import_module("ml.train_baseline")
    _, validation, models = fitted_fixture
    before = module.predict_models(models, validation)
    targets = validation.targets.copy()
    targets["raw_class"] = pd.array([0] * len(targets), dtype="Int16")
    targets["event_family"] = pd.array([0] * len(targets), dtype="Int16")
    targets["phase"] = "normal"
    targets["raw_state"] = pd.array([8] * len(targets), dtype="Int16")
    targets["supervised_eligible"] = True
    after = module.predict_models(models, replace(validation, targets=targets))
    pd.testing.assert_frame_equal(before[["model", "window_id", "score", "predicted"]],
                                  after[["model", "window_id", "score", "predicted"]], check_exact=True)


def test_fixed_thresholds_use_train_offset_and_explicit_tie_rules(fitted_fixture):
    module = importlib.import_module("ml.train_baseline")
    _, validation, fitted = fitted_fixture
    assert fitted["logistic_regression"].threshold == 0.5
    assert fitted["isolation_forest"].threshold == -fitted["isolation_forest"].estimator.offset_

    class LogisticTie:
        classes_ = np.array([0, 1])

        def predict_proba(self, values):
            return np.full((len(values), 2), 0.5)

    class IsolationTie:
        def score_samples(self, values):
            return np.full(len(values), -0.5)

    models = {
        "logistic_regression": module.FittedBaseline("logistic_regression", LogisticTie(), 0.5, "ge", None, ()),
        "isolation_forest": module.FittedBaseline("isolation_forest", IsolationTie(), 0.5, "gt", None, ()),
    }
    rows = module.predict_models(models, validation)
    assert rows.loc[rows.model.eq("logistic_regression"), "predicted"].eq(1).all()
    assert rows.loc[rows.model.eq("isolation_forest"), "predicted"].eq(0).all()
