ALTER TABLE mc_contracts ADD COLUMN executor_key text;
ALTER TABLE mc_contracts ADD COLUMN executor_config jsonb;
INSERT INTO mc_migrations(version) VALUES(5);
