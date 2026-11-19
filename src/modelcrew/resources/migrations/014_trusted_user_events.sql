-- Trusted local capture evidence, separate from model-supplied event references.
CREATE TABLE mc_trusted_user_events (
 event_id text PRIMARY KEY,
 channel text NOT NULL CHECK(channel = 'trusted_local_cli'),
 principal jsonb NOT NULL,
 pending_id text NOT NULL,
 review_sha256 text NOT NULL,
 review jsonb NOT NULL,
 statement text NOT NULL,
 statement_sha256 text NOT NULL,
 request_sha256 text NOT NULL,
 request jsonb NOT NULL,
 captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL DEFAULT (clock_timestamp() + interval '10 minutes'),
 CHECK(expires_at > captured_at)
);
CREATE TRIGGER mc_trusted_user_events_immutable BEFORE UPDATE OR DELETE ON mc_trusted_user_events
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
CREATE TABLE mc_trusted_user_event_claims (
 event_id text PRIMARY KEY REFERENCES mc_trusted_user_events(event_id),
 scope_sha256 text NOT NULL,
 operation text NOT NULL,
 request_id text NOT NULL,
 request_sha256 text NOT NULL,
 claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(scope_sha256,operation,request_id)
 REFERENCES mc_business_operations(scope_sha256,operation,request_id),
 UNIQUE(scope_sha256,operation,request_id)
);
CREATE TRIGGER mc_trusted_user_event_claims_immutable BEFORE UPDATE OR DELETE ON mc_trusted_user_event_claims
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(14);
