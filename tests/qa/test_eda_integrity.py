"""Independent, offline checks for EDA boundaries and descriptive statistics."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("oilwell_eda_qa", ROOT / "scripts/data/eda.py")
assert SPEC is not None and SPEC.loader is not None
EDA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EDA)


def test_unknown_boundaries_do_not_become_known_onsets() -> None:
    labels = pd.Series([0, 0, pd.NA, 101, 101, 1], dtype="Int16")
    original = labels.copy(deep=True)
    index = pd.date_range("2020-01-01", periods=len(labels), freq="s")
    runs = EDA.label_runs(labels, index)
    changes = EDA.transitions_between_runs(runs, index)
    assert [run["raw_label"] for run in runs] == ["0", "unknown", "101", "1"]
    assert [run["rows"] for run in runs] == [2, 1, 2, 1]
    assert [(row["from_raw"], row["to_raw"]) for row in changes if row["known_labels"]] == [("101", "1")]
    assert runs[0]["left_censored"] and runs[0]["right_censored"]
    assert runs[2]["left_censored"] and not runs[2]["right_censored"]
    assert runs[-1]["right_censored"]
    pd.testing.assert_series_equal(labels, original)


def test_timestamp_gap_splits_same_label_run() -> None:
    index = pd.to_datetime(["2020-01-01 00:00:00", "2020-01-01 00:00:01",
                            "2020-01-01 00:00:10", "2020-01-01 00:00:11"])
    labels = pd.Series([0, 0, 0, 101], dtype="Int16")
    runs = EDA.label_runs(labels, index)
    assert [run["rows"] for run in runs] == [2, 1, 1]
    assert runs[0]["right_censored"] and runs[1]["left_censored"]
    changes = EDA.transitions_between_runs(runs, index)
    assert len(changes) == 1
    assert changes[0]["boundary_position"] == 3


def test_gap_between_different_labels_is_not_a_transition() -> None:
    index = pd.to_datetime(["2020-01-01", "2020-01-01 00:10:00"], format="mixed")
    runs = EDA.label_runs(pd.Series([0, 101], dtype="Int16"), index)
    assert EDA.transitions_between_runs(runs, index) == []


def test_separate_instances_have_no_cross_file_transition() -> None:
    index = pd.date_range("2020-01-01", periods=3, freq="s")
    first = EDA.label_runs(pd.Series([0, 0, 0], dtype="Int16"), index)
    second = EDA.label_runs(pd.Series([101, 101, 101], dtype="Int16"), index)
    assert EDA.transitions_between_runs(first, index) == []
    assert EDA.transitions_between_runs(second, index) == []
    assert first[-1]["right_censored"] and second[0]["left_censored"]


def test_single_observation_duration_is_support_not_elapsed_time() -> None:
    index = pd.date_range("2020-01-01", periods=1, freq="s")
    run = EDA.label_runs(pd.Series([101], dtype="Int16"), index)[0]
    assert run["duration_seconds"] == 1.0
    assert run["left_censored"] and run["right_censored"]


@pytest.mark.parametrize("index", [
    pd.to_datetime(["2020-01-01", "2020-01-01"]),
    pd.to_datetime(["2020-01-02", "2020-01-01"]),
    pd.DatetimeIndex([pd.Timestamp("2020-01-01"), pd.NaT]),
])
def test_invalid_time_order_is_rejected(index: pd.DatetimeIndex) -> None:
    with pytest.raises(ValueError):
        EDA.label_runs(pd.Series([0, 101], dtype="Int16"), index)


def test_pairwise_support_counts_missing_rows_without_imputation() -> None:
    frame = pd.DataFrame({"P-PDG": [1.0, np.nan, 3.0, 4.0],
                          "P-TPT": [4.0, 3.0, np.nan, 1.0]})
    original = frame.copy(deep=True)
    row = EDA.correlation_rows(frame, ["P-PDG", "P-TPT"], min_pairs=2)[0]
    assert row["pair_count"] == 2
    assert row["pearson"] == pytest.approx(-1.0)
    insufficient = EDA.correlation_rows(frame, ["P-PDG", "P-TPT"], min_pairs=3)[0]
    assert insufficient["pair_count"] == 2 and insufficient["pearson"] is None
    pd.testing.assert_frame_equal(frame, original)


def test_pairwise_counts_are_counts_not_boolean_or_byte_overflow() -> None:
    frame = pd.DataFrame({"P-PDG": np.arange(300, dtype=float),
                          "P-TPT": -np.arange(300, dtype=float)})
    row = EDA.correlation_rows(frame, ["P-PDG", "P-TPT"])[0]
    assert row["pair_count"] == 300
    assert row["pearson"] == pytest.approx(-1.0)


@pytest.mark.parametrize("other", [[2.0, 2.0, 2.0], [np.nan, np.nan, np.nan]])
def test_constant_or_missing_correlation_is_undefined(other: list[float]) -> None:
    frame = pd.DataFrame({"P-PDG": [1.0, 2.0, 3.0], "P-TPT": other})
    row = EDA.correlation_rows(frame, ["P-PDG", "P-TPT"], min_pairs=2)[0]
    assert row["pearson"] is None


@pytest.mark.parametrize("forbidden", ["class", "state", "timestamp"])
def test_labels_and_time_are_rejected_as_sensor_inputs(forbidden: str) -> None:
    frame = pd.DataFrame({"P-PDG": [1.0, 2.0, 3.0], forbidden: [0.0, 1.0, 2.0]})
    with pytest.raises(ValueError, match="not sensor inputs"):
        EDA.correlation_rows(frame, ["P-PDG", forbidden], min_pairs=2)


def test_missing_pair_support_is_zero_not_observed_zero_values() -> None:
    frame = pd.DataFrame({"P-PDG": [1.0, 2.0, np.nan, np.nan],
                          "P-TPT": [np.nan, np.nan, 3.0, 4.0]})
    row = EDA.correlation_rows(frame, ["P-PDG", "P-TPT"], min_pairs=2)[0]
    assert row["pair_count"] == 0 and row["pearson"] is None
