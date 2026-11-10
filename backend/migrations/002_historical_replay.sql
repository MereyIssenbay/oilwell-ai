CREATE TABLE IF NOT EXISTS oilwell_replays (
    replay_id UUID PRIMARY KEY,
    state TEXT NOT NULL,
    payload JSONB NOT NULL,
    due_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS oilwell_one_active_replay ON oilwell_replays ((true))
    WHERE state IN ('created','running','paused');
CREATE TABLE IF NOT EXISTS oilwell_replay_events (
    replay_id UUID NOT NULL REFERENCES oilwell_replays(replay_id),
    sequence BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY(replay_id, sequence)
);
CREATE INDEX IF NOT EXISTS oilwell_replay_events_kind ON oilwell_replay_events(replay_id,event_type,sequence);
CREATE TABLE IF NOT EXISTS oilwell_replay_requests (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    response JSONB NOT NULL,
    PRIMARY KEY(scope,key)
);
INSERT INTO oilwell_schema_migrations(version) VALUES(2) ON CONFLICT DO NOTHING;
