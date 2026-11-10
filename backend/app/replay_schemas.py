"""Additive historical replay contracts; synchronous predictions remain unchanged."""
from __future__ import annotations
from typing import Annotated, Literal, Any
from uuid import UUID
from pydantic import Field, StrictInt, StrictFloat, StrictStr, model_validator
from backend.app.schemas import StrictModel, UtcTime, SourceTime, DiagnosticPrediction, Fraction, SensorSample

Position = Annotated[StrictInt, Field(ge=0)]
Speed = Annotated[StrictFloat, Field(ge=.1, le=20, allow_inf_nan=False)]
State = Literal['created','running','paused','stopped','completed','failed']

class Playback(StrictModel):
    schema_version: Literal['diagnostic-replay-1.0.0'] = 'diagnostic-replay-1.0.0'
    mode: Literal['historical_replay'] = 'historical_replay'
    simulated_playback: Literal[True] = True
    diagnostic_only: Literal[True] = True
    accepted_for_monitoring: Literal[False] = False

    @model_validator(mode='before')
    @classmethod
    def strict_playback(cls, value):
        if isinstance(value, dict) and 'simulated_playback' in value and type(value['simulated_playback']) is not bool:
            raise ValueError('Playback marker must be Boolean')
        return value

class CreateReplay(StrictModel):
    source_instance_id: Annotated[StrictStr, Field(min_length=1,max_length=128)]
    start_position: Position = 0
    end_position: Position | None = None
    speed_multiplier: Speed = 1.0
    model_version: Annotated[StrictStr, Field(min_length=1,max_length=128)] | None = None

class ReplayCommand(StrictModel):
    command: Literal['start','pause','resume','stop','set_speed']
    expected_version: Annotated[StrictInt, Field(ge=1)]
    speed_multiplier: Speed | None = None

    @model_validator(mode='after')
    def speed_required(self):
        if (self.command == 'set_speed') != (self.speed_multiplier is not None):
            raise ValueError('Speed is required only for set_speed')
        return self

class ReplayEpisode(Playback):
    episode_id: UUID
    replay_id: UUID
    opened_by_prediction_id: UUID
    opened_at: UtcTime
    last_prediction_id: UUID
    last_prediction_at: UtcTime
    last_data_status: Literal['alert','insufficient_data']
    threshold: Fraction
    model_version: str

class ReplaySnapshot(Playback):
    replay_id: UUID
    state: State
    version: Annotated[StrictInt, Field(ge=1)]
    source_instance_id: str
    source_kind: Literal['real'] = 'real'
    well_id: str
    model_version: str
    policy_version: Literal['replay-episode-ge-no-dwell-v1'] = 'replay-episode-ge-no-dwell-v1'
    source_sha256: str
    model_artifact_sha256: str
    preprocessor_fingerprint: str
    threshold: Fraction
    speed_multiplier: Speed
    start_position: Position
    end_position: Position
    cursor_position: Position | None
    source_start: SourceTime
    source_end: SourceTime
    cursor_timestamp: SourceTime | None
    time_basis: Literal['source_naive_assumed_utc'] = 'source_naive_assumed_utc'
    last_sequence: Position
    alert_episode: ReplayEpisode | None
    created_at: UtcTime
    updated_at: UtcTime
    failure: dict[str,str] | None

class ReplayPrediction(Playback):
    replay_id: UUID
    sequence: Annotated[StrictInt, Field(ge=1)]
    source_position: Position
    speed_multiplier: Speed
    alert_episode: ReplayEpisode | None
    prediction: DiagnosticPrediction

    @model_validator(mode='after')
    def causal_episode(self):
        if self.source_position < 59 or (self.source_position - 59) % 10:
            raise ValueError('Prediction position does not align with frozen windows')
        if self.prediction.window.sample_count != 60:
            raise ValueError('Replay prediction requires sixty observed rows')
        if self.prediction.alert_status == 'alert' and self.alert_episode is None:
            raise ValueError('Positive replay prediction must have an ongoing episode')
        if self.prediction.alert_status == 'normal' and self.alert_episode is not None:
            raise ValueError('Normal replay prediction resolves its episode')
        if self.alert_episode is not None:
            episode = self.alert_episode
            if episode.last_data_status != self.prediction.alert_status:
                raise ValueError('Episode data status differs from current prediction')
            if (episode.replay_id != self.replay_id or episode.model_version != self.prediction.model_version
                    or episode.threshold != self.prediction.threshold
                    or episode.last_prediction_id != self.prediction.prediction_id
                    or episode.last_prediction_at != self.prediction.timestamp
                    or episode.opened_at > episode.last_prediction_at):
                raise ValueError('Episode snapshot does not belong to current prediction')
        return self

class ReplayTelemetry(Playback, SensorSample):
    source_kind: Literal['real'] = 'real'
    source_instance_id: str
    well_id: str
    source_position: Position
    time_basis: Literal['source_naive_assumed_utc'] = 'source_naive_assumed_utc'

class EpisodeTransition(Playback):
    transition: Literal['opened','updated','resolved']
    episode_id: UUID
    alert_episode: ReplayEpisode | None
    caused_by_prediction_id: UUID
    source_position: Position
    timestamp: UtcTime

    @model_validator(mode='after')
    def episode_consistent(self):
        if (self.transition == 'resolved') != (self.alert_episode is None):
            raise ValueError('Episode resolution and snapshot disagree')
        if self.alert_episode is not None and self.episode_id != self.alert_episode.episode_id:
            raise ValueError('Episode identifiers disagree')
        return self

class ReplayFailure(Playback):
    code: str
    message: str

class ReplayEvent(Playback):
    replay_id: UUID
    sequence: Annotated[StrictInt, Field(ge=1)]
    event_type: Literal['replay_state','telemetry','prediction','alert_episode','replay_error']
    emitted_at: UtcTime
    payload: ReplaySnapshot | ReplayPrediction | ReplayTelemetry | EpisodeTransition | ReplayFailure

    @model_validator(mode='before')
    @classmethod
    def typed_payload(cls, data):
        if isinstance(data, dict):
            mapping = {'replay_state':ReplaySnapshot, 'prediction':ReplayPrediction,
                       'telemetry':ReplayTelemetry, 'alert_episode':EpisodeTransition, 'replay_error':ReplayFailure}
            if data.get('event_type') in mapping:
                data = dict(data)
                data['payload'] = mapping[data['event_type']].model_validate(data.get('payload'))
        return data

    @model_validator(mode='after')
    def envelope_consistent(self):
        if isinstance(self.payload, (ReplaySnapshot, ReplayPrediction)):
            if self.payload.replay_id != self.replay_id:
                raise ValueError('Event replay identity differs from payload')
            seq = self.payload.sequence if isinstance(self.payload, ReplayPrediction) else self.payload.last_sequence
            if seq != self.sequence:
                raise ValueError('Event watermark differs from payload')
        if isinstance(self.payload, EpisodeTransition) and self.payload.alert_episode is not None:
            if self.payload.alert_episode.replay_id != self.replay_id:
                raise ValueError('Episode belongs to another replay')
        return self

class ReplayEventPage(Playback):
    items: list[ReplayEvent]
    next_after_sequence: Position | None
