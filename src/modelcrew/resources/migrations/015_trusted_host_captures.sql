-- Additive native-host capture evidence. Existing events/revisions remain immutable.
ALTER TABLE mc_trusted_user_events DROP CONSTRAINT mc_trusted_user_events_channel_check;
ALTER TABLE mc_trusted_user_events ADD CONSTRAINT mc_trusted_user_events_channel_check
 CHECK(channel IN ('trusted_local_cli','trusted_host_ui'));
CREATE TABLE mc_trusted_host_captures (
 event_id text PRIMARY KEY REFERENCES mc_trusted_user_events(event_id),
 capture jsonb NOT NULL,
 capture_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER mc_trusted_host_captures_immutable BEFORE UPDATE OR DELETE ON mc_trusted_host_captures
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(15);
