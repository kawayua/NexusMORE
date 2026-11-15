CREATE TABLE mc_math_packages(
 task_id text NOT NULL, version integer NOT NULL, revision integer NOT NULL CHECK(revision>0),
 content jsonb NOT NULL, sha256 text NOT NULL, semantic_sha256 text NOT NULL,
 proposal_markdown text NOT NULL, proposal_sha256 text NOT NULL, latex_source text NOT NULL,
 actor text NOT NULL, reason text NOT NULL, change_kind text NOT NULL CHECK(change_kind IN ('initial','mathematical','presentation','restoration')),
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(task_id,version,revision),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version));
CREATE TRIGGER mc_math_packages_immutable BEFORE UPDATE OR DELETE ON mc_math_packages FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(7);
