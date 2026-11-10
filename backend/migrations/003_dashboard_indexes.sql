CREATE INDEX IF NOT EXISTS oilwell_replays_created_page
    ON oilwell_replays(created_at DESC, replay_id DESC);
INSERT INTO oilwell_schema_migrations(version) VALUES(3) ON CONFLICT DO NOTHING;
