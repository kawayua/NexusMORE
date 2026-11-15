CREATE TABLE mc_assembly_builds (
 id uuid PRIMARY KEY,
 assembly_run_id uuid NOT NULL REFERENCES mc_assembly_runs(id),
 project_id text NOT NULL REFERENCES mc_projects(id),
 request_id text NOT NULL,
 request_sha256 text NOT NULL,
 phase text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id, request_id)
);
CREATE TABLE mc_assembly_build_events (
 id bigserial PRIMARY KEY,
 build_id uuid NOT NULL REFERENCES mc_assembly_builds(id),
 phase text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER mc_assembly_build_events_immutable BEFORE UPDATE OR DELETE ON mc_assembly_build_events
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(12);
