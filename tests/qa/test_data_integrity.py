"""Independent offline boundary checks for the Phase 1 raw-data auditor.

All records/files constructed here are synthetic test fixtures. They are not 3W
observations and are never written to the acquired dataset directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_data.py"
SPEC = importlib.util.spec_from_file_location("oilwell_phase1_validation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validation
SPEC.loader.exec_module(validation)

SENSORS = ["P-TPT", "ESTADO-DHSV"]
CLASS_CODES = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 101, 102, 105, 106, 107, 108, 109}
STATE_CODES = set(range(9))


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "P-TPT": [10.0, np.nan, 12.0, 13.0],
            "ESTADO-DHSV": [0.0, 0.5, 1.0, 1.0],
            "class": pd.array([0, 101, 1, None], dtype="Int16"),
            "state": pd.array([0, 1, 7, None], dtype="Int16"),
        },
        index=pd.date_range("2020-01-01", periods=4, freq="s", name="timestamp"),
    )


def inspect(frame: pd.DataFrame) -> dict:
    return validation.inspect_frame(
        frame, sensor_names=SENSORS, valid_labels=CLASS_CODES, valid_states=STATE_CODES
    )


def codes(result: dict, level: str = "errors") -> set[str]:
    return {item["code"] for item in result[level]}


def file_entry(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob_sha1": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest(),
    }


def test_nulls_preserved_and_excluded_from_class_counts(frame: pd.DataFrame) -> None:
    before = frame.copy(deep=True)
    result = inspect(frame)
    assert result["errors"] == []
    assert result["class_distribution"] == {"0": 1, "1": 1, "101": 1, "null": 1}
    assert result["state_distribution"]["null"] == 1
    assert result["sensor_summary"]["P-TPT"]["missing_count"] == 1
    assert result["sensor_summary"]["P-TPT"]["missing_fraction"] == 0.25
    assert set(result["sensor_summary"]) == set(SENSORS)
    assert result["timestamp"]["timezone"] is None
    assert "unknown_timezone" in codes(result, "warnings")
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("field,value,expected", [("class", 103, "unknown_class"), ("class", -1, "unknown_class"), ("state", 9, "unknown_state")])
def test_undocumented_label_codes_are_rejected(frame: pd.DataFrame, field: str, value: int, expected: str) -> None:
    frame.loc[frame.index[0], field] = value
    assert expected in codes(inspect(frame))


def test_valid_class_from_another_event_family_is_not_rejected(frame: pd.DataFrame) -> None:
    frame["class"] = pd.array([3, 102, 8, 109], dtype="Int16")
    assert inspect(frame)["errors"] == []


@pytest.mark.parametrize("mutation,expected", [("duplicate", "duplicate_timestamps"), ("backwards", "nonmonotonic_timestamps"), ("null", "null_timestamps"), ("text", "timestamp_dtype")])
def test_invalid_timestamps_are_reported(frame: pd.DataFrame, mutation: str, expected: str) -> None:
    times = list(frame.index)
    if mutation == "duplicate":
        times[1] = times[0]
    elif mutation == "backwards":
        times[1], times[2] = times[2], times[1]
    elif mutation == "null":
        times[1] = pd.NaT
    else:
        frame.index = pd.Index(["a", "b", "c", "d"], name="timestamp")
        assert expected in codes(inspect(frame))
        return
    frame.index = pd.DatetimeIndex(times, name="timestamp")
    assert expected in codes(inspect(frame))


def test_cadence_gap_is_visible_without_filling_rows(frame: pd.DataFrame) -> None:
    frame.index = pd.DatetimeIndex(["2020-01-01T00:00:00", "2020-01-01T00:00:01", "2020-01-01T00:00:04", "2020-01-01T00:00:05"], name="timestamp")
    result = inspect(frame)
    assert "irregular_cadence" in codes(result, "warnings")
    assert result["rows"] == 4
    assert result["timestamp"]["gaps_over_one_second"] == 1


@pytest.mark.parametrize("mutation,expected", [("extra_metadata", "unexpected_columns"), ("missing_sensor", "missing_columns"), ("duplicate", "duplicate_columns"), ("text_sensor", "sensor_dtype"), ("infinity", "infinite_sensor_values"), ("fractional_label", "label_dtype")])
def test_schema_and_nonfinite_input_fail_closed(frame: pd.DataFrame, mutation: str, expected: str) -> None:
    if mutation == "extra_metadata":
        frame["event_code"] = 1
    elif mutation == "missing_sensor":
        frame = frame.drop(columns="P-TPT")
    elif mutation == "duplicate":
        frame = pd.concat([frame, frame[["P-TPT"]]], axis=1)
    elif mutation == "text_sensor":
        frame["P-TPT"] = ["10", "11", "12", "13"]
    elif mutation == "infinity":
        frame.loc[frame.index[0], "P-TPT"] = np.inf
    else:
        frame["class"] = [0.0, 1.5, 1.0, np.nan]
    assert expected in codes(inspect(frame))


def test_empty_and_all_missing_sources_are_not_silently_normal(frame: pd.DataFrame) -> None:
    assert "empty_instance" in codes(inspect(frame.iloc[:0]))
    frame["P-TPT"] = np.nan
    result = inspect(frame)
    assert "all_missing_sensors" in codes(result, "warnings")
    assert result["sensor_summary"]["P-TPT"]["missing_fraction"] == 1.0
    assert result["class_distribution"]["null"] == 1


def test_null_label_positions_distinguish_leading_from_interior_gaps(frame: pd.DataFrame) -> None:
    frame["class"] = pd.array([None, None, 1, None], dtype="Int16")
    profile = inspect(frame)["label_null_profile"]["class"]
    assert profile == {"missing_count": 3, "leading_missing_count": 2, "trailing_missing_count": 1,
                       "first_missing_position": 0, "last_missing_position": 3}


def test_file_corruption_and_wrong_hash_are_detected_without_rewriting(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.bin"
    path.write_bytes(b"immutable fixture")
    entry = file_entry(path)
    assert validation.verify_file(path, entry)["ok"]
    path.write_bytes(b"corrupted fixture")
    before = path.read_bytes()
    result = validation.verify_file(path, entry)
    assert not result["ok"]
    assert {"sha256_mismatch", "git_blob_sha1_mismatch"} <= codes(result)
    assert path.read_bytes() == before
    assert "missing_file" in codes(validation.verify_file(tmp_path / "absent", entry))


@pytest.mark.parametrize("relative", ["../outside.parquet", "data/raw/../outside.parquet", "C:/outside.parquet", "/outside.parquet", "data/raw", "data/processed/file.parquet", "data\\raw\\file.parquet"])
def test_source_path_escape_rejected(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError):
        validation.resolve_raw_path(tmp_path, relative)


def test_raw_root_symlink_escape_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    (repo / "data").mkdir(parents=True)
    outside.mkdir()
    try:
        (repo / "data/raw").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Host cannot create directory symlinks: {exc}")
    with pytest.raises(ValueError):
        validation.resolve_raw_path(repo, "data/raw/file.parquet")


@pytest.mark.parametrize("overwrite", ["raw", "manifest"])
def test_cli_refuses_overwriting_sources_before_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overwrite: str) -> None:
    monkeypatch.setattr(validation, "REPO_ROOT", tmp_path)
    manifest = tmp_path / "data/manifests/subset.json"
    target = tmp_path / "data/raw/protected.json" if overwrite == "raw" else manifest
    target.parent.mkdir(parents=True)
    target.write_text("preserve me", encoding="utf-8")
    monkeypatch.setattr(validation, "audit_manifest", lambda *args: pytest.fail("Audit should not start for a protected output"))
    assert validation.main(["--manifest", str(manifest), "--output", str(target)]) == 2
    assert target.read_text(encoding="utf-8") == "preserve me"


@pytest.mark.parametrize("relative", ["data/raw/file.json", "scripts/validate_data.py", "reports/file.py", "../outside.json"])
def test_report_destination_cannot_clobber_sources_or_code(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError):
        validation.safe_report_path(tmp_path, tmp_path / relative, tmp_path / "data/manifests/subset.json")


def test_report_destination_accepts_json_in_reports(tmp_path: Path) -> None:
    output = tmp_path / "reports/qa.json"
    assert validation.safe_report_path(tmp_path, output, tmp_path / "data/manifests/subset.json") == output.resolve()


@pytest.mark.parametrize("payload", ["[]", "null", "{}", "{bad json"])
def test_malformed_manifest_returns_fatal_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str) -> None:
    monkeypatch.setattr(validation, "REPO_ROOT", tmp_path)
    manifest = tmp_path / "malformed.json"
    manifest.write_text(payload, encoding="utf-8")
    output = tmp_path / "reports/result.json"
    assert validation.main(["--manifest", str(manifest), "--output", str(output)]) == 2
    assert not output.exists()


def test_metadata_hash_failure_prevents_registry_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = tmp_path / "data/raw/test/dataset.ini"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("synthetic metadata", encoding="utf-8")
    entry = {"source_path": "dataset/dataset.ini", "local_path": "data/raw/test/dataset.ini", **file_entry(metadata)}
    entry["sha256"] = "0" * 64
    manifest = {
        "schema_version": "1.0.0",
        "dataset": {"repository": "https://github.com/petrobras/3W", "revision": "a" * 40, "version": "2.0.0"},
        "selection": {},
        "metadata": [entry],
        "files": [{"source_path": "dataset/0/WELL-99999_20200101000000.parquet", "local_path": "data/raw/test/file.parquet", "source_instance_id": "synthetic"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(validation, "parse_registry", lambda *args: pytest.fail("Unverified metadata must not be parsed"))
    with pytest.raises(ValueError, match="Metadata integrity"):
        validation.audit_manifest(manifest_path, tmp_path)
