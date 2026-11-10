"""Independent Phase 5 selection/inference checks using synthetic data only."""
from __future__ import annotations

from types import SimpleNamespace
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from ml.features import feature_names
from ml.predict import Predictor, estimator_scores
from ml.train_baseline import PartitionData
from ml.training import phase5


class RecordingEstimator:
    classes_ = np.array([0, 1])

    def __init__(self):
        self.inputs = []

    def predict_proba(self, values):
        self.inputs.append(values.copy())
        positive = np.clip(values.iloc[:, 0].to_numpy(float), 0, 1)
        return np.column_stack((1 - positive, positive))


@pytest.fixture
def predictor():
    sensors = ("P-PDG", "P-TPT")
    retained = ("P-PDG__mean", "P-TPT__mean")
    state = SimpleNamespace(sensor_names=sensors, retained_features=retained,
                            input_feature_names=feature_names(sensors),
                            medians=np.array([0.1, 0.2]), means=np.zeros(2), scales=np.ones(2),
                            config=SimpleNamespace(cadence_seconds=1.0, window_rows=3, stride_rows=1))
    return Predictor(RecordingEstimator(), "logistic_regression", 0.5,
                     SimpleNamespace(state=state), {"model_version": "qa-synthetic"})


def feature_frame(values=(0.1, 0.5, 0.9)):
    return pd.DataFrame({"P-PDG__mean": values, "P-TPT__mean": np.zeros(len(values))},
                        index=pd.Index([f"w{i}" for i in range(len(values))]))


def raw_frame(values=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)):
    return pd.DataFrame({"P-PDG": values, "P-TPT": np.zeros(len(values))},
                        index=pd.date_range("2020-01-01", periods=len(values), freq="s"))


def test_prediction_threshold_tie_is_positive_and_unknown_evidence_abstains(predictor):
    x = feature_frame()
    available = pd.Series([True, True, False], index=x.index)
    result = predictor.predict_features(x, available)
    assert result.predicted.iloc[:2].tolist() == [0, 1]
    assert pd.isna(result.predicted.iloc[2]) and pd.isna(result.score.iloc[2])
    assert result.abstention_reason.iloc[2] == "missing_required_sensors"
    assert predictor.estimator.inputs[0].index.tolist() == ["w0", "w1"]
    assert result.model_version.eq("qa-synthetic").all()


def test_all_unavailable_inputs_never_invoke_estimator(predictor):
    x = feature_frame()
    result = predictor.predict_features(x, pd.Series(False, index=x.index))
    assert not predictor.estimator.inputs
    assert result.score.isna().all() and result.predicted.isna().all()


@pytest.mark.parametrize("mutation", ["label", "reorder", "nonfinite", "duplicate", "mask_dtype", "mask_index"])
def test_normalized_inference_rejects_malformed_boundary(predictor, mutation):
    x = feature_frame()
    available = pd.Series(True, index=x.index)
    if mutation == "label":
        x["class"] = 0
    elif mutation == "reorder":
        x = x.iloc[:, ::-1]
    elif mutation == "nonfinite":
        x.iloc[0, 0] = np.inf
    elif mutation == "duplicate":
        x.index = ["w0", "w0", "w2"]
        available.index = x.index
    elif mutation == "mask_dtype":
        available = available.astype(int)
    else:
        available = available.iloc[::-1]
    with pytest.raises(ValueError):
        predictor.predict_features(x, available)
    assert not predictor.estimator.inputs


def test_raw_inference_is_causal_and_normalization_is_frozen(predictor):
    raw = raw_frame()
    first = predictor.predict_instance(raw)
    changed = raw.copy()
    changed.iloc[4:] = 0.99
    second = predictor.predict_instance(changed)
    pd.testing.assert_frame_equal(first.iloc[:2], second.iloc[:2])
    np.testing.assert_allclose(first.score.to_numpy(), [0.2, 0.3, 0.4, 0.5])
    assert first.endpoint_position.tolist() == [2, 3, 4, 5]
    assert first.window_start.tolist() == raw.index[:4].tolist()
    np.testing.assert_array_equal(predictor.pipeline.state.medians, [0.1, 0.2])


def test_raw_gap_resets_window_and_never_bridges_observations(predictor):
    raw = raw_frame()
    raw.index = raw.index[:3].append(raw.index[3:] + pd.Timedelta(seconds=20))
    result = predictor.predict_instance(raw)
    assert result.endpoint_position.tolist() == [2, 5]
    np.testing.assert_allclose(result.score.to_numpy(), [0.2, 0.5])
    assert result.window_start.tolist() == [raw.index[0], raw.index[3]]


def test_missing_raw_observations_use_only_saved_median_and_allmissing_abstains(predictor):
    raw = raw_frame()
    raw.iloc[:3, 0] = np.nan
    result = predictor.predict_instance(raw)
    assert result.score.iloc[0] == pytest.approx(0.1)
    raw.iloc[:] = np.nan
    result = predictor.predict_instance(raw)
    assert result.predicted.isna().all() and result.score.isna().all()


def test_insufficient_history_is_empty_not_normal_prediction(predictor):
    result = predictor.predict_instance(raw_frame((0.1, 0.2)))
    assert result.empty and result.attrs["empty_reason"] == "insufficient_history"
    assert not predictor.estimator.inputs


@pytest.mark.parametrize("mutation", ["class", "state", "origin", "infinity", "duplicate_time", "reverse", "boolean", "faster_cadence"])
def test_sensor_boundary_rejects_labels_metadata_and_invalid_time(predictor, mutation):
    raw = raw_frame()
    if mutation in {"class", "state", "origin"}:
        raw[mutation] = 0
    elif mutation == "infinity":
        raw.iloc[0, 0] = np.inf
    elif mutation == "duplicate_time":
        raw.index = raw.index[:1].append(raw.index[:-1])
    elif mutation == "reverse":
        raw = raw.iloc[::-1]
    elif mutation == "boolean":
        raw["P-PDG"] = True
    else:
        raw.index = pd.date_range("2020-01-01", periods=len(raw), freq="500ms")
    with pytest.raises(ValueError):
        predictor.predict_instance(raw)
    assert not predictor.estimator.inputs


def test_positive_probability_uses_class_identity_not_column_position():
    class Reversed:
        classes_ = np.array([1, 0])

        def predict_proba(self, x):
            return np.tile([0.8, 0.2], (len(x), 1))

    np.testing.assert_array_equal(estimator_scores(Reversed(), "xgboost", feature_frame()), [0.8] * 3)


@pytest.mark.parametrize("values", [[0.2], [0.2, 0.3, np.nan], [0.2, 0.3, 1.1]])
def test_estimator_probability_shape_and_range_are_validated(values):
    class Malformed:
        classes_ = np.array([0, 1])

        def predict_proba(self, x):
            return np.column_stack((1 - np.array(values), values))

    with pytest.raises(ValueError):
        estimator_scores(Malformed(), "catboost", feature_frame())


def test_search_grid_has_exactly_eight_bounded_seeded_single_thread_candidates():
    specs = phase5.candidate_specs()
    assert len(specs) == len({s["candidate_id"] for s in specs}) == 8
    assert {(s["kind"], s["parameters"]["depth"], s["parameters"]["learning_rate"])
            for s in specs} == {(kind, depth, rate) for kind in ("catboost", "xgboost")
                               for depth in (3, 6) for rate in (0.05, 0.1)}
    assert all(s["parameters"]["trees"] == 200 and s["parameters"]["seed"] == 42
               and s["parameters"]["threads"] == 1 and s["parameters"]["positive_weight"] == 2
               for s in specs)


def test_threshold_accounts_for_normal_hold_after_unknown_endpoint():
    scores = np.array([0.1, 0.6, 0.8, 0.9, np.nan])
    y = np.array([0, np.nan, 1, 1, 0])
    weights = np.array([95, 5, 0, 0, 0])
    eligible = np.isfinite(y) & np.isfinite(scores)
    choice = phase5.choose_threshold(scores, y, weights, eligible)
    assert len(choice["grid"]) <= 203
    for row in choice["grid"]:
        decision = np.isfinite(scores) & (scores >= row["threshold"])
        expected = weights[decision].sum() / 100
        assert row["normal_alarm_occupancy_fraction"] == expected
        assert row["recall"] == ((decision & eligible & (y == 1)).sum() / 2)
        assert row["feasible"] == (expected <= 0.05)
    optimum = min((r for r in choice["grid"] if r["feasible"]),
                  key=lambda r: (-r["recall"], r["normal_alarm_occupancy_fraction"], -r["threshold"]))
    assert choice["selected"] == optimum
    assert optimum["recall"] == 1 and optimum["normal_alarm_occupancy_fraction"] == 0


def test_constant_scores_select_allnormal_fallback_under_exposure_cap():
    choice = phase5.choose_threshold(np.ones(4) * 0.5, np.array([0, 0, 1, 1]),
                                     np.array([10, 10, 0, 0]), np.ones(4, bool))
    assert choice["selected"]["threshold"] > 0.5
    assert choice["selected"]["recall"] == 0
    assert choice["selected"]["normal_alarm_occupancy_fraction"] == 0


@pytest.mark.parametrize("mutation", ["no_normal_time", "negative_time", "nonfinite_time", "mask_dtype",
                                     "forged_eligibility", "unknown_positive", "unavailable_exposure", "inf_score",
                                     "bad_label", "no_abnormal", "bad_cap"])
def test_threshold_rejects_invalid_or_unsupported_denominators(mutation):
    scores = np.array([0.1, 0.5, 0.9])
    labels = np.array([0, 0, 1], dtype=float)
    weights = np.array([10, 10, 0], dtype=float)
    eligible = np.ones(3, bool)
    cap = 0.05
    if mutation == "no_normal_time": weights[:] = 0
    elif mutation == "negative_time": weights[0] = -1
    elif mutation == "nonfinite_time": weights[0] = np.nan
    elif mutation == "mask_dtype": eligible = eligible.astype(int)
    elif mutation == "forged_eligibility": eligible[0] = False
    elif mutation == "unknown_positive": labels[-1] = np.nan
    elif mutation == "unavailable_exposure": scores[0] = np.nan; eligible[0] = False
    elif mutation == "inf_score": scores[0] = np.inf
    elif mutation == "bad_label": labels[0] = 2
    elif mutation == "no_abnormal": labels[:] = 0
    else: cap = 1.1
    with pytest.raises(ValueError):
        phase5.choose_threshold(scores, labels, weights, eligible, cap)


def candidate(name, recall=0.8, ap=0.9, occupancy=0.03):
    return dict(candidate_id=name, recall=recall, average_precision=ap,
                normal_alarm_occupancy_fraction=occupancy)


def test_candidate_selection_uses_frozen_order_not_latency_or_input_order():
    rows = [candidate("higher_recall", 0.9, 0.5, 0.05), candidate("higher_ap", 0.8, 0.99, 0),
            candidate("z", 0.9, 0.6, 0.02), candidate("a", 0.9, 0.6, 0.02),
            candidate("lower_occupancy", 0.9, 0.55, 0)]
    rows[3]["single_p95_ms"] = 10**6
    for ordered in (rows, rows[::-1]):
        assert phase5.rank_candidates(ordered)["candidate_id"] == "a"


@pytest.mark.parametrize("rows", [[], [candidate("a"), candidate("a")], [candidate("a", occupancy=0.051)],
                                 [candidate("a", ap=np.nan)], [candidate("a", recall=1.1)]])
def test_candidate_selection_rejects_invalid_records(rows):
    with pytest.raises(ValueError):
        phase5.rank_candidates(rows)


def partition_for(raw, positions, partition="validation"):
    ids = pd.Index([f"w{i}" for i in range(len(positions))], name="window_id")
    features = pd.DataFrame({"P-PDG__mean": np.linspace(0.1, 0.9, len(ids))}, index=ids)
    labels = raw["class"].iloc[positions].to_numpy()
    families = [pd.NA if pd.isna(v) else int(v) - 100 if v >= 100 else int(v) for v in labels]
    phases = ["unknown" if pd.isna(v) else "transient" if v >= 100 else "normal" if v == 0 else "event" for v in labels]
    targets = pd.DataFrame({"raw_class": pd.array(labels, dtype="Int16"),
                            "event_family": pd.array(families, dtype="Int16"), "phase": phases}, index=ids)
    metadata = pd.DataFrame({"instance_id": "qa-source", "partition": partition, "origin": "real",
                             "well_id": "WELL-QA", "timestamp": raw.index[positions],
                             "endpoint_position": positions}, index=ids)
    quality = pd.DataFrame({"P-PDG__observed_count": 1}, index=ids)
    cls = PartitionData if partition == "validation" else phase5.ExperimentalPartition
    return cls(features, targets, metadata, quality, pd.Series(True, index=ids), partition)


@pytest.mark.parametrize("seconds,positions,labels,stride", [
    ([0, 1, 2, 3, 4], [0, 2], [0, 0, 3, 0, 0], 4),
    ([0, 1, 10, 11], [0, 2], [0, 0, 0, 3], 10),
    ([0, 1, 2, 3], [0, 2], [pd.NA, 0, 3, 0], 2),
])
def test_normal_weights_match_full_temporal_accounting(seconds, positions, labels, stride):
    raw = pd.DataFrame({"class": pd.array(labels, dtype="Int16")},
                        index=pd.Timestamp("2020-01-01") + pd.to_timedelta(seconds, unit="s"))
    part = partition_for(raw, positions)
    weights = phase5.normal_exposure_weights(part, {"qa-source": raw}, stride, 1.0)
    predictions = phase5.prediction_frame(part, np.ones(len(positions)), 0.5, "qa")
    result = phase5.evaluate_partition(predictions, {0, 3}, {"qa-source": raw}, "validation", stride, 1.0)
    assert weights.sum() == result["models"]["qa"]["false_alerts"]["normal_seconds"]


@pytest.mark.parametrize("cadence", [0, -1, np.nan, np.inf, True])
def test_normal_exposure_rejects_invalid_cadence(cadence):
    raw = pd.DataFrame({"class": pd.array([0, 3], dtype="Int16")},
                        index=pd.date_range("2020-01-01", periods=2, freq="s"))
    with pytest.raises(ValueError):
        phase5.normal_exposure_weights(partition_for(raw, [0, 1]), {"qa-source": raw}, 1, cadence)


def test_normal_exposure_rejects_finer_cadence_instead_of_overcounting_seconds():
    raw = pd.DataFrame({"class": pd.array([0, 0, 3], dtype="Int16")},
                        index=pd.Timestamp("2020-01-01") + pd.to_timedelta([0, 0.5, 1.5], unit="s"))
    with pytest.raises(ValueError):
        phase5.normal_exposure_weights(partition_for(raw, [0, 2]), {"qa-source": raw}, 2, 1.0)


def test_test_scope_adapter_preserves_saved_partition_and_true_metric_names():
    raw = pd.DataFrame({"class": pd.array([0, 3], dtype="Int16")},
                        index=pd.date_range("2020-01-01", periods=2, freq="s"))
    predictions = phase5.prediction_frame(partition_for(raw, [0, 1], "test"), np.array([0.1, 0.9]), 0.5, "qa")
    result = phase5.evaluate_partition(predictions, {0, 3}, {"qa-source": raw}, "test", 1, 1.0)
    assert predictions.partition.eq("test").all()
    assert result["partition"] == "test"
    assert result["models"]["qa"]["test"]["confusion_matrix"] == [[1, 0], [0, 1]]
    assert "validation" not in result["models"]["qa"]
    with pytest.raises(ValueError):
        phase5.evaluate_partition(predictions, {0, 3}, {"qa-source": raw}, "validation", 1, 1.0)


def test_gate_exclusively_persists_started_and_refuses_any_existing_journal(tmp_path):
    journal = tmp_path / "test_access.json"
    result = phase5.acquire_test_gate(journal, "a" * 64)
    assert result["status"] == "STARTED" and result["test_attempts"] == 1
    assert json.loads(journal.read_text())["selection_sha256"] == "a" * 64
    for content in [journal.read_text(), "", '{"status":"FAILED_NO_RETRY"}', '{"status":"COMPLETE"}']:
        journal.write_text(content)
        with pytest.raises(FileExistsError):
            phase5.acquire_test_gate(journal, "a" * 64)
        assert journal.read_text() == content


def test_gate_rejects_malformed_selection_hash_without_publication(tmp_path):
    journal = tmp_path / "test_access.json"
    with pytest.raises(ValueError):
        phase5.acquire_test_gate(journal, "not-a-hash")
    assert not journal.exists()


def released_root(tmp_path, monkeypatch):
    report = tmp_path / "reports/experiments"
    report.mkdir(parents=True)
    selection = {"run_id": "qa", "candidate_id": "qa", "model_version": "qa", "train_families": [0, 3]}
    payload = json.dumps(selection)
    (report / "selection.json").write_text(payload)
    (report / "TEST_RELEASE.json").write_text(json.dumps({"approved": True,
                                                        "selection_sha256": hashlib.sha256(payload.encode()).hexdigest()}))
    fake = SimpleNamespace(estimator=object(), kind="logistic_regression", threshold=0.5,
                           pipeline=SimpleNamespace(state=SimpleNamespace(config=SimpleNamespace(stride_rows=1, cadence_seconds=1))))
    monkeypatch.setattr(phase5, "_validate_selection", lambda *args: fake)
    monkeypatch.setattr(phase5, "_verify_requirement_pins", lambda *args: None)
    (tmp_path / "ml/runs/phase5/qa").mkdir(parents=True)
    return report


def test_failure_after_gate_blocks_repeat_before_any_second_test_read(tmp_path, monkeypatch):
    report = released_root(tmp_path, monkeypatch)
    reads = []

    def failed_read(*args):
        assert json.loads((report / "test_access.json").read_text())["status"] == "STARTED"
        reads.append(1)
        raise RuntimeError("synthetic read failure")

    monkeypatch.setattr(phase5, "_load_test_partition", failed_read)
    with pytest.raises(RuntimeError, match="synthetic read failure"):
        phase5.evaluate_test_once(tmp_path)
    assert json.loads((report / "test_access.json").read_text())["status"] == "FAILED_NO_RETRY"
    with pytest.raises(FileExistsError):
        phase5.evaluate_test_once(tmp_path)
    assert reads == [1]
    with pytest.raises(ValueError, match="closed"):
        phase5.run_search(tmp_path)


def test_test_release_must_bind_exact_selection_before_loading_rows(tmp_path, monkeypatch):
    report = released_root(tmp_path, monkeypatch)
    (report / "selection.json").write_text('{"changed":true}')
    monkeypatch.setattr(phase5, "_load_test_partition", lambda *args: pytest.fail("test rows accessed"))
    with pytest.raises(ValueError, match="approval"):
        phase5.evaluate_test_once(tmp_path)
    assert not (report / "test_access.json").exists()


def test_successful_test_evaluates_once_and_never_tunes(tmp_path, monkeypatch):
    report = released_root(tmp_path, monkeypatch)
    raw = pd.DataFrame({"class": pd.array([0, 3], dtype="Int16")},
                        index=pd.date_range("2020-01-01", periods=2, freq="s"))
    reads, predictions = [], []

    def read(*args):
        assert json.loads((report / "test_access.json").read_text())["status"] == "STARTED"
        reads.append(1)
        return partition_for(raw, [0, 1], "test")

    def score(*args):
        predictions.append(1)
        return np.array([0.1, 0.9])

    monkeypatch.setattr(phase5, "_load_test_partition", read)
    monkeypatch.setattr(phase5, "_test_raw", lambda *args: {"qa-source": raw})
    monkeypatch.setattr(phase5, "estimator_scores", score)
    monkeypatch.setattr(phase5, "fit_candidate", lambda *args: pytest.fail("fit after selection"))
    monkeypatch.setattr(phase5, "choose_threshold", lambda *args: pytest.fail("threshold after selection"))
    result = phase5.evaluate_test_once(tmp_path)
    journal = json.loads((report / "test_access.json").read_text())
    assert result["partition"] == "test" and journal["status"] == "COMPLETE"
    assert reads == predictions == [1]
    with pytest.raises(FileExistsError):
        phase5.evaluate_test_once(tmp_path)
    assert reads == predictions == [1]


def test_anomaly_scores_are_never_assessed_as_probabilities():
    value = phase5.probability_quality(np.array([0, 1]), np.array([-10, 20]), "isolation_forest")
    assert value["brier"] is None and value["log_loss"] is None


def test_failure_after_predictions_preserves_auditable_outputs_without_reinference(tmp_path, monkeypatch):
    report = released_root(tmp_path, monkeypatch)
    raw = pd.DataFrame({"class": pd.array([0, 3], dtype="Int16")},
                        index=pd.date_range("2020-01-01", periods=2, freq="s"))
    scored = []
    monkeypatch.setattr(phase5, "_load_test_partition", lambda *args: partition_for(raw, [0, 1], "test"))

    def score(*args):
        scored.append(1)
        return np.array([0.1, 0.9])

    def fail_labels(*args):
        raise RuntimeError("synthetic metric preparation failure")

    monkeypatch.setattr(phase5, "estimator_scores", score)
    monkeypatch.setattr(phase5, "_test_raw", fail_labels)
    with pytest.raises(RuntimeError, match="metric preparation"):
        phase5.evaluate_test_once(tmp_path)
    journal = json.loads((report / "test_access.json").read_text())
    assert journal["status"] == "FAILED_NO_RETRY"
    saved = tmp_path / journal["prediction_path"]
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == journal["prediction_sha256"]
    assert pd.read_parquet(saved).partition.eq("test").all()
    with pytest.raises(FileExistsError):
        phase5.evaluate_test_once(tmp_path)
    assert scored == [1]


def selection_files(tmp_path, monkeypatch):
    report = tmp_path / "reports/experiments"
    report.mkdir(parents=True)
    artifacts = {}
    for name in ["threshold_search.csv", "normal_exposure_weights.csv", "PROTOCOL.md", "predictions.parquet"]:
        (report / name).write_text(name)
    for name in ["features", "targets", "metadata", "quality", "preprocessor"]:
        path = tmp_path / f"data/processed/{name}.fixture"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        artifacts[name] = {"path": str(path.relative_to(tmp_path)), "sha256": phase5.sha256(path)}
    split = tmp_path / "data/manifests/development_split.json"
    split.parent.mkdir(parents=True)
    split.write_text("{}")
    summary = tmp_path / "reports/preprocessing_summary.json"
    summary.write_text("{}")
    search = {"threshold_search_sha256": phase5.sha256(report / "threshold_search.csv"),
               "normal_exposure_weights_sha256": phase5.sha256(report / "normal_exposure_weights.csv")}
    (report / "search.json").write_text(json.dumps(search))
    bundle = tmp_path / "ml/artifacts/phase5/qa"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text("{}")
    selection = {"test_rows_used": 0, "protocol_sha256": phase5.sha256(report / "PROTOCOL.md"),
                 "code_sha256": {"qa-source": "frozen"}, "search_sha256": phase5.sha256(report / "search.json"),
                 "validation_predictions_sha256": phase5.sha256(report / "predictions.parquet"),
                 "validation_predictions_path": "reports/experiments/predictions.parquet",
                 "data_provenance": {"artifacts": artifacts, "split_file_sha256": phase5.sha256(split),
                                      "preprocessing_summary_sha256": phase5.sha256(summary)},
                 "bundle_path": "ml/artifacts/phase5/qa", "bundle_manifest_sha256": phase5.sha256(bundle / "manifest.json"),
                 "threshold": 0.5, "model_version": "qa"}
    monkeypatch.setattr(phase5, "_code_hashes", lambda root: {"qa-source": "frozen"})
    monkeypatch.setattr(phase5, "load_bundle", lambda root: SimpleNamespace(threshold=0.5, metadata={"model_version": "qa"}))
    return selection


@pytest.mark.parametrize("target", ["protocol", "code", "search", "validation_predictions", "split", "summary",
                                   "thresholds", "exposure", "features", "bundle", "threshold", "test_used"])
def test_selection_rejects_changed_evidence_before_test_access(tmp_path, monkeypatch, target):
    selection = selection_files(tmp_path, monkeypatch)
    assert phase5._validate_selection(tmp_path, selection).threshold == 0.5
    paths = {"protocol": "reports/experiments/PROTOCOL.md", "search": "reports/experiments/search.json",
             "validation_predictions": "reports/experiments/predictions.parquet", "split": "data/manifests/development_split.json",
             "summary": "reports/preprocessing_summary.json", "thresholds": "reports/experiments/threshold_search.csv",
             "exposure": "reports/experiments/normal_exposure_weights.csv", "features": "data/processed/features.fixture",
             "bundle": "ml/artifacts/phase5/qa/manifest.json"}
    if target in paths:
        (tmp_path / paths[target]).write_text("changed")
    elif target == "code": selection["code_sha256"] = {"qa-source": "changed"}
    elif target == "threshold": selection["threshold"] = 0.4
    else: selection["test_rows_used"] = 1
    with pytest.raises(ValueError):
        phase5._validate_selection(tmp_path, selection)
    assert not (tmp_path / "reports/experiments/test_access.json").exists()


@pytest.mark.parametrize("mutation", ["missing_source", "window_count", "wrong_well", "wrong_group", "eligible_support", "feature_leak"])
def test_test_loader_rejects_incomplete_or_inconsistent_synthetic_cohort(tmp_path, monkeypatch, mutation):
    raw = pd.DataFrame({"class": pd.array([0, 3], dtype="Int16")},
                        index=pd.date_range("2020-01-01", periods=2, freq="s"))
    part = partition_for(raw, [0, 1], "test")
    part.metadata["group_id"] = "qa-group"
    part.metadata["source_path"] = "synthetic.parquet"
    part.metadata["sha256"] = "a" * 64
    source = SimpleNamespace(instance_id="qa-source", well_id="WELL-QA", origin="real",
                              source_path="synthetic.parquet", sha256="a" * 64)
    assignment = SimpleNamespace(source=source, partition="test", group_id="qa-group")
    assignments = [assignment]
    summary = {"windows": 2, "connected_groups": 1, "real_well_ids": ["WELL-QA"],
               "supervised_eligible_windows": 2, "unknown_endpoint_windows": 0}
    if mutation == "missing_source": assignments.append(SimpleNamespace(source=SimpleNamespace(instance_id="absent"), partition="test"))
    elif mutation == "window_count": summary["windows"] = 3
    elif mutation == "wrong_well": part.metadata["well_id"] = "other-well"
    elif mutation == "wrong_group": part.metadata["group_id"] = "other-group"
    elif mutation == "eligible_support": summary["supervised_eligible_windows"] = 1
    else: part.features["class"] = 0
    report = tmp_path / "reports/preprocessing_summary.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"partitions": {"test": summary}}))
    tables = {name: getattr(part, name) for name in ("features", "targets", "metadata", "quality")}

    def read(path, filters):
        name = path.name
        if name == "metadata": assert filters == [("partition", "==", "test")]
        else: assert filters == [("window_id", "in", part.metadata.index.tolist())]
        return tables[name]

    monkeypatch.setattr(phase5.pd, "read_parquet", read)
    split = SimpleNamespace(assignments=assignments, assignment_for=lambda source_id: assignment)
    fake = SimpleNamespace(pipeline=SimpleNamespace(state=SimpleNamespace(split_manifest=split,
                                                                         retained_features=("P-PDG__mean",))))
    selection = {"data_provenance": {"artifacts": {name: {"path": name} for name in tables}}}
    with pytest.raises(ValueError):
        phase5._load_test_partition(tmp_path, selection, fake)
