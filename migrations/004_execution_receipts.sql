ALTER TABLE mc_tasks ADD COLUMN executor_config jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE mc_executions ADD COLUMN backend_key text;
ALTER TABLE mc_executions ADD COLUMN operation_key text;
CREATE UNIQUE INDEX mc_execution_operation ON mc_executions(operation_key) WHERE operation_key IS NOT NULL;
CREATE TABLE mc_backend_receipts(
 operation_key text PRIMARY KEY, task_id text NOT NULL, version integer NOT NULL,
 backend_key text NOT NULL, contract_sha256 text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version));
CREATE TABLE mc_backend_attempts(
 id bigserial PRIMARY KEY, operation_key text NOT NULL, task_id text NOT NULL,
 version integer NOT NULL, phase text NOT NULL CHECK(phase IN ('started','succeeded','failed','unknown')),
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version));
CREATE TRIGGER mc_backend_receipts_immutable BEFORE UPDATE OR DELETE ON mc_backend_receipts FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
CREATE TRIGGER mc_backend_attempts_immutable BEFORE UPDATE OR DELETE ON mc_backend_attempts FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(4);
