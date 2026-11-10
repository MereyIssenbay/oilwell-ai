"""Bounded model selection tests on explicitly synthetic fixtures."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ml.predict import estimator_scores
from ml.train_baseline import PartitionData
from ml.training import phase5


def training_fixture() -> PartitionData:
    size = 80
    index = pd.Index([f"synthetic-{i}" for i in range(size)], name="window_id")
    positive = np.arange(size) >= size // 2
    features = pd.DataFrame({"P-TPT__mean": np.where(positive, 2., -2.), "P-TPT__trend": np.linspace(-1, 1, size)}, index=index)
    targets = pd.DataFrame({"raw_class": pd.array(np.where(positive, 3, 0), dtype="Int16"),
                            "event_family": pd.array(np.where(positive, 3, 0), dtype="Int16"),
                            "phase": np.where(positive, "event", "normal")}, index=index)
    metadata = pd.DataFrame({"partition": "train", "origin": "real"}, index=index)
    quality = pd.DataFrame({"P-TPT__observed_count": 60}, index=index)
    return PartitionData(features, targets, metadata, quality, pd.Series(True, index=index), "train")


@pytest.mark.parametrize("kind", ["catboost", "xgboost"])
def test_boosted_estimator_fits_only_known_training_targets(kind):
    train = training_fixture()
    train.targets.loc[train.targets.index[:5], ["raw_class", "event_family"]] = pd.NA
    train.targets.loc[train.targets.index[:5], "phase"] = "unknown"
    spec = next(spec for spec in phase5.candidate_specs() if spec["kind"] == kind)
    estimator = phase5.fit_candidate(train, spec)
    scores = estimator_scores(estimator, kind, train.features)
    assert np.isfinite(scores).all() and ((0 <= scores) & (scores <= 1)).all()
    assert scores[-1] > scores[5]
    if kind == "catboost":
        assert estimator.tree_count_ == 200
    else:
        assert estimator.get_booster().num_boosted_rounds() == 200


def test_candidate_budget_is_fixed_and_cannot_accept_holdout():
    specs = phase5.candidate_specs()
    assert len(specs) == 8 and len({spec["candidate_id"] for spec in specs}) == 8
    train = training_fixture()
    changed = replace(train, partition="validation", metadata=train.metadata.assign(partition="validation"))
    with pytest.raises(ValueError, match="train only"):
        phase5.fit_candidate(changed, specs[0])
    altered = {**specs[0], "parameters": {**specs[0]["parameters"], "depth": 12}}
    with pytest.raises(ValueError, match="bounded"):
        phase5.fit_candidate(train, altered)


def test_threshold_uses_normal_seconds_including_unknown_endpoint():
    scores = np.array([.9, .8, .7, .1])
    y = np.array([1., np.nan, 0., 0.])
    eligible = np.array([True, False, True, True])
    selection = phase5.choose_threshold(scores, y, np.array([0., 10., 1., 89.]), eligible)
    assert selection["selected"]["threshold"] > .8
    assert selection["selected"]["recall"] == 1
    assert selection["selected"]["normal_alarm_occupancy_fraction"] == 0
    assert len(selection["grid"]) <= 203


def test_threshold_all_positive_rank_has_feasible_allnormal_fallback():
    scores = np.ones(5)
    y = np.array([0, 0, 0, 1, 1])
    selection = phase5.choose_threshold(scores, y, np.array([10, 10, 10, 0, 0]), np.ones(5, dtype=bool))
    assert selection["selected"]["threshold"] > 1
    assert selection["selected"]["recall"] == 0
    assert selection["selected"]["normal_alarm_occupancy_fraction"] == 0


def test_candidate_ranking_prefers_recall_then_ap_then_occupancy_then_id():
    base = {"recall": .9, "average_precision": .8, "normal_alarm_occupancy_fraction": .02}
    records = [{"candidate_id": "b", **base}, {"candidate_id": "a", **base},
               {"candidate_id": "better_ap_lower_recall", **base, "average_precision": 1., "recall": .8}]
    assert phase5.rank_candidates(records)["candidate_id"] == "a"
    assert phase5.rank_candidates(list(reversed(records)))["candidate_id"] == "a"
    records[0]["average_precision"] = .81
    assert phase5.rank_candidates(records)["candidate_id"] == "b"


def test_exclusive_gate_never_reopens_failed_or_completed_attempt(tmp_path):
    path = tmp_path / "test_access.json"
    first = phase5.acquire_test_gate(path, "a" * 64)
    assert first["status"] == "STARTED" and first["test_attempts"] == 1
    for status in ["STARTED", "FAILED_NO_RETRY", "COMPLETE"]:
        path.write_text(json.dumps({**first, "status": status}))
        with pytest.raises(FileExistsError):
            phase5.acquire_test_gate(path, "b" * 64)


def test_test_loader_cannot_run_without_hash_bound_release(tmp_path, monkeypatch):
    report = tmp_path / phase5.REPORTS
    report.mkdir(parents=True)
    (report / "selection.json").write_text('{}')
    (report / "TEST_RELEASE.json").write_text('{"approved":true,"selection_sha256":"wrong"}')
    called = []
    monkeypatch.setattr(phase5, "_load_test_partition", lambda *args: called.append(True))
    with pytest.raises(ValueError, match="Root integrity approval"):
        phase5.evaluate_test_once(tmp_path)
    assert not called and not (report / "test_access.json").exists()


def test_test_read_failure_is_recorded_and_never_retried(tmp_path, monkeypatch):
    report = tmp_path / phase5.REPORTS
    report.mkdir(parents=True)
    selection = report / "selection.json"
    selection.write_text('{}')
    (report / "TEST_RELEASE.json").write_text(json.dumps({"approved": True, "selection_sha256": phase5.sha256(selection)}))
    monkeypatch.setattr(phase5, "_validate_selection", lambda *args: SimpleNamespace())
    monkeypatch.setattr(phase5, "_verify_requirement_pins", lambda *args: None)
    calls = []
    def failed_read(*args):
        assert json.loads((report / "test_access.json").read_text())["status"] == "STARTED"
        calls.append(True)
        raise ValueError("synthetic test read failure")
    monkeypatch.setattr(phase5, "_load_test_partition", failed_read)
    with pytest.raises(ValueError, match="synthetic test read"):
        phase5.evaluate_test_once(tmp_path)
    assert json.loads((report / "test_access.json").read_text())["status"] == "FAILED_NO_RETRY"
    with pytest.raises(FileExistsError):
        phase5.evaluate_test_once(tmp_path)
    assert len(calls) == 1


def test_search_is_closed_once_any_test_attempt_has_started(tmp_path):
    report = tmp_path / phase5.REPORTS
    report.mkdir(parents=True)
    (report / "test_access.json").write_text('{}')
    with pytest.raises(ValueError, match="permanently closed"):
        phase5.run_search(tmp_path)
