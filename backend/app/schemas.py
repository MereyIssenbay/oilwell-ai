"""Diagnostic API 1.0.0 types, distinct from the planned event-family contract."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, StrictFloat, StrictInt,
                      StrictStr, field_validator, model_validator)

from ml.data_pipeline.models import SENSOR_COLUMNS

SOURCE_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$"


def _source_time(value: str) -> str:
    if not re.fullmatch(SOURCE_PATTERN, value):
        raise ValueError("Source timestamp must be a timezone-naive ISO datetime")
    datetime.fromisoformat(value)
    return value


def _utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("UTC transport datetime required")
    return value


SourceTime = Annotated[StrictStr, Field(pattern=SOURCE_PATTERN), AfterValidator(_source_time)]
UtcTime = Annotated[datetime, AfterValidator(_utc)]
Fraction = Annotated[StrictFloat, Field(ge=0, le=1, allow_inf_nan=False)]
Finite = Annotated[StrictFloat, Field(allow_inf_nan=False)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def literal_flags_are_booleans(cls, values: Any) -> Any:
        if isinstance(values, dict):
            for name in ("diagnostic_only", "accepted_for_monitoring"):
                if name in values and type(values[name]) is not bool:
                    raise ValueError("Diagnostic and acceptance flags must be Boolean")
        return values


class SensorSample(StrictModel):
    timestamp: SourceTime
    sensors: dict[str, Finite | None] = Field(
        min_length=27, max_length=27,
        json_schema_extra={"propertyNames": {"enum": list(SENSOR_COLUMNS)}})

    @field_validator("sensors", mode="before")
    @classmethod
    def exact_sensor_input(cls, value: Any) -> Any:
        if not isinstance(value, dict) or set(value) != set(SENSOR_COLUMNS):
            raise ValueError("Exactly the registered 27 sensor columns are required")
        if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in value.values()):
            raise ValueError("Sensor values must be finite numbers or null")
        return value


class PredictRequest(StrictModel):
    source_instance_id: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    endpoint_position: Annotated[StrictInt, Field(ge=0)]
    model_version: Annotated[StrictStr, Field(min_length=1, max_length=128)] | None = None
    samples: list[SensorSample] | None = Field(default=None, min_length=1, max_length=60)

    @model_validator(mode="after")
    def complete_window(self) -> PredictRequest:
        if self.endpoint_position >= 59 and (self.endpoint_position - 59) % 10:
            raise ValueError("Endpoint does not align with the frozen window stride")
        if self.samples is not None and len(self.samples) != min(60, self.endpoint_position + 1):
            raise ValueError("Submitted samples must cover the entire registered trailing window")
        return self


class Window(StrictModel):
    start: UtcTime
    end: UtcTime
    sample_count: Annotated[StrictInt, Field(ge=1, le=60)]
    expected_sample_count: Literal[60] = 60


class SensorEvidence(StrictModel):
    evidence_id: str
    sensor_name: str
    statistic: Literal["mean"] = "mean"
    value: Finite | None
    unit: str
    window_start: UtcTime
    window_end: UtcTime
    missing_fraction: Fraction
    method: Literal["observed_summary"] = "observed_summary"

    @field_validator("sensor_name")
    @classmethod
    def known_sensor(cls, value: str) -> str:
        if value not in SENSOR_COLUMNS:
            raise ValueError("Unregistered sensor evidence")
        return value


class Quality(StrictModel):
    status: Literal["valid", "degraded", "invalid"]
    missing_fraction: Fraction
    warnings: list[str] = Field(max_length=16)


class Provenance(StrictModel):
    dataset_name: Literal["3W"] = "3W"
    dataset_version: str
    dataset_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    source_instance_id: str
    source_sha256: Digest
    source_kind: Literal["real"] = "real"
    well_identity_kind: Literal["anonymized_well"] = "anonymized_well"
    source_timestamp: SourceTime
    time_basis: Literal["source_naive_assumed_utc"] = "source_naive_assumed_utc"
    preprocessor_fingerprint: Digest
    model_artifact_sha256: Digest
    request_window_sha256: Digest


class Execution(StrictModel):
    mode: Literal["historical_inference"] = "historical_inference"
    generated_at: UtcTime


class DiagnosticPrediction(StrictModel):
    schema_version: Literal["diagnostic-1.0.0"] = "diagnostic-1.0.0"
    prediction_id: UUID
    timestamp: UtcTime
    well_id: str
    event_type: Literal["normal", "undesirable_event", "unknown"]
    confidence: Fraction | None
    confidence_kind: Literal["raw_probability", "unavailable"]
    abnormal_score: Fraction | None
    threshold: Fraction
    model_version: str
    feature_spec_version: str
    policy_version: str
    diagnostic_only: Literal[True] = True
    accepted_for_monitoring: Literal[False] = False
    sensor_evidence: list[SensorEvidence] = Field(max_length=27)
    alert_status: Literal["normal", "alert", "insufficient_data"]
    abstention_reason: Literal["insufficient_history", "missing_required_sensors"] | None
    window: Window
    quality: Quality
    provenance: Provenance
    execution: Execution

    @model_validator(mode="after")
    def consistent_prediction(self) -> DiagnosticPrediction:
        if self.timestamp != self.window.end or self.window.start > self.window.end:
            raise ValueError("Prediction/window timestamp mismatch")
        source_coordinate = datetime.fromisoformat(self.provenance.source_timestamp).replace(tzinfo=timezone.utc)
        if source_coordinate != self.timestamp:
            raise ValueError("Provenance source coordinate differs from prediction timestamp")
        if any(e.window_start < self.window.start or e.window_end > self.window.end
               or e.window_start > e.window_end for e in self.sensor_evidence):
            raise ValueError("Evidence is outside the causal window")
        if len({e.evidence_id for e in self.sensor_evidence}) != len(self.sensor_evidence):
            raise ValueError("Evidence identifiers must be unique")
        if len({e.sensor_name for e in self.sensor_evidence}) != len(self.sensor_evidence):
            raise ValueError("Sensor summaries must be unique")
        if self.event_type == "unknown":
            if (self.confidence is not None or self.abnormal_score is not None
                    or self.confidence_kind != "unavailable" or self.abstention_reason is None
                    or self.alert_status != "insufficient_data"):
                raise ValueError("Inconsistent abstention")
            if ((self.abstention_reason == "insufficient_history") != (self.window.sample_count < 60)):
                raise ValueError("Abstention reason and history length disagree")
        else:
            if (self.confidence is None or self.abnormal_score is None
                    or self.confidence_kind != "raw_probability" or self.abstention_reason is not None
                    or self.quality.status == "invalid" or not any(e.value is not None for e in self.sensor_evidence)):
                raise ValueError("Usable predictions require finite evidence and explicit raw score")
            if self.window.sample_count != 60:
                raise ValueError("Usable prediction requires a full frozen window")
            positive = self.abnormal_score >= self.threshold
            if self.event_type != ("undesirable_event" if positive else "normal"):
                raise ValueError("Decision differs from frozen threshold")
            if self.alert_status != ("alert" if positive else "normal"):
                raise ValueError("Alert status differs from binary decision")
            expected = self.abnormal_score if positive else 1 - self.abnormal_score
            if not math.isclose(self.confidence, expected, rel_tol=0, abs_tol=1e-15):
                raise ValueError("Confidence must describe the selected binary class")
        return self


class ModelInfo(StrictModel):
    schema_version: Literal["diagnostic-1.0.0"] = "diagnostic-1.0.0"
    model_version: str
    task: Literal["binary_normal_vs_documented_undesirable"]
    supported_labels: list[Literal["normal", "undesirable_event"]]
    calibration: Literal["none"]
    status: Literal["diagnostic_only_rejected_for_monitoring"]
    diagnostic_only: Literal[True] = True
    accepted_for_monitoring: Literal[False] = False
    threshold: Fraction
    comparison: Literal["ge"]
    sensor_names: list[str]
    window_rows: Literal[60]
    stride_rows: Literal[10]
    preprocessor_fingerprint: Digest
    model_artifact_sha256: Digest
    limitations: list[str]


class SourceInfo(StrictModel):
    source_instance_id: str
    source_start: SourceTime
    source_end: SourceTime
    row_count: Annotated[StrictInt, Field(ge=1)]


class WellInfo(StrictModel):
    well_id: str
    well_identity_kind: Literal["anonymized_well"] = "anonymized_well"
    source_kind: Literal["real"] = "real"
    source_instances: list[SourceInfo]
    mode: Literal["historical_inference"] = "historical_inference"


class WellPage(StrictModel):
    items: list[WellInfo]
    next_cursor: str | None


class TelemetrySample(StrictModel):
    timestamp: SourceTime
    sensors: dict[str, Finite | None]


class TelemetryPage(StrictModel):
    well_id: str
    source_instance_id: str
    source_kind: Literal["real"] = "real"
    time_basis: Literal["source_naive_assumed_utc"] = "source_naive_assumed_utc"
    mode: Literal["historical_inference"] = "historical_inference"
    items: list[TelemetrySample]
    next_offset: Annotated[StrictInt, Field(ge=0)] | None


class Alert(StrictModel):
    alert_id: UUID
    prediction_id: UUID
    well_id: str
    source_instance_id: str
    timestamp: UtcTime
    generated_at: UtcTime
    model_version: str
    event_type: Literal["undesirable_event"] = "undesirable_event"
    status: Literal["diagnostic_detection"] = "diagnostic_detection"
    abnormal_score: Fraction
    threshold: Fraction
    diagnostic_only: Literal[True] = True
    accepted_for_monitoring: Literal[False] = False
    mode: Literal["historical_inference"] = "historical_inference"


class AlertPage(StrictModel):
    items: list[Alert]
    next_cursor: str | None


class Health(StrictModel):
    status: Literal["ok", "degraded"]
    model: Literal["ready", "unavailable"]
    registry: Literal["ready", "unavailable"]
    database: Literal["ready", "unavailable"]
    diagnostic_only: Literal[True] = True
    accepted_for_monitoring: Literal[False] = False


class ErrorDetail(StrictModel):
    code: str
    message: str
    details: dict[str, Any]
    request_id: UUID


class ErrorResponse(StrictModel):
    error: ErrorDetail
