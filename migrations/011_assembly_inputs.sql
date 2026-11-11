CREATE TABLE mc_assembly_runs (
 id uuid PRIMARY KEY,
 project_id text NOT NULL REFERENCES mc_projects(id),
 request_id text NOT NULL,
 request_sha256 text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id, request_id)
);
CREATE TRIGGER mc_assembly_runs_immutable BEFORE UPDATE OR DELETE ON mc_assembly_runs
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(11);
