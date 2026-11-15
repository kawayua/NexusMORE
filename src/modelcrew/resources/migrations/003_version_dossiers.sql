ALTER TABLE mc_contracts ADD COLUMN IF NOT EXISTS restored_from_version integer;
ALTER TABLE mc_contracts ADD CONSTRAINT mc_restored_source_fk FOREIGN KEY(task_id,restored_from_version) REFERENCES mc_contracts(task_id,version);
ALTER TABLE mc_tasks ADD COLUMN IF NOT EXISTS executor_key text NOT NULL DEFAULT 'historical-fixture';
CREATE TABLE mc_version_entries(
 id uuid PRIMARY KEY, task_id text NOT NULL, version integer NOT NULL,
 kind text NOT NULL CHECK(kind IN ('proposal','feedback','next_step','change_note','code','experiment')),
 body jsonb NOT NULL, actor text NOT NULL, request_id text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version),
 UNIQUE(task_id,request_id));
CREATE TRIGGER mc_version_entries_immutable BEFORE UPDATE OR DELETE ON mc_version_entries FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(3);
