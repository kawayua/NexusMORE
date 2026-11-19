CREATE TABLE mc_business_operations (
 scope_sha256 text NOT NULL,
 operation text NOT NULL,
 request_id text NOT NULL,
 request_sha256 text NOT NULL,
 resource_key text NOT NULL,
 scope jsonb NOT NULL,
 request jsonb NOT NULL,
 state text NOT NULL CHECK(state IN ('claimed','dispatched','succeeded','failed','outcome_unknown')),
 response jsonb,
 legacy_domain text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(scope_sha256,operation,request_id)
);
CREATE UNIQUE INDEX mc_business_legacy_keys ON mc_business_operations(legacy_domain,request_id) WHERE legacy_domain IS NOT NULL;
CREATE INDEX mc_business_unresolved ON mc_business_operations(resource_key,state);
CREATE TABLE mc_business_operation_events (
 sequence bigserial PRIMARY KEY,
 scope_sha256 text NOT NULL,
 operation text NOT NULL,
 request_id text NOT NULL,
 state text NOT NULL,
 response_sha256 text,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(scope_sha256,operation,request_id) REFERENCES mc_business_operations(scope_sha256,operation,request_id)
);
CREATE TRIGGER mc_business_operation_events_immutable BEFORE UPDATE OR DELETE ON mc_business_operation_events
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
CREATE TABLE mc_business_artifacts (
 artifact_id text PRIMARY KEY,
 owner_sha256 text NOT NULL,
 owner jsonb NOT NULL,
 path text NOT NULL,
 sha256 text NOT NULL,
 media_type text NOT NULL,
 bytes bigint NOT NULL CHECK(bytes>=0),
 role text NOT NULL,
 is_input boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(owner_sha256,path,sha256)
);
CREATE TRIGGER mc_business_artifacts_immutable BEFORE UPDATE OR DELETE ON mc_business_artifacts
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(13);
