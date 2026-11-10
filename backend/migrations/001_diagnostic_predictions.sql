CREATE TABLE IF NOT EXISTS oilwell_schema_migrations (
    version integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oilwell_predictions (
    prediction_id uuid PRIMARY KEY,
    idempotency_key varchar(128) NOT NULL UNIQUE,
    request_sha256 char(64) NOT NULL,
    well_id text NOT NULL,
    source_instance_id text NOT NULL,
    model_version text NOT NULL,
    source_timestamp timestamptz NOT NULL,
    generated_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    CHECK (payload->>'schema_version' = 'diagnostic-1.0.0'),
    CHECK (payload->>'diagnostic_only' = 'true'),
    CHECK (payload->>'accepted_for_monitoring' = 'false')
);

CREATE TABLE IF NOT EXISTS oilwell_alerts (
    sequence bigserial PRIMARY KEY,
    alert_id uuid NOT NULL UNIQUE,
    prediction_id uuid NOT NULL UNIQUE REFERENCES oilwell_predictions(prediction_id),
    well_id text NOT NULL,
    source_instance_id text NOT NULL,
    model_version text NOT NULL,
    source_timestamp timestamptz NOT NULL,
    generated_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    CHECK (payload->>'status' = 'diagnostic_detection'),
    CHECK (payload->>'diagnostic_only' = 'true')
);

CREATE INDEX IF NOT EXISTS oilwell_alerts_well_sequence ON oilwell_alerts(well_id, sequence);
CREATE INDEX IF NOT EXISTS oilwell_predictions_well_time ON oilwell_predictions(well_id, source_timestamp);
INSERT INTO oilwell_schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;
