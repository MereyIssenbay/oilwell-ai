"""Validated, versioned data-pipeline contracts; no estimator training."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Annotated, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ml.features.constants import FEATURES

PIPELINE_VERSION = "1.0.0"
DATASET_REVISION = "914af287b1cf3e5207dce0da1e9dc08361c9adeb"
SENSOR_COLUMNS = (
    "ABER-CKGL", "ABER-CKP", "ESTADO-DHSV", "ESTADO-M1", "ESTADO-M2",
    "ESTADO-PXO", "ESTADO-SDV-GL", "ESTADO-SDV-P", "ESTADO-W1", "ESTADO-W2",
    "ESTADO-XO", "P-ANULAR", "P-JUS-BS", "P-JUS-CKGL", "P-JUS-CKP",
    "P-MON-CKGL", "P-MON-CKP", "P-MON-SDV-P", "P-PDG", "PT-P", "P-TPT",
    "QBS", "QGL", "T-JUS-CKP", "T-MON-CKP", "T-PDG", "T-TPT",
)
TRANSIENT_TO_FAMILY = {101: 1, 102: 2, 105: 5, 106: 6, 107: 7, 108: 8, 109: 9}
VALID_CLASSES = frozenset(range(10)) | frozenset(TRANSIENT_TO_FAMILY)
Partition = Literal["train", "validation", "test", "excluded"]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def fingerprint(value: object) -> str:
    """Stable JSON identity; nonfinite numbers are never serialized."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class PipelineConfig(FrozenModel):
    version: Literal["1.0.0"] = PIPELINE_VERSION
    window_rows: Annotated[int, Field(strict=True, ge=2)] = 60
    stride_rows: Annotated[int, Field(strict=True, ge=1)] = 10
    cadence_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1.0
    transient_policy: Literal["family", "exclude"] = "family"

    @field_validator("cadence_seconds", mode="before")
    @classmethod
    def no_boolean_cadence(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Cadence must be a positive number")
        return value

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class SplitConfig(FrozenModel):
    seed: Annotated[int, Field(strict=True, ge=0, le=2**32 - 1)] = 42
    ratios: tuple[float, float, float] = (0.6, 0.2, 0.2)
    mode: Literal["diagnostic", "protected"] = "diagnostic"
    include_synthetic_train: Annotated[bool, Field(strict=True)] = False
    required_families: tuple[int, ...] = tuple(range(10))
    minimum_groups_per_family: Annotated[int, Field(strict=True, ge=1)] = 1

    @field_validator("ratios", mode="before")
    @classmethod
    def valid_ratios(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError("Exactly three positive group ratios are required")
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) or v <= 0 for v in value):
            raise ValueError("Group ratios must be finite and positive")
        if not math.isclose(sum(value), 1.0, abs_tol=1e-12):
            raise ValueError("Group ratios must sum to one")
        return value

    @field_validator("required_families", mode="before")
    @classmethod
    def valid_families(cls, value: object) -> object:
        if not isinstance(value, (tuple, list)) or not value:
            raise ValueError("Declare at least one required family")
        if any(type(v) is not int or v not in range(10) for v in value):
            raise ValueError("Required families must be documented base labels 0..9")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate required family")
        return value


class SourceMetadata(FrozenModel):
    instance_id: Annotated[str, Field(min_length=1)]
    source_path: Annotated[str, Field(min_length=1)]
    sha256: Sha256
    origin: Literal["real", "simulated", "drawn"]
    well_id: str | None = None
    dataset_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] = DATASET_REVISION
    dataset_version: Literal["2.0.0"] = "2.0.0"
    manifest_sha256: Sha256 = "0" * 64
    registry_sha256: Sha256 = "0" * 64
    related_group: Annotated[str, Field(min_length=1)] | None = None

    @model_validator(mode="after")
    def valid_identity(self) -> SourceMetadata:
        import re
        if self.origin == "real":
            if self.well_id is None or not re.fullmatch(r"WELL-\d{5}", self.well_id):
                raise ValueError("Real data requires a published WELL-xxxxx grouping key")
        elif self.well_id is not None:
            raise ValueError("Synthetic instances do not have published physical-well IDs")
        return self


@dataclass(frozen=True)
class Instance:
    metadata: SourceMetadata
    frame: pd.DataFrame


class ExposureLedger(FrozenModel):
    instance_ids: tuple[str, ...]
    real_well_ids: tuple[str, ...]
    ledger_sha256: Sha256

    @model_validator(mode="after")
    def valid_exposures(self) -> ExposureLedger:
        import re
        if (len(set(self.instance_ids)) != len(self.instance_ids)
                or any(not value.strip() for value in self.instance_ids)
                or len(set(self.real_well_ids)) != len(self.real_well_ids)
                or any(not re.fullmatch(r"WELL-\d{5}", value) for value in self.real_well_ids)):
            raise ValueError("Exposure IDs must be unique nonempty instance IDs and published well IDs")
        return self


class SplitAssignment(FrozenModel):
    source: SourceMetadata
    group_id: Sha256
    partition: Partition


class ClassSupport(FrozenModel):
    partition: Literal["train", "validation", "test"]
    family: Annotated[int, Field(ge=0, le=9)]
    real_groups: Annotated[int, Field(ge=0)]


class SplitManifest(FrozenModel):
    version: Literal["1.0.0"] = PIPELINE_VERSION
    algorithm: Literal["sha256-ranked-connected-groups-v1"] = "sha256-ranked-connected-groups-v1"
    config: SplitConfig
    assignments: tuple[SplitAssignment, ...]
    exposure_sha256: Sha256 | None
    support: tuple[ClassSupport, ...]
    warnings: tuple[str, ...]
    fingerprint: Sha256

    @model_validator(mode="after")
    def check_integrity(self) -> SplitManifest:
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if fingerprint(payload) != self.fingerprint:
            raise ValueError("Split manifest fingerprint mismatch")
        ids = [a.source.instance_id for a in self.assignments]
        if len(set(ids)) != len(ids):
            raise ValueError("Instance appears more than once in split manifest")
        groups: dict[str, set[str]] = {}
        members: dict[str, list[str]] = {}
        identities: dict[tuple[str, str], set[str]] = {}
        for entry in self.assignments:
            members.setdefault(entry.group_id, []).append(entry.source.instance_id)
            keys = [("sha256", entry.source.sha256)]
            if entry.source.origin == "real":
                keys.append(("published-well", entry.source.well_id))
            if entry.source.related_group is not None:
                keys.append(("related-group", entry.source.related_group))
            for key in keys:
                identities.setdefault(key, set()).add(entry.group_id)
            if entry.partition != "excluded":
                groups.setdefault(entry.group_id, set()).add(entry.partition)
                if entry.source.origin != "real" and entry.partition != "train":
                    raise ValueError("Synthetic sources may only enter training")
                if entry.source.origin != "real" and not self.config.include_synthetic_train:
                    raise ValueError("Synthetic training was not enabled")
        if any(len(parts) != 1 for parts in groups.values()):
            raise ValueError("Connected group spans partitions")
        if any(len(group_ids) != 1 for group_ids in identities.values()):
            raise ValueError("A well, duplicate hash or related family was divided between groups")
        if any(fingerprint(sorted(ids)) != group_id for group_id, ids in members.items()):
            raise ValueError("Connected group identity does not match its members")
        for partition in ("train", "validation", "test"):
            if not any(a.partition == partition and a.source.origin == "real" for a in self.assignments):
                raise ValueError("Every partition must contain real connected groups")
        if self.config.mode == "protected":
            if self.exposure_sha256 is None:
                raise ValueError("Protected split requires exposure provenance")
            expected = {(partition, family) for partition in ("train", "validation", "test")
                        for family in self.config.required_families}
            if (len(self.support) != len(expected)
                    or {(s.partition, s.family) for s in self.support} != expected
                    or any(s.real_groups < self.config.minimum_groups_per_family for s in self.support)):
                raise ValueError("Protected split lacks declared class support")
        return self

    def assignment_for(self, instance_id: str) -> SplitAssignment:
        for assignment in self.assignments:
            if assignment.source.instance_id == instance_id:
                return assignment
        raise ValueError(f"Source instance is not assigned: {instance_id}")

    def partition_for(self, instance_id: str) -> Partition:
        return self.assignment_for(instance_id).partition


def dataframe_fingerprint(frame: pd.DataFrame) -> str:
    hasher = hashlib.sha256()
    hasher.update(json.dumps([(str(c), str(t)) for c, t in zip(frame.columns, frame.dtypes)]).encode())
    hasher.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    return hasher.hexdigest()


@dataclass(frozen=True)
class WindowBatch:
    """Features, labels and provenance are separate aligned tables.

    The digest detects accidental mutation/relabeling after construction. It is
    integrity checking, not an authorization boundary against malicious Python.
    """
    features: pd.DataFrame
    targets: pd.DataFrame
    metadata: pd.DataFrame
    quality: pd.DataFrame
    config_fingerprint: str
    split_fingerprint: str
    content_fingerprint: str

    def validate(self) -> None:
        tables = (self.features, self.targets, self.metadata, self.quality)
        if any(not table.index.equals(self.features.index) for table in tables):
            raise ValueError("Window tables are not aligned")
        if not self.features.index.is_unique:
            raise ValueError("Window IDs must be unique")
        actual = fingerprint({"config": self.config_fingerprint, "split": self.split_fingerprint,
                              "tables": [dataframe_fingerprint(table) for table in tables]})
        if actual != self.content_fingerprint:
            raise ValueError("Window batch content fingerprint mismatch; rebuild after mutation")

    def subset(self, partition: Literal["train", "validation", "test"]) -> WindowBatch:
        self.validate()
        if partition not in ("train", "validation", "test"):
            raise ValueError("Unknown partition")
        mask = self.metadata["partition"].eq(partition)
        return make_batch(*(table.loc[mask].copy() for table in
                            (self.features, self.targets, self.metadata, self.quality)),
                          self.config_fingerprint, self.split_fingerprint)


def make_batch(features: pd.DataFrame, targets: pd.DataFrame, metadata: pd.DataFrame,
               quality: pd.DataFrame, config_fingerprint: str,
               split_fingerprint: str) -> WindowBatch:
    content = fingerprint({"config": config_fingerprint, "split": split_fingerprint,
                           "tables": [dataframe_fingerprint(t) for t in
                                      (features, targets, metadata, quality)]})
    return WindowBatch(features, targets, metadata, quality, config_fingerprint,
                       split_fingerprint, content)
