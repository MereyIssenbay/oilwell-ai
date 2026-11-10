#!/usr/bin/env python3
"""Audit immutable 3W source files offline; never preprocess or rewrite telemetry.

Exit codes: 0 = audit passed (warnings allowed), 1 = integrity/data validation
findings, 2 = fatal manifest/configuration/I/O error. Reports contain aggregates,
not raw telemetry. Run from any directory; defaults resolve against the repo.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import configparser
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_MEANINGS = {
    0: "Open", 1: "Shut-In", 2: "Flushing Diesel", 3: "Flushing Gas",
    4: "Bullheading", 5: "Closed With Diesel", 6: "Closed With Gas",
    7: "Restart", 8: "Depressurization",
}
STATE_SOURCE = "https://arxiv.org/html/2507.01048v1#S2.T5"


def finding(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def resolve_raw_path(repo_root: Path, local_path: str) -> Path:
    """Only allow repository-relative files beneath data/raw, including symlinks."""
    value = PurePosixPath(local_path)
    if "\\" in local_path or ":" in local_path or value.is_absolute() or ".." in value.parts:
        raise ValueError(f"Unsafe raw path: {local_path}")
    if value.parts[:2] != ("data", "raw"):
        raise ValueError(f"Path must be beneath data/raw: {local_path}")
    raw_root = (repo_root / "data" / "raw").resolve()
    target = (repo_root / Path(*value.parts)).resolve()
    if not raw_root.is_relative_to(repo_root.resolve()) or not target.is_relative_to(raw_root) or target == raw_root:
        raise ValueError(f"Raw path escapes its allowed directory: {local_path}")
    return target


def safe_report_path(repo_root: Path, output: Path, manifest_path: Path) -> Path:
    """Reports may replace JSON reports only, never raw inputs or project code."""
    target = output.resolve()
    reports_root = (repo_root / "reports").resolve()
    if (not reports_root.is_relative_to(repo_root.resolve())
            or not target.is_relative_to(reports_root)
            or target.suffix.lower() != ".json" or target == manifest_path.resolve()):
        raise ValueError("Report destination must be a .json file beneath the repository reports/ directory.")
    return target


def verify_file(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    """Verify pinned Git blob identity as well as the recorded SHA-256."""
    result: dict[str, Any] = {"ok": False, "errors": []}
    if not path.is_file():
        result["errors"].append(finding("missing_file", "Manifest file is absent."))
        return result
    size = path.stat().st_size
    git_hash = hashlib.sha1(f"blob {size}\0".encode(), usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(block)
            git_hash.update(block)
    result.update(actual_size_bytes=size, actual_sha256=sha256.hexdigest(),
                  actual_git_blob_sha1=git_hash.hexdigest())
    for field, actual in [("size_bytes", size), ("sha256", sha256.hexdigest()),
                          ("git_blob_sha1", git_hash.hexdigest())]:
        if entry.get(field) != actual:
            result["errors"].append(finding(f"{field}_mismatch", f"Source {field} does not match manifest."))
    result["ok"] = not result["errors"]
    return result


def distribution(series: pd.Series) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value, count in series.value_counts(dropna=False).items():
        if pd.isna(value):
            key = "null"
        elif isinstance(value, (int, float, np.number)) and np.isfinite(value) and float(value).is_integer():
            key = str(int(value))
        else:
            key = str(value)
        counts[key] += int(count)
    return dict(sorted(counts.items()))


def inspect_frame(frame: pd.DataFrame, *, sensor_names: list[str],
                  valid_labels: set[int], valid_states: set[int]) -> dict[str, Any]:
    """Describe an in-memory source frame without modifying it or filling nulls."""
    result: dict[str, Any] = {
        "rows": len(frame), "columns": list(frame.columns),
        "pandas_dtypes": {str(k): str(v) for k, v in frame.dtypes.items()},
        "errors": [], "warnings": [], "sensor_summary": {},
        "class_distribution": {}, "state_distribution": {}, "timestamp": {},
        "label_null_profile": {},
    }
    errors, warnings = result["errors"], result["warnings"]
    expected = set(sensor_names) | {"class", "state"}
    if not frame.columns.is_unique:
        errors.append(finding("duplicate_columns", "Column names are not unique."))
        return result
    missing, extra = expected - set(frame.columns), set(frame.columns) - expected
    if missing:
        errors.append(finding("missing_columns", ", ".join(sorted(missing))))
    if extra:
        errors.append(finding("unexpected_columns", ", ".join(sorted(map(str, extra)))))
    if not len(frame):
        errors.append(finding("empty_instance", "Source contains zero observations."))
    for name in sensor_names:
        if name not in frame:
            continue
        series = frame[name]
        null_count = int(series.isna().sum())
        stats: dict[str, Any] = {
            "dtype": str(series.dtype), "missing_count": null_count,
            "missing_fraction": null_count / len(frame) if len(frame) else None,
            "all_missing": bool(len(frame) and null_count == len(frame)),
        }
        if not pd.api.types.is_float_dtype(series.dtype):
            errors.append(finding("sensor_dtype", f"{name} must be a floating sensor field, got {series.dtype}."))
        else:
            values = series.to_numpy(dtype=float, na_value=np.nan)
            finite = values[np.isfinite(values)]
            inf_count = int(np.isinf(values).sum())
            stats.update(non_finite_count=inf_count,
                         finite_min=float(finite.min()) if finite.size else None,
                         finite_max=float(finite.max()) if finite.size else None,
                         unique_non_null_count=int(series.nunique(dropna=True)))
            if inf_count:
                errors.append(finding("infinite_sensor_values", f"{name}: {inf_count} infinite values."))
            if name.startswith("ESTADO-"):
                invalid = int((series.notna() & ~series.isin([0.0, 0.5, 1.0])).sum())
                stats["outside_documented_valve_domain"] = invalid
                if invalid:
                    warnings.append(finding("valve_domain", f"{name}: {invalid} readings outside 0/0.5/1."))
        result["sensor_summary"][name] = stats
    all_null = [name for name, stats in result["sensor_summary"].items() if stats["all_missing"]]
    if all_null:
        warnings.append(finding("all_missing_sensors", ", ".join(all_null)))
    for name, allowed in [("class", valid_labels), ("state", valid_states)]:
        if name not in frame:
            continue
        series = frame[name]
        result[f"{name}_distribution"] = distribution(series)
        missing_mask = series.isna().to_numpy()
        missing_positions = np.flatnonzero(missing_mask)
        present_positions = np.flatnonzero(~missing_mask)
        result["label_null_profile"][name] = {
            "missing_count": int(missing_mask.sum()),
            "leading_missing_count": int(present_positions[0]) if present_positions.size else len(series),
            "trailing_missing_count": len(series) - int(present_positions[-1]) - 1 if present_positions.size else len(series),
            "first_missing_position": int(missing_positions[0]) if missing_positions.size else None,
            "last_missing_position": int(missing_positions[-1]) if missing_positions.size else None,
        }
        if not pd.api.types.is_integer_dtype(series.dtype):
            errors.append(finding("label_dtype", f"{name} must use nullable integer labels, got {series.dtype}."))
        invalid = series.notna() & ~series.isin(allowed)
        if invalid.any():
            errors.append(finding(f"unknown_{name}", json.dumps(distribution(series[invalid]), sort_keys=True)))
        if series.isna().any():
            warnings.append(finding(f"missing_{name}", f"{int(series.isna().sum())} unknown {name} labels; retained as null."))
    index = frame.index
    result["timestamp"] = {"index_name": index.name, "dtype": str(index.dtype)}
    if index.name != "timestamp":
        errors.append(finding("timestamp_index_name", "Expected timestamp as the named index."))
    if not isinstance(index, pd.DatetimeIndex):
        errors.append(finding("timestamp_dtype", "Expected a Pandas DatetimeIndex; no conversion was attempted."))
    else:
        valid_index = index[~index.isna()]
        diffs = pd.Series(valid_index).diff().dt.total_seconds().dropna()
        duplicates = int(index.duplicated().sum())
        null_times = int(index.isna().sum())
        backwards = int((diffs < 0).sum())
        time_info = result["timestamp"]
        time_info.update(
            timezone=str(index.tz) if index.tz is not None else None,
            timezone_interpretation="unverified_source_timezone" if index.tz is None else "stored_timezone",
            first=index[0].isoformat() if len(index) and not pd.isna(index[0]) else None,
            last=index[-1].isoformat() if len(index) and not pd.isna(index[-1]) else None,
            minimum=valid_index.min().isoformat() if len(valid_index) else None,
            maximum=valid_index.max().isoformat() if len(valid_index) else None,
            duration_seconds=float((valid_index.max() - valid_index.min()).total_seconds()) if len(valid_index) else None,
            null_count=null_times, duplicate_count=duplicates, backwards_steps=backwards,
            monotonic_increasing=bool(index.is_monotonic_increasing),
            interval_counts_seconds={str(k): int(v) for k, v in diffs.value_counts().sort_index().items()},
            non_one_second_intervals=int((diffs != 1.0).sum()),
            gaps_over_one_second=int((diffs > 1.0).sum()),
        )
        if null_times:
            errors.append(finding("null_timestamps", f"{null_times} null timestamps."))
        if duplicates:
            errors.append(finding("duplicate_timestamps", f"{duplicates} duplicate timestamps after first occurrence."))
        if backwards:
            errors.append(finding("nonmonotonic_timestamps", f"{backwards} backward timestamp steps."))
        if index.tz is None:
            warnings.append(finding("unknown_timezone", "Naive source timestamps retained without localization."))
        if time_info["non_one_second_intervals"]:
            warnings.append(finding("irregular_cadence", "Observed intervals differ from the documented 1 Hz expectation."))
    if not errors:
        # Includes the timestamp index, sensors and labels. This is a diagnostic
        # fingerprint tied to the recorded pandas version, not a source checksum.
        row_hashes = pd.util.hash_pandas_object(frame, index=True).to_numpy(dtype="uint64")
        result["content_fingerprint"] = hashlib.sha256(row_hashes.tobytes()).hexdigest()
        result["duplicate_full_rows_including_timestamp"] = int(pd.Series(row_hashes).duplicated().sum())
    return result


def parse_registry(ini_path: Path) -> dict[str, Any]:
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read_string(ini_path.read_text(encoding="utf-8"))
    properties = dict(parser.items("PARQUET_FILE_PROPERTIES"))
    sensors = {name: meaning for name, meaning in properties.items() if name not in {"timestamp", "class", "state"}}
    offset = parser.getint("EVENTS", "TRANSIENT_OFFSET")
    labels: dict[str, Any] = {}
    for name in parser.get("EVENTS", "NAMES").replace("\n", " ").split(","):
        name = name.strip()
        code = parser.getint(name, "LABEL")
        labels[str(code)] = {"event_name": name, "phase": "normal" if code == 0 else "event", "base_code": code}
        if parser.getboolean(name, "TRANSIENT", fallback=False):
            labels[str(code + offset)] = {"event_name": name, "phase": "transient", "base_code": code}
    return {
        "dataset_version": parser.get("VERSION", "DATASET"),
        "sensor_columns": list(sensors), "sensor_descriptions": sensors,
        "target_columns": ["class"], "operational_label_columns": ["state"],
        "timestamp_field": "timestamp", "class_labels": labels,
        "state_labels": {str(k): v for k, v in STATE_MEANINGS.items()},
        "state_mapping_source": STATE_SOURCE, "null_label_meaning": "unknown",
        "excluded_from_features": ["class", "state", "timestamp", "source_path", "event_code", "well_identifier", "source_kind", "source_instance_id"],
    }


def _identity_errors(entry: dict[str, Any], revision: str, version: str) -> list[dict[str, str]]:
    errors = []
    path = entry.get("source_path", "")
    match = re.fullmatch(r"dataset/([0-9])/(WELL-\d+_\d+|SIMULATED_\d+|DRAWN_\d+)\.parquet", path)
    if not match:
        return [finding("source_identifier", "Unrecognized upstream instance path.")]
    stem = match[2]
    kind = "real" if stem.startswith("WELL-") else "simulated" if stem.startswith("SIMULATED_") else "drawn"
    well = stem.split("_")[0] if kind == "real" else None
    expected_id = "3w:" + hashlib.sha256(f"{revision}:{path}".encode()).hexdigest()
    expected = {"event_code": int(match[1]), "source_kind": kind, "well_identifier": well,
                "source_instance_id": expected_id,
                "local_path": f"data/raw/3w/{version}/{revision}/{path}"}
    for key, value in expected.items():
        if entry.get(key) != value:
            errors.append(finding("manifest_identity", f"{key} disagrees with pinned source path."))
    return errors


def audit_manifest(manifest_path: Path, repo_root: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Acquisition manifest must be a JSON object.")
    if manifest.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported acquisition manifest schema_version.")
    dataset = manifest["dataset"]
    if not isinstance(dataset, dict):
        raise ValueError("Manifest dataset must be an object.")
    revision, version = dataset["revision"], dataset["version"]
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Dataset revision must be a pinned 40-character Git SHA.")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Dataset version must be a semantic version string.")
    if dataset.get("repository") != "https://github.com/petrobras/3W":
        raise ValueError("Only the documented Petrobras 3W repository is supported.")
    entries = manifest["files"]
    metadata = manifest["metadata"]
    if not isinstance(entries, list) or not entries or not all(isinstance(entry, dict) for entry in entries):
        raise ValueError("Manifest files must be a nonempty array of objects.")
    if not isinstance(metadata, list) or not metadata or not all(isinstance(entry, dict) for entry in metadata):
        raise ValueError("Manifest metadata must be a nonempty array of objects.")
    if not isinstance(manifest["selection"], dict):
        raise ValueError("Manifest selection must be an object.")
    for key in ("source_path", "local_path", "source_instance_id"):
        if len({entry[key] for entry in entries}) != len(entries):
            raise ValueError(f"Duplicate manifest {key} values.")
    metadata_results = []
    for entry in manifest["metadata"]:
        path = resolve_raw_path(repo_root, entry["local_path"])
        integrity = verify_file(path, entry)
        metadata_results.append({"source_path": entry["source_path"], **integrity})
    bad_metadata = [item for item in metadata_results if not item["ok"]]
    if bad_metadata:
        raise ValueError("Metadata integrity check failed: " + ", ".join(item["source_path"] for item in bad_metadata))
    ini_entries = [entry for entry in manifest["metadata"] if entry["source_path"] == "dataset/dataset.ini"]
    if len(ini_entries) != 1:
        raise ValueError("Exactly one verified dataset/dataset.ini entry is required.")
    registry = parse_registry(resolve_raw_path(repo_root, ini_entries[0]["local_path"]))
    if registry["dataset_version"] != version:
        raise ValueError("Manifest version differs from verified dataset.ini.")
    sensors = registry["sensor_columns"]
    files = []
    for entry in entries:
        path = resolve_raw_path(repo_root, entry["local_path"])
        integrity = verify_file(path, entry)
        record = {**entry, "integrity": integrity, "readable": False,
                  "errors": _identity_errors(entry, revision, version) + integrity["errors"], "warnings": []}
        if integrity["ok"] and not record["errors"]:
            try:
                parquet = pq.ParquetFile(path)
                record["parquet_schema"] = [{"name": field.name, "type": str(field.type), "nullable": field.nullable} for field in parquet.schema_arrow]
                record["parquet_row_groups"] = parquet.num_row_groups
                record["parquet_rows"] = parquet.metadata.num_rows
                record["parquet_compression"] = sorted({parquet.metadata.row_group(i).column(j).compression for i in range(parquet.num_row_groups) for j in range(parquet.metadata.row_group(i).num_columns)})
                frame = pd.read_parquet(path, engine="pyarrow")
                record.update(inspect_frame(frame, sensor_names=sensors,
                                            valid_labels={int(code) for code in registry["class_labels"]},
                                            valid_states=set(STATE_MEANINGS)))
                record["readable"] = True
                if len(frame) != record["parquet_rows"]:
                    record["errors"].append(finding("parquet_row_count", "Pandas and Parquet footer row counts differ."))
                if "class" in frame:
                    allowed_family = {code for code, spec in registry["class_labels"].items() if spec["base_code"] in {0, entry["event_code"]}}
                    record["other_family_row_count"] = sum(count for code, count in record["class_distribution"].items() if code not in allowed_family and code != "null")
                    if record["other_family_row_count"]:
                        record["warnings"].append(finding("other_family_rows", "Valid row classes differ from the enclosing directory; directory is not a row-label restriction."))
                record["unchanged_after_read"] = verify_file(path, entry)["ok"]
                if not record["unchanged_after_read"]:
                    record["errors"].append(finding("changed_during_audit", "Raw bytes changed while being audited."))
            except (OSError, ValueError, TypeError, pa.ArrowException) as exc:
                record["errors"].append(finding("parquet_read_failed", f"{type(exc).__name__}: {exc}"))
        files.append(record)
    aggregate: dict[str, Any] = {
        "selected_files": len(files), "readable_files": sum(record["readable"] for record in files),
        "total_size_bytes": sum(record.get("size_bytes", 0) for record in files),
        "total_rows": sum(record.get("rows", 0) for record in files),
        "files_by_origin": dict(Counter(record["source_kind"] for record in files)),
        "files_by_event_directory": dict(sorted(Counter(str(record["event_code"]) for record in files).items())),
        "class_distribution": {}, "state_distribution": {}, "sensors": {}, "by_origin": {},
    }
    for field in ("class_distribution", "state_distribution"):
        counter: Counter[str] = Counter()
        for record in files:
            counter.update(record.get(field, {}))
        aggregate[field] = dict(sorted(counter.items()))
    for name in sensors:
        present = [record for record in files if name in record.get("sensor_summary", {})]
        rows = sum(record["rows"] for record in present)
        missing = sum(record["sensor_summary"][name]["missing_count"] for record in present)
        aggregate["sensors"][name] = {"observed_rows": rows, "missing_count": missing,
                                      "missing_fraction": missing / rows if rows else None,
                                      "files_all_missing": sum(record["sensor_summary"][name]["all_missing"] for record in present)}
    for origin in ("real", "simulated", "drawn"):
        group = [record for record in files if record["source_kind"] == origin]
        rows = sum(record.get("rows", 0) for record in group)
        classes: Counter[str] = Counter()
        states: Counter[str] = Counter()
        for record in group:
            classes.update(record.get("class_distribution", {}))
            states.update(record.get("state_distribution", {}))
        aggregate["by_origin"][origin] = {
            "files": len(group), "rows": rows, "class_distribution": dict(sorted(classes.items())),
            "state_distribution": dict(sorted(states.items())),
            "sensor_missing_count": {name: sum(record.get("sensor_summary", {}).get(name, {}).get("missing_count", 0) for record in group) for name in sensors},
        }
    well_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    byte_groups: dict[str, list[str]] = defaultdict(list)
    content_groups: dict[str, list[str]] = defaultdict(list)
    for record in files:
        byte_groups[record["sha256"]].append(record["source_path"])
        if record.get("content_fingerprint"):
            content_groups[record["content_fingerprint"]].append(record["source_path"])
        if record["source_kind"] == "real":
            well_groups[record["well_identifier"]].append(record)
    overlaps = []
    for well, group in well_groups.items():
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                a, b = left.get("timestamp", {}), right.get("timestamp", {})
                if all([a.get("minimum"), a.get("maximum"), b.get("minimum"), b.get("maximum")]):
                    start = max(pd.Timestamp(a["minimum"]), pd.Timestamp(b["minimum"]))
                    end = min(pd.Timestamp(a["maximum"]), pd.Timestamp(b["maximum"]))
                    if start <= end:
                        overlaps.append({"well_identifier": well, "left": left["source_path"], "right": right["source_path"], "start": start.isoformat(), "end": end.isoformat()})
    real_support = {str(code): sorted({record["well_identifier"] for record in files if record["source_kind"] == "real" and record["event_code"] == code}) for code in range(10)}
    observed_real_support = {
        str(code): sorted({record["well_identifier"] for record in files
                          if record["source_kind"] == "real" and any(
                              count > 0 and label in registry["class_labels"]
                              and registry["class_labels"][label]["base_code"] == code
                              for label, count in record.get("class_distribution", {}).items())})
        for code in range(10)
    }
    errors = [{"source_path": record["source_path"], **issue} for record in files for issue in record["errors"]]
    warnings = [{"source_path": record["source_path"], **issue} for record in files for issue in record["warnings"]]
    code_revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=False)
    git_status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, check=False)
    return {
        "schema_version": "1.0.0", "audit_kind": "bounded_raw_source_audit_not_training_data",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": dataset, "selection": manifest["selection"], "registry": registry,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "tooling": {"python": platform.python_version(), "platform": platform.platform(),
                    "dependencies": {name: importlib.metadata.version(name) for name in ("pandas", "numpy", "pyarrow")},
                    "base_git_revision": code_revision.stdout.strip() if code_revision.returncode == 0 else None,
                    "working_tree_dirty": bool(git_status.stdout.strip()) if git_status.returncode == 0 else None,
                    "validator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "downloader_sha256": hashlib.sha256((repo_root / "scripts/download_data.py").read_bytes()).hexdigest()
                    if (repo_root / "scripts/download_data.py").exists() else None,
                    "requirements_sha256": hashlib.sha256((repo_root / "requirements-data.txt").read_bytes()).hexdigest()
                    if (repo_root / "requirements-data.txt").exists() else None},
        "validation": {"status": "failed" if errors else "passed", "errors": errors, "warnings": warnings},
        "metadata_integrity": metadata_results, "aggregate": aggregate, "files": files,
        "leakage_audit": {
            "duplicate_source_bytes": [paths for paths in byte_groups.values() if len(paths) > 1],
            "duplicate_frame_content": [paths for paths in content_groups.values() if len(paths) > 1],
            "real_well_groups": {well: [record["source_path"] for record in group] for well, group in sorted(well_groups.items())},
            "overlapping_real_well_intervals": overlaps,
            "selected_real_well_ids_by_directory": real_support,
            "observed_real_well_ids_by_event_family": observed_real_support,
            "split_readiness": "not_established_no_splits_created",
            "required_controls": [
                "Group verified related well/instance segments before any windows or partitions.",
                "Exclude class, state, identifiers, filenames, origin and directory labels from features.",
                "Use globally documented row labels; never broadcast the directory label across rows.",
                "Missing sensor patterns and source interpolation may reveal origin or future information.",
                "Synthetic families and physical identity equivalence remain unverified.",
                "This size-biased stratified audit cannot estimate dataset prevalence or model readiness.",
            ],
        },
        "raw_files_unchanged_during_audit": all(record.get("unchanged_after_read", False) for record in files),
        "limitations": [
            "Only selected instances were read; full-tree file counts are not row counts.",
            "No timezone localization, resampling, imputation, normalization, feature generation or training was performed.",
            "Source missing values and labels are retained unchanged; null labels mean unknown.",
            "No train/validation/test split or model event-family scope is approved by this audit.",
            "Git SHA-1 verifies bytes against pinned Git metadata; SHA-256 is additionally recorded for local integrity.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "data/manifests/subset.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/data_summary.json")
    args = parser.parse_args(argv)
    try:
        output = safe_report_path(REPO_ROOT, args.output, args.manifest)
        report = audit_manifest(args.manifest, REPO_ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=output.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except (OSError, KeyError, TypeError, ValueError, configparser.Error) as exc:
        print(f"Audit could not complete; report not updated: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": report["validation"]["status"], "files": report["aggregate"]["selected_files"],
                      "rows": report["aggregate"]["total_rows"], "errors": len(report["validation"]["errors"]),
                      "warnings": len(report["validation"]["warnings"])}))
    return 0 if report["validation"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
