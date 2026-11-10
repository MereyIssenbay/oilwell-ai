"""Additive dashboard browsing and strictly retrospective label contracts."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, model_validator

from backend.app.replay_schemas import Playback, Position, ReplaySnapshot
from backend.app.schemas import Digest, Fraction, SourceTime, StrictModel


class ReplayList(Playback):
    items: list[ReplaySnapshot]
    next_cursor: str | None


class SensorDescription(StrictModel):
    name: str
    unit_or_domain: str


class SensorCatalog(StrictModel):
    items: list[SensorDescription]
    time_basis: Literal["source_naive_assumed_utc"] = "source_naive_assumed_utc"


class RetrospectivePrediction(StrictModel):
    sequence: Annotated[StrictInt, Field(ge=1)]
    source_position: Position
    prediction_id: UUID
    timestamp: SourceTime
    abnormal_score: Fraction | None
    predicted_event_type: Literal["normal", "undesirable_event", "unknown"]
    raw_class: StrictInt | None
    raw_state: StrictInt | None
    actual_event_family: Annotated[StrictInt, Field(ge=0, le=9)] | None
    actual_event_name: str | None
    actual_phase: Literal["normal", "event", "transient", "unknown"]
    actual_binary: Literal[0, 1] | None
    decision_matches: StrictBool | None

    @model_validator(mode="before")
    @classmethod
    def strict_binary(cls, value: object) -> object:
        if isinstance(value, dict) and value.get("actual_binary") is not None and type(value["actual_binary"]) is not int:
            raise ValueError("Actual binary target must be an integer or null")
        return value


class RetrospectivePage(Playback):
    schema_version: Literal["retrospective-1.0.0"] = "retrospective-1.0.0"
    retrospective_only: Literal[True] = True
    replay_id: UUID
    source_instance_id: str
    source_sha256: Digest
    label_policy_version: Literal["3w-v2-family-including-transients-v1"] = "3w-v2-family-including-transients-v1"
    time_basis: Literal["source_naive_assumed_utc"] = "source_naive_assumed_utc"
    items: list[RetrospectivePrediction]
    next_after_sequence: Position | None

    @model_validator(mode="before")
    @classmethod
    def strict_retrospective_marker(cls, value: object) -> object:
        if isinstance(value, dict) and "retrospective_only" in value and type(value["retrospective_only"]) is not bool:
            raise ValueError("Retrospective marker must be Boolean")
        return value
