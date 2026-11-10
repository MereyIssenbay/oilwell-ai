"""Read original Parquets with checksum, exact-schema and time validation."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Annotated, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from .models import (DATASET_REVISION, SENSOR_COLUMNS, VALID_CLASSES, ExposureLedger,
                     FrozenModel, Instance, Sha256, SourceMetadata)


class AcquiredFile(FrozenModel):
    source_path: str
    local_path: str
    size_bytes: Annotated[int, Field(strict=True, gt=0)]
    git_blob_sha1: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    sha256: Sha256
    source_kind: Literal["real", "simulated", "drawn"]
    event_code: Annotated[int, Field(strict=True, ge=0, le=9)]
    well_identifier: str | None
    source_instance_id: str


def read_json(path: Path) -> dict:
    def invalid(value: str) -> None:
        raise ValueError(f"Nonfinite JSON value: {value}")
    def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    payload = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid,
                         object_pairs_hook=unique_pairs)
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    return payload


def validate_instance(instance: Instance, require_all_sensors: bool = False) -> None:
    if not isinstance(instance, Instance) or not isinstance(instance.metadata, SourceMetadata):
        raise ValueError("Validated Instance/SourceMetadata required")
    frame = instance.frame
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("Instance must contain observations")
    if not frame.columns.is_unique:
        raise ValueError("Duplicate columns")
    allowed = set(SENSOR_COLUMNS) | {"class", "state"}
    if set(frame.columns) - allowed:
        raise ValueError("Unexpected data column; metadata is not a sensor")
    if not {"class", "state"}.issubset(frame.columns):
        raise ValueError("Both source label columns must be present")
    if require_all_sensors and set(frame.columns) != allowed:
        raise ValueError("Original Parquet schema does not match pinned sensor registry")
    index = frame.index
    if (not isinstance(index, pd.DatetimeIndex) or index.tz is not None or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing):
        raise ValueError("Source index must be unique increasing naive timestamps; timezone is unknown")
    for column in set(frame.columns) & set(SENSOR_COLUMNS):
        if not pd.api.types.is_float_dtype(frame[column].dtype):
            raise ValueError(f"Sensor must be floating point: {column}")
        values = frame[column].to_numpy(dtype=float, na_value=np.nan)
        if np.isinf(values).any():
            raise ValueError(f"Infinite sensor observation: {column}")
    for column, valid in (("class", VALID_CLASSES), ("state", set(range(9)))):
        series = frame[column]
        if not pd.api.types.is_integer_dtype(series.dtype):
            raise ValueError(f"Nullable integer label required: {column}")
        if not series.dropna().isin(valid).all():
            raise ValueError(f"Unknown documented label code in {column}")


def load_instances(root: Path, manifest_path: Path | None = None,
                   registry_path: Path | None = None) -> tuple[Instance, ...]:
    root = Path(root).resolve()
    manifest_path = root / "data/manifests/subset.json" if manifest_path is None else Path(manifest_path)
    registry_path = root / "data/manifests/dataset_metadata.json" if registry_path is None else Path(registry_path)
    manifest_path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    registry_path = registry_path if registry_path.is_absolute() else root / registry_path
    manifest = read_json(manifest_path)
    registry = read_json(registry_path)
    dataset = manifest.get("dataset")
    if (manifest.get("schema_version") != "1.0.0" or manifest.get("status") != "complete"
            or not isinstance(dataset, dict) or dataset.get("revision") != DATASET_REVISION
            or dataset.get("version") != "2.0.0"):
        raise ValueError("Expected completed acquisition manifest at the pinned 3W revision")
    if (registry.get("dataset_revision") != DATASET_REVISION
            or registry.get("dataset_version") != "2.0.0"
            or tuple(s.get("name") for s in registry.get("sensor_columns", [])) != SENSOR_COLUMNS):
        raise ValueError("Pinned sensor registry mismatch")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Nonempty manifest file list required")
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    registry_hash = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    result = []
    source_paths = set()
    for payload in entries:
        entry = AcquiredFile.model_validate(payload)
        match = re.fullmatch(r"dataset/([0-9])/(WELL-\d{5}_\d+|SIMULATED_\d+|DRAWN_\d+)\.parquet",
                             entry.source_path)
        if match is None:
            raise ValueError("Source path does not follow pinned 3W identity conventions")
        directory, stem = match.groups()
        origin = "real" if stem.startswith("WELL-") else "simulated" if stem.startswith("SIMULATED_") else "drawn"
        well_id = stem.split("_", 1)[0] if origin == "real" else None
        instance_id = "3w:" + hashlib.sha256(f"{DATASET_REVISION}:{entry.source_path}".encode()).hexdigest()
        expected_local = f"data/raw/3w/2.0.0/{DATASET_REVISION}/{entry.source_path}"
        if (entry.source_kind != origin or entry.well_identifier != well_id
                or entry.event_code != int(directory) or entry.source_instance_id != instance_id
                or entry.local_path != expected_local):
            raise ValueError("Manifest source identity/local path does not match pinned source path")
        if entry.source_path in source_paths:
            raise ValueError("Duplicate source path in acquisition manifest")
        source_paths.add(entry.source_path)
        path = (root / entry.local_path).resolve()
        if not path.is_relative_to(root / "data/raw"):
            raise ValueError("Original source path escapes data/raw")
        original = path.read_bytes()
        git_blob = hashlib.sha1(b"blob " + str(len(original)).encode() + b"\0" + original).hexdigest()
        if (len(original) != entry.size_bytes or hashlib.sha256(original).hexdigest() != entry.sha256
                or git_blob != entry.git_blob_sha1):
            raise ValueError(f"Original source checksum mismatch: {entry.source_path}")
        metadata = SourceMetadata(instance_id=entry.source_instance_id, source_path=entry.source_path,
                                  sha256=entry.sha256, origin=entry.source_kind,
                                  well_id=entry.well_identifier, dataset_revision=dataset["revision"],
                                  dataset_version=dataset["version"], manifest_sha256=manifest_hash,
                                  registry_sha256=registry_hash)
        instance = Instance(metadata, pd.read_parquet(BytesIO(original), engine="pyarrow"))
        validate_instance(instance, require_all_sensors=True)
        result.append(instance)
    if len({item.metadata.instance_id for item in result}) != len(result):
        raise ValueError("Duplicate source instance ID in acquisition manifest")
    return tuple(sorted(result, key=lambda item: item.metadata.instance_id))


def load_exposure(path: Path) -> ExposureLedger:
    payload = read_json(Path(path))
    exposed = payload.get("eda_exposure")
    if (not isinstance(exposed, dict)
            or exposed.get("status") != "development_exposed_not_clean_final_test"):
        raise ValueError("Explicit recognized exposure ledger required")
    try:
        ids = tuple(sorted(item["source_instance_id"] for item in exposed["instances"]))
        wells = tuple(sorted(exposed["real_well_ids"]))
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed exposure ledger") from exc
    return ExposureLedger(instance_ids=ids, real_well_ids=wells,
                          ledger_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
