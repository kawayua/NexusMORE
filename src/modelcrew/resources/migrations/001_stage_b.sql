CREATE TABLE IF NOT EXISTS mc_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS mc_projects(id text PRIMARY KEY, title text NOT NULL);
CREATE TABLE IF NOT EXISTS mc_tasks(
 id text PRIMARY KEY, project_id text NOT NULL REFERENCES mc_projects(id),
 current_version integer NOT NULL, thread_id text NOT NULL UNIQUE,
 phase text NOT NULL CHECK(phase IN ('WAITING_MODEL_APPROVAL','SOLVING','WAITING_RESULT_APPROVAL','COMPLETED')),
 model_approved boolean NOT NULL DEFAULT false, result_revision integer NOT NULL DEFAULT 0,
 result_approved boolean NOT NULL DEFAULT false, execution_id uuid,
 interpretation text NOT NULL DEFAULT '', updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS mc_contracts(
 task_id text NOT NULL REFERENCES mc_tasks(id), version integer NOT NULL,
 content jsonb NOT NULL, sha256 text NOT NULL, parent_version integer,
 guidance text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(task_id,version));
CREATE TABLE IF NOT EXISTS mc_executions(
 id uuid PRIMARY KEY, task_id text NOT NULL, version integer NOT NULL,
 contract_sha256 text NOT NULL, mode text NOT NULL CHECK(mode='fixture'),
 artifacts jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version), UNIQUE(task_id,version));
CREATE TABLE IF NOT EXISTS mc_results(
 task_id text NOT NULL, version integer NOT NULL, revision integer NOT NULL,
 execution_id uuid NOT NULL REFERENCES mc_executions(id), interpretation text NOT NULL,
 review jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(task_id,version,revision), FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version));
CREATE TABLE IF NOT EXISTS mc_events(
 id bigserial PRIMARY KEY, task_id text NOT NULL REFERENCES mc_tasks(id),
 kind text NOT NULL, actor text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS mc_requests(
 task_id text NOT NULL REFERENCES mc_tasks(id), request_id text NOT NULL,
 payload_sha256 text NOT NULL, response jsonb NOT NULL,
 PRIMARY KEY(task_id,request_id));
CREATE TABLE IF NOT EXISTS mc_summaries(
 task_id text NOT NULL, version integer NOT NULL, revision integer NOT NULL,
 content jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(task_id,version,revision),
 FOREIGN KEY(task_id,version,revision) REFERENCES mc_results(task_id,version,revision));
CREATE OR REPLACE FUNCTION mc_immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable audit record: %', TG_TABLE_NAME; END $$;
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['mc_contracts','mc_executions','mc_results','mc_events','mc_summaries','mc_requests'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname=tab||'_immutable') THEN
   EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION mc_immutable_record()',tab||'_immutable',tab);
  END IF;
 END LOOP;
END $$;
INSERT INTO mc_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
