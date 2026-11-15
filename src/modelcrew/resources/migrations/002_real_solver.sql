ALTER TABLE mc_executions DROP CONSTRAINT IF EXISTS mc_executions_mode_check;
ALTER TABLE mc_executions DROP CONSTRAINT IF EXISTS mc_executions_task_id_version_key;
ALTER TABLE mc_executions ADD COLUMN IF NOT EXISTS run_id text;
ALTER TABLE mc_executions ADD CONSTRAINT mc_executions_mode_check CHECK(mode IN ('fixture','solver'));
ALTER TABLE mc_executions ADD CONSTRAINT mc_executions_solver_run_check CHECK(mode <> 'solver' OR run_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS mc_one_fixture_per_contract ON mc_executions(task_id,version) WHERE mode='fixture';
CREATE UNIQUE INDEX IF NOT EXISTS mc_one_solver_run ON mc_executions(task_id,version,run_id) WHERE mode='solver';
INSERT INTO mc_migrations(version) VALUES(2) ON CONFLICT DO NOTHING;
