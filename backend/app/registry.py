"""Read-only registry of verified, non-test historical sources."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.errors import ServiceError
from ml.data_pipeline import CausalFeaturePipeline, SourceMetadata

SELECTION_SHA256 = "dfbe88250db8808d58730ab6f0010da3c548cb4b1c26715ba4a4b78057e7130b"


def trusted_selection(root: Path) -> dict:
    payload = (root / "reports/experiments/selection.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != SELECTION_SHA256:
        raise ValueError("Frozen selection integrity failure")
    return json.loads(payload)


@dataclass(frozen=True)
class RegisteredSource:
    source: SourceMetadata
    frame: pd.DataFrame


class Registry:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.records: dict[str, RegisteredSource] = {}
        self.units: dict[str, str] = {}
        self.sensor_names: tuple[str, ...] = ()
        self.ready = False

    def startup(self) -> None:
        selection = trusted_selection(self.root)
        item = selection["data_provenance"]["artifacts"]["preprocessor"]
        path = (self.root / item["path"]).resolve()
        if not path.is_relative_to(self.root) or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Frozen preprocessing integrity failure")
        state = CausalFeaturePipeline.load(path).state
        if state is None:
            raise ValueError("Preprocessing unavailable")
        self.sensor_names = state.sensor_names
        registry_bytes = (self.root / "data/manifests/dataset_metadata.json").read_bytes()
        registry_hash = hashlib.sha256(registry_bytes).hexdigest()
        self.units = {r["name"]: r["unit_or_domain"] for r in json.loads(registry_bytes)["sensor_columns"]}
        if set(self.units) != set(self.sensor_names):
            raise ValueError("Sensor registry mismatch")
        records = {}
        raw_root = (self.root / "data/raw/3w").resolve()
        for assignment in state.split_manifest.assignments:
            if assignment.partition not in {"train", "validation"}:
                continue
            source = assignment.source
            if source.origin != "real" or source.registry_sha256 != registry_hash:
                raise ValueError("Unsupported registry source")
            raw_path = (raw_root / source.dataset_version / source.dataset_revision / source.source_path).resolve()
            if not raw_path.is_relative_to(raw_root):
                raise ValueError("Source escapes registered directory")
            payload = raw_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != source.sha256:
                raise ValueError("Source integrity failure")
            # Never decode labels, test sources or excluded synthetic sources.
            frame = pd.read_parquet(BytesIO(payload), columns=list(self.sensor_names), engine="pyarrow")
            if (not isinstance(frame.index, pd.DatetimeIndex) or frame.empty
                    or frame.index.tz is not None or frame.index.hasnans
                    or not frame.index.is_unique or not frame.index.is_monotonic_increasing
                    or (np.diff(frame.index.as_unit("ns").asi8) != 1_000_000_000).any()
                    or np.isinf(frame.to_numpy(dtype=float)).any()):
                raise ValueError("Invalid historical sensor frame")
            records[source.instance_id] = RegisteredSource(source, frame)
        if len(records) != 10:
            raise ValueError("Incomplete approved train/validation registry")
        self.records = records
        self.ready = True

    def record(self, source_instance_id: str) -> RegisteredSource:
        if not self.ready:
            raise ServiceError("DATA_UNAVAILABLE", "Historical data is unavailable", 503)
        if source_instance_id not in self.records:
            raise ServiceError("SOURCE_NOT_FOUND", "Registered source not found", 404)
        return self.records[source_instance_id]

    def list_wells(self) -> list[dict]:
        if not self.ready:
            raise ServiceError("DATA_UNAVAILABLE", "Historical data is unavailable", 503)
        wells: dict[str, dict] = {}
        for source_id, record in sorted(self.records.items()):
            source, frame = record.source, record.frame
            well = wells.setdefault(source.well_id, {"well_id": source.well_id,
                "well_identity_kind": "anonymized_well", "source_kind": "real",
                "source_instances": [], "mode": "historical_inference"})
            well["source_instances"].append({"source_instance_id": source_id,
                "source_start": frame.index[0].isoformat(), "source_end": frame.index[-1].isoformat(),
                "row_count": len(frame)})
        return [wells[key] for key in sorted(wells)]

    def telemetry(self, well_id: str, source_instance_id: str, offset: int,
                  limit: int, sensors: list[str] | None = None) -> dict:
        record = self.record(source_instance_id)
        if record.source.well_id != well_id:
            raise ServiceError("SOURCE_NOT_FOUND", "Registered well/source pair not found", 404)
        columns = list(self.sensor_names) if sensors is None else sensors
        if not columns or len(set(columns)) != len(columns) or not set(columns) <= set(self.sensor_names):
            raise ServiceError("INVALID_SENSORS", "Use unique registered sensor names", 422)
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 1000:
            raise ServiceError("INVALID_RANGE", "Invalid telemetry pagination", 422)
        frame = record.frame.iloc[offset:offset + limit].loc[:, columns]
        items = [{"timestamp": timestamp.isoformat(), "sensors": {
            name: None if pd.isna(value) else float(value) for name, value in row.items()}}
            for timestamp, row in frame.iterrows()]
        next_offset = offset + len(items) if offset + len(items) < len(record.frame) else None
        return {"well_id": well_id, "source_instance_id": source_instance_id, "source_kind": "real",
            "time_basis": "source_naive_assumed_utc", "mode": "historical_inference",
            "items": items, "next_offset": next_offset}

    def window(self, source_instance_id: str, endpoint_position: int) -> tuple[SourceMetadata, pd.DataFrame]:
        record = self.record(source_instance_id)
        if type(endpoint_position) is not int or not 0 <= endpoint_position < len(record.frame):
            raise ServiceError("INVALID_ENDPOINT", "Endpoint is outside the registered source", 422)
        if endpoint_position >= 59 and (endpoint_position - 59) % 10:
            raise ServiceError("INVALID_ENDPOINT", "Endpoint must follow the frozen 60-row/10-row policy", 422)
        start = max(0, endpoint_position - 59)
        return record.source, record.frame.iloc[start:endpoint_position + 1].copy(deep=True)
