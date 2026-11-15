CREATE TABLE mc_modeling_runs(
 sequence bigserial UNIQUE NOT NULL,
 id uuid PRIMARY KEY,
 task_id text NOT NULL REFERENCES mc_tasks(id),
 base_version integer NOT NULL,
 version integer,
 request_id text NOT NULL,
 request_sha256 text NOT NULL,
 actor text NOT NULL,
 guidance text NOT NULL,
 status text NOT NULL CHECK(status IN ('started','planning','modeling','reviewing','ready','needs_human','blocked','failed','unknown')),
 payload jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(task_id,request_id),
 FOREIGN KEY(task_id,base_version) REFERENCES mc_contracts(task_id,version),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version)
);
CREATE TABLE mc_modeling_events(
 sequence bigserial PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES mc_modeling_runs(id),
 status text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER mc_modeling_events_immutable BEFORE UPDATE OR DELETE ON mc_modeling_events FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(8);
