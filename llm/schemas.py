"""Allowlisted provider packet and versioned public explanation contract."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ml.data_pipeline.models import SENSOR_COLUMNS

Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Fraction = Annotated[Finite, Field(ge=0, le=1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SourceTime = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True,
                              revalidate_instances="always", allow_inf_nan=False)


class SensorEvidence(StrictModel):
    evidence_id: Annotated[str, Field(pattern=r"^e[0-9]{1,3}$")]
    sensor: Annotated[str, Field(max_length=30)]
    unit: Annotated[str, Field(max_length=80)] | None
    mean: Finite | None
    latest: Finite | None
    trend_per_second: Finite | None
    missing_fraction: Fraction
    observed_count: Annotated[int, Field(strict=True, ge=0, le=60)]

    @field_validator("sensor")
    @classmethod
    def known_sensor(cls, value: str) -> str:
        if value not in SENSOR_COLUMNS:
            raise ValueError("Unregistered sensor")
        return value


class EvidencePacket(StrictModel):
    packet_version: Literal["copilot-evidence-1.0.0"] = "copilot-evidence-1.0.0"
    model_version: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")]
    event_type: Literal["normal", "undesirable_event", "unknown"]
    confidence: Fraction | None
    abnormal_score: Fraction | None
    threshold: Fraction
    calibration: Literal["uncalibrated"] = "uncalibrated"
    alert_status: Literal["normal", "alert", "insufficient_data"]
    episode_state: Literal["none", "open", "resolved", "unknown"] = "none"
    source_origin: Literal["real", "simulated", "drawn"] = "real"
    source_time_basis: Literal["source_naive_assumed_utc"] = "source_naive_assumed_utc"
    window_start: SourceTime
    window_end: SourceTime
    sample_count: Annotated[int, Field(strict=True, ge=1, le=60)]
    expected_sample_count: Literal[60] = 60
    sensors: list[SensorEvidence] = Field(max_length=27)
    integrity: Literal["verified", "conflicting"] = "verified"
    abstention_reason: Literal["insufficient_history", "missing_required_sensors"] | None = None

    @model_validator(mode="after")
    def valid_bounds(self) -> EvidencePacket:
        start, end = datetime.fromisoformat(self.window_start), datetime.fromisoformat(self.window_end)
        if start > end:
            raise ValueError("Reversed source window")
        if len({x.evidence_id for x in self.sensors}) != len(self.sensors):
            raise ValueError("Duplicate evidence ID")
        if len({x.sensor for x in self.sensors}) != len(self.sensors):
            raise ValueError("Duplicate sensor")
        return self


class ExplanationRequest(StrictModel):
    question: Annotated[str, Field(strict=True, max_length=500)] = ""
    use_provider: Annotated[bool, Field(strict=True)] = False


class Source(StrictModel):
    source_id: str
    title: str
    url: str
    section: str
    attribution: str
    license: str
    license_url: str
    accessed_at: str
    content: str
    content_sha256: Digest
    content_kind: Literal["curated_paraphrase"] = "curated_paraphrase"

    @field_validator("url", "license_url")
    @classmethod
    def public_reference(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port is not None
                or parsed.hostname not in {"www.nature.com", "www.itl.nist.gov", "www.nist.gov", "creativecommons.org"}):
            raise ValueError("Unapproved source link")
        return value


class Claim(StrictModel):
    claim_id: str
    text: str
    evidence_ids: list[str]
    citation_ids: list[str] = Field(default_factory=list)


class TokenUsage(StrictModel):
    input_tokens: Annotated[int, Field(strict=True, ge=0)]
    output_tokens: Annotated[int, Field(strict=True, ge=0)]


class Explanation(StrictModel):
    schema_version: Literal["copilot-explanation-1.0.0"] = "copilot-explanation-1.0.0"
    status: Literal["fallback", "provider", "abstained"]
    reason: Literal["deterministic_requested", "provider_disabled", "provider_unavailable", "provider_invalid",
                    "budget_exhausted", "unsupported_question", "missing_evidence", "conflicting_evidence",
                    "provider_refusal", "provider_selected"]
    historical_replay: Literal[True] = True
    diagnostic_only: Literal[True] = True
    accepted_for_monitoring: Literal[False] = False
    observations: list[Claim]
    prediction: list[Claim]
    possible_interpretations: list[Claim]
    limitations: list[Claim]
    abstention: str | None
    citations: list[Source]
    evidence: EvidencePacket
    evidence_hash: Digest
    prompt_version: Literal["claim-selection-1.0.0"] = "claim-selection-1.0.0"
    kb_version: str
    provider: Literal["none", "openai"] = "none"
    provider_model: str | None = None
    created_at: datetime
    cached: bool = False
    usage: TokenUsage | None = None


class Selection(StrictModel):
    """The provider cannot produce sentences, numerical values, URLs, or actions."""
    observation_ids: list[str] = Field(max_length=6)
    interpretation_ids: list[str] = Field(max_length=3)
    citation_ids: list[str] = Field(max_length=3)
    abstain: Annotated[bool, Field(strict=True)]
