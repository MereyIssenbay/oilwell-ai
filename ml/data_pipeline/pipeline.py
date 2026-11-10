"""Causal window extraction and frozen training-only feature normalization."""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from .io import read_json, validate_instance
from .models import (PIPELINE_VERSION, SENSOR_COLUMNS, TRANSIENT_TO_FAMILY, FrozenModel,
                     Instance, PipelineConfig, Sha256, SplitManifest, WindowBatch,
                     fingerprint, make_batch)
from ml.features import feature_names, summarize_windows

METADATA_COLUMNS = ("instance_id", "group_id", "partition", "window_start", "timestamp",
                    "endpoint_position", "source_path", "origin", "well_id", "sha256")
TARGET_COLUMNS = ("raw_class", "raw_state", "event_family", "phase", "supervised_eligible")


def _dependencies() -> tuple[tuple[str, str], ...]:
    return tuple((name, importlib.metadata.version(name))
                 for name in ("numpy", "pandas", "pyarrow", "pydantic"))


def _implementation_hash() -> str:
    package = Path(__file__).parent
    files = sorted(package.glob("*.py")) + sorted((package.parent / "features").glob("*.py"))
    return fingerprint({str(path.relative_to(package.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in files})


class PreprocessorState(FrozenModel):
    version: Literal["1.0.0"] = PIPELINE_VERSION
    config: PipelineConfig
    sensor_names: tuple[str, ...]
    input_feature_names: tuple[str, ...]
    retained_features: tuple[str, ...]
    dropped_features: tuple[str, ...]
    medians: tuple[float, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    training_instance_ids: tuple[str, ...]
    training_group_ids: tuple[str, ...]
    training_window_count: int = Field(strict=True, gt=0)
    training_batch_fingerprint: Sha256
    split_manifest: SplitManifest
    implementation_sha256: Sha256
    dependency_versions: tuple[tuple[str, str], ...]
    fingerprint: Sha256

    @model_validator(mode="after")
    def valid_state(self) -> PreprocessorState:
        if (not self.sensor_names or len(set(self.sensor_names)) != len(self.sensor_names)
                or set(self.sensor_names) - set(SENSOR_COLUMNS)):
            raise ValueError("Invalid state sensor allowlist")
        if self.input_feature_names != feature_names(self.sensor_names):
            raise ValueError("State feature schema mismatch")
        retained = set(self.retained_features)
        dropped = set(self.dropped_features)
        if (not retained or len(retained) != len(self.retained_features)
                or len(dropped) != len(self.dropped_features) or retained & dropped
                or retained | dropped != set(self.input_feature_names)
                or tuple(f for f in self.input_feature_names if f in retained) != self.retained_features
                or tuple(f for f in self.input_feature_names if f in dropped) != self.dropped_features):
            raise ValueError("Invalid retained/dropped feature schema")
        length = len(self.retained_features)
        if any(len(values) != length for values in (self.medians, self.means, self.scales)):
            raise ValueError("State statistic lengths do not match retained features")
        if not np.isfinite(np.array((self.medians, self.means, self.scales))).all():
            raise ValueError("Nonfinite normalization state")
        if any(value <= 0 for value in self.scales):
            raise ValueError("Normalization scales must be positive")
        if not self.training_instance_ids or not self.training_group_ids:
            raise ValueError("Training provenance required")
        expected_groups = set()
        for source_id in self.training_instance_ids:
            entry = self.split_manifest.assignment_for(source_id)
            if entry.partition != "train":
                raise ValueError("Fitted state contains a nontraining source")
            expected_groups.add(entry.group_id)
        if expected_groups != set(self.training_group_ids):
            raise ValueError("Training group provenance mismatch")
        if fingerprint(self.model_dump(mode="json", exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("Preprocessor state fingerprint mismatch")
        return self


class CausalFeaturePipeline:
    """Fit only on ``batch.subset('train')``; transform never learns statistics.

    Source labels affect only the separate target table. Normalization is fitted
    on every assigned train endpoint, including unknown-label windows. Output
    quality must accompany normalized features for downstream abstention.
    """

    def __init__(self, config: PipelineConfig | None = None,
                 sensor_names: tuple[str, ...] | list[str] = SENSOR_COLUMNS):
        self.config = PipelineConfig() if config is None else config
        if not isinstance(self.config, PipelineConfig):
            raise ValueError("Validated PipelineConfig required")
        self.sensor_names = tuple(sensor_names)
        if (not self.sensor_names or len(set(self.sensor_names)) != len(self.sensor_names)
                or set(self.sensor_names) - set(SENSOR_COLUMNS)):
            raise ValueError("Only unique exact registry sensor names are allowed")
        self.state: PreprocessorState | None = None

    def build(self, instances: tuple[Instance, ...] | list[Instance],
              split: SplitManifest) -> WindowBatch:
        split = self._validated_split(split)
        if len({i.metadata.instance_id for i in instances}) != len(instances):
            raise ValueError("Cannot build repeated source instances")
        blocks, counts, records, targets, window_ids = [], [], [], [], []
        cadence_ns = round(self.config.cadence_seconds * 1e9)
        if cadence_ns <= 0 or not np.isclose(cadence_ns / 1e9, self.config.cadence_seconds,
                                             atol=0, rtol=1e-12):
            raise ValueError("Cadence must be representable as whole nanoseconds")
        for instance in sorted(instances, key=lambda item: item.metadata.instance_id):
            validate_instance(instance)
            source = instance.metadata
            entry = split.assignment_for(source.instance_id)
            if source != entry.source:
                raise ValueError("Source metadata does not match its frozen split assignment")
            if entry.partition == "excluded":
                continue
            frame = instance.frame
            if not set(self.sensor_names).issubset(frame.columns):
                raise ValueError("A configured sensor column is missing from the instance schema")
            differences = np.diff(frame.index.as_unit("ns").asi8)
            if np.any(differences < cadence_ns):
                raise ValueError("Observed cadence is finer than configured; resampling is not implemented")
            cuts = np.r_[0, np.flatnonzero(differences != cadence_ns) + 1, len(frame)]
            values = frame.loc[:, self.sensor_names].to_numpy(dtype=float, na_value=np.nan)
            for start, stop in zip(cuts, cuts[1:]):
                endpoints = np.arange(start + self.config.window_rows - 1, stop,
                                      self.config.stride_rows, dtype=np.int64)
                if not len(endpoints):
                    continue
                feature_block, count_block = summarize_windows(
                    values, endpoints, self.config.window_rows, self.config.cadence_seconds)
                blocks.append(feature_block)
                counts.append(count_block)
                for row_number, position in enumerate(endpoints):
                    timestamp = frame.index[position]
                    window_start = frame.index[position - self.config.window_rows + 1]
                    window_id = fingerprint({"source": source.instance_id, "sha256": source.sha256,
                                             "endpoint": timestamp.isoformat(),
                                             "window_config": self.config.model_dump(mode="json", exclude={"transient_policy"}),
                                             "sensors": self.sensor_names})
                    window_ids.append(window_id)
                    records.append((source.instance_id, entry.group_id, entry.partition, window_start,
                                    timestamp, int(position), source.source_path, source.origin,
                                    source.well_id, source.sha256))
                    raw = frame["class"].iloc[position]
                    state = frame["state"].iloc[position]
                    if pd.isna(raw):
                        family, phase = pd.NA, "unknown"
                    elif int(raw) in TRANSIENT_TO_FAMILY:
                        phase = "transient"
                        family = (TRANSIENT_TO_FAMILY[int(raw)]
                                  if self.config.transient_policy == "family" else pd.NA)
                    else:
                        family = int(raw)
                        phase = "normal" if family == 0 else "event"
                    eligible = not pd.isna(family) and count_block[row_number].sum() > 0
                    targets.append((raw, state, family, phase, bool(eligible)))
        index = pd.Index(window_ids, name="window_id")
        features = pd.DataFrame(np.concatenate(blocks) if blocks else
                                np.empty((0, len(self.sensor_names) * 6)),
                                index=index, columns=feature_names(self.sensor_names))
        observed = np.concatenate(counts) if counts else np.empty((0, len(self.sensor_names)), dtype=int)
        quality = pd.DataFrame(observed, index=index,
                               columns=[f"{sensor}__observed_count" for sensor in self.sensor_names])
        quality["observed_cells"] = observed.sum(axis=1)
        quality["selected_sensor_cells"] = self.config.window_rows * len(self.sensor_names)
        quality["observed_fraction"] = quality.observed_cells / quality.selected_sensor_cells
        quality["all_missing"] = quality.observed_cells.eq(0)
        metadata = pd.DataFrame(records, index=index, columns=METADATA_COLUMNS)
        for column in ("window_start", "timestamp"):
            metadata[column] = pd.to_datetime(metadata[column])
        target_frame = pd.DataFrame(targets, index=index, columns=TARGET_COLUMNS)
        for column in ("raw_class", "raw_state", "event_family"):
            target_frame[column] = pd.array(target_frame[column], dtype="Int16")
        target_frame["supervised_eligible"] = target_frame["supervised_eligible"].astype(bool)
        batch = make_batch(features, target_frame, metadata, quality,
                           self.config.fingerprint, split.fingerprint)
        self._validate_batch(batch, split)
        if split.config.mode == "protected":
            self._check_endpoint_support(batch, split)
        return batch

    @staticmethod
    def _validated_split(split: SplitManifest) -> SplitManifest:
        if not isinstance(split, SplitManifest):
            raise ValueError("Validated SplitManifest required")
        return SplitManifest.model_validate(split.model_dump(mode="json"))

    def _validate_batch(self, batch: WindowBatch, split: SplitManifest) -> None:
        if not isinstance(batch, WindowBatch):
            raise ValueError("WindowBatch required")
        batch.validate()
        if batch.split_fingerprint != split.fingerprint or batch.config_fingerprint != self.config.fingerprint:
            raise ValueError("Batch split/config fingerprint mismatch")
        if tuple(batch.features.columns) != feature_names(self.sensor_names):
            raise ValueError("Batch feature schema mismatch")
        if tuple(batch.metadata.columns) != METADATA_COLUMNS or tuple(batch.targets.columns) != TARGET_COLUMNS:
            raise ValueError("Batch target/provenance schema mismatch")
        if np.isinf(batch.features.to_numpy(dtype=float)).any():
            raise ValueError("Infinite feature value")
        for source_id, rows in batch.metadata.groupby("instance_id", sort=False):
            assigned = split.assignment_for(source_id)
            expected = {"partition": assigned.partition, "group_id": assigned.group_id,
                        "origin": assigned.source.origin, "sha256": assigned.source.sha256,
                        "source_path": assigned.source.source_path}
            if assigned.partition == "excluded":
                raise ValueError("Excluded source appears in window batch")
            for column, value in expected.items():
                if not rows[column].eq(value).all():
                    raise ValueError(f"Window source assignment mismatch in {column}")
            well_matches = (rows.well_id.isna().all() if assigned.source.well_id is None
                            else rows.well_id.eq(assigned.source.well_id).all())
            if not well_matches:
                raise ValueError("Window well assignment mismatch")

    @staticmethod
    def _check_endpoint_support(batch: WindowBatch, split: SplitManifest) -> None:
        for partition in ("train", "validation", "test"):
            for family in split.config.required_families:
                mask = (batch.metadata.partition.eq(partition) & batch.metadata.origin.eq("real")
                        & batch.targets.supervised_eligible & batch.targets.event_family.eq(family).fillna(False))
                groups = batch.metadata.loc[mask, "group_id"].nunique()
                if groups < split.config.minimum_groups_per_family:
                    raise ValueError(f"{partition}: family {family} lacks eligible window endpoint support")

    def fit(self, batch: WindowBatch, split: SplitManifest) -> CausalFeaturePipeline:
        if self.state is not None:
            raise ValueError("Preprocessor is frozen; create a new pipeline to fit again")
        split = self._validated_split(split)
        self._validate_batch(batch, split)
        if batch.features.empty or not batch.metadata.partition.eq("train").all():
            raise ValueError("Fit requires a nonempty train-only window batch")
        retained = tuple(column for column in batch.features if batch.features[column].notna().any())
        dropped = tuple(column for column in batch.features if column not in retained)
        if not retained:
            raise ValueError("No observed training feature; cannot fabricate a usable pipeline")
        values = batch.features.loc[:, retained].to_numpy(dtype=float)
        medians = np.nanmedian(values, axis=0)
        imputed = np.where(np.isnan(values), medians, values)
        means = imputed.mean(axis=0)
        scales = imputed.std(axis=0, ddof=0)
        scales[scales == 0] = 1.0
        if not np.isfinite(np.array((medians, means, scales))).all():
            raise ValueError("Normalization statistics overflowed")
        payload = {"version": PIPELINE_VERSION, "config": self.config.model_dump(mode="json"),
                   "sensor_names": self.sensor_names,
                   "input_feature_names": feature_names(self.sensor_names),
                   "retained_features": retained, "dropped_features": dropped,
                   "medians": medians.tolist(), "means": means.tolist(), "scales": scales.tolist(),
                   "training_instance_ids": sorted(batch.metadata.instance_id.unique()),
                   "training_group_ids": sorted(batch.metadata.group_id.unique()),
                   "training_window_count": len(batch.features),
                   "training_batch_fingerprint": batch.content_fingerprint,
                   "split_manifest": split.model_dump(mode="json"),
                   "implementation_sha256": _implementation_hash(),
                   "dependency_versions": _dependencies()}
        self.state = PreprocessorState.model_validate({**payload, "fingerprint": fingerprint(payload)})
        return self

    def transform(self, batch: WindowBatch, split: SplitManifest) -> pd.DataFrame:
        if self.state is None:
            raise ValueError("Fit or load a preprocessor before transform")
        split = self._validated_split(split)
        self._validate_batch(batch, split)
        if split.fingerprint != self.state.split_manifest.fingerprint:
            raise ValueError("Transform split does not match fitted split")
        if self.config != self.state.config or self.sensor_names != self.state.sensor_names:
            raise ValueError("Pipeline configuration changed after fit")
        values = batch.features.loc[:, self.state.retained_features].to_numpy(dtype=float)
        imputed = np.where(np.isnan(values), np.array(self.state.medians), values)
        normalized = (imputed - np.array(self.state.means)) / np.array(self.state.scales)
        if not np.isfinite(normalized).all():
            raise ValueError("Nonfinite transformed feature")
        return pd.DataFrame(normalized, index=batch.features.index,
                            columns=self.state.retained_features)

    def save(self, path: Path) -> None:
        if self.state is None:
            raise ValueError("Cannot serialize an unfitted preprocessor")
        state = PreprocessorState.model_validate(self.state.model_dump(mode="json"))
        Path(path).write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CausalFeaturePipeline:
        state = PreprocessorState.model_validate(read_json(Path(path)))
        if state.implementation_sha256 != _implementation_hash():
            raise ValueError("State implementation hash mismatch; use the recorded code revision")
        if state.dependency_versions != _dependencies():
            raise ValueError("State dependency versions mismatch; use the pinned environment")
        pipeline = cls(state.config, state.sensor_names)
        pipeline.state = state
        return pipeline
