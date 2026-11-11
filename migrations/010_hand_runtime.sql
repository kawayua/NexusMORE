CREATE TABLE mc_hand_runs(
 id uuid PRIMARY KEY, task_id text NOT NULL, version integer NOT NULL,
 hand text NOT NULL CHECK(hand IN ('coding','writing')),
 request_id text NOT NULL, request_sha256 text NOT NULL,
 phase text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(task_id,version) REFERENCES mc_contracts(task_id,version),
 UNIQUE(task_id,request_id));
CREATE TABLE mc_hand_events(
 id bigserial PRIMARY KEY, run_id uuid NOT NULL REFERENCES mc_hand_runs(id),
 phase text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TRIGGER mc_hand_events_immutable BEFORE UPDATE OR DELETE ON mc_hand_events
 FOR EACH ROW EXECUTE FUNCTION mc_immutable_record();
INSERT INTO mc_migrations(version) VALUES(10);
