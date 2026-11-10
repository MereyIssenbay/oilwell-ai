"""Small synthetic regression cases for descriptive EDA boundaries."""
from pathlib import Path
import importlib.util

import numpy as np
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location("eda", Path(__file__).parents[2] / "scripts/data/eda.py")
eda = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eda)


def test_unknowns_and_gaps_censor_runs_without_inventing_known_transition():
    index = pd.to_datetime(["2020-01-01 00:00:00", "2020-01-01 00:00:01", "2020-01-01 00:00:02", "2020-01-01 00:00:10"])
    labels = pd.Series([0, None, 101, 1], dtype="Int16")
    runs = eda.label_runs(labels, index)
    changes = eda.transitions_between_runs(runs, index)
    assert [r["raw_label"] for r in runs] == ["0", "unknown", "101", "1"]
    assert runs[2]["left_censored"] and runs[2]["right_censored"]
    assert not any(c["known_labels"] for c in changes)
    assert len(changes) == 2
    assert all(r["duration_seconds"] == 1 for r in runs)


def test_correlations_use_pairwise_observations_and_mask_pairwise_constant():
    frame = pd.DataFrame({"A": [0., 1., 2., 100.], "B": [0., 2., 4., np.nan], "C": [3., 3., 3., np.nan]})
    rows = eda.correlation_rows(frame, ["A", "B", "C"], min_pairs=3)
    ab = next(row for row in rows if row["sensor_a"] == "A" and row["sensor_b"] == "B")
    ac = next(row for row in rows if row["sensor_a"] == "A" and row["sensor_b"] == "C")
    assert ab["pair_count"] == 3 and ab["pearson"] == pytest.approx(1)
    assert ac["pair_count"] == 3 and ac["pearson"] is None


def test_labels_are_never_allowed_in_sensor_correlations():
    frame = pd.DataFrame({"P-TPT": [1., 2.], "class": [0, 1], "state": [0, 0]})
    for label in ("class", "state"):
        with pytest.raises(ValueError, match="not sensor inputs"):
            eda.correlation_rows(frame, ["P-TPT", label], min_pairs=2)
