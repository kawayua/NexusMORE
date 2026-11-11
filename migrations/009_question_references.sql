CREATE TABLE mc_question_intakes(
 id text NOT NULL, revision integer NOT NULL CHECK(revision>0),
 case_id text NOT NULL, question_id text NOT NULL,
 payload jsonb NOT NULL, sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(id,revision));
CREATE TABLE mc_question_references(
 id text PRIMARY KEY, target_id text NOT NULL, target_revision integer NOT NULL,
 source_task text NOT NULL REFERENCES mc_tasks(id), payload jsonb NOT NULL, sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(target_id,target_revision) REFERENCES mc_question_intakes(id,revision));
CREATE TRIGGER mc_question_intakes_immutable BEFORE UPDATE OR DELETE ON mc_question_intakes FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
CREATE TRIGGER mc_question_references_immutable BEFORE UPDATE OR DELETE ON mc_question_references FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(9);
