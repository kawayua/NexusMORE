CREATE TABLE mc_mcp_traces(
 id uuid PRIMARY KEY, task_id text NOT NULL, version integer NOT NULL,
 contract_sha256 text NOT NULL, operation_key text NOT NULL, service text NOT NULL,
 tool text NOT NULL, phase text NOT NULL CHECK(phase IN ('started','completed','transport_error')),
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version));
CREATE INDEX mc_mcp_trace_version ON mc_mcp_traces(task_id,version,created_at);
CREATE TABLE mc_references(
 task_id text NOT NULL, version integer NOT NULL, reference_id text NOT NULL,
 trace_id uuid NOT NULL REFERENCES mc_mcp_traces(id), payload jsonb NOT NULL,
 payload_sha256 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(task_id,version,reference_id),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version));
CREATE TABLE mc_reference_discussions(
 id uuid PRIMARY KEY, sequence bigserial UNIQUE, task_id text NOT NULL, version integer NOT NULL,
 entry_id uuid NOT NULL REFERENCES mc_version_entries(id), decisions jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version));
CREATE TRIGGER mc_mcp_traces_immutable BEFORE UPDATE OR DELETE ON mc_mcp_traces FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
CREATE TRIGGER mc_references_immutable BEFORE UPDATE OR DELETE ON mc_references FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
CREATE TRIGGER mc_reference_discussions_immutable BEFORE UPDATE OR DELETE ON mc_reference_discussions FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(6);
