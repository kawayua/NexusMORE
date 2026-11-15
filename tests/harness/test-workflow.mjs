import test from "node:test";
import assert from "node:assert/strict";
import { createNexusmoreWorkflow } from "../../src/harness/nexusmore-workflow.js";

test("host presentation returns exact authoritative state without completing or approving", async () => {
  const state = { status: "needs_user_input", pending: ["manuscript", "figures"] };
  let observed;
  const workflow = createNexusmoreWorkflow({ request: async (call) => { observed = call; return state; } });
  assert.strictEqual(await workflow.invoke("hand_status", { task_id: "q1", run_id: "run-1" }), state);
  assert.deepEqual(observed, { method: "GET", path: "/tasks/q1/hand-runs/run-1" });
});

test("uncertain mutation is never retried and preserves caller identity/version", async () => {
  let count = 0;
  const workflow = createNexusmoreWorkflow({ request: async (call) => {
    count++;
    assert.equal(call.body.request_id, "request-1");
    assert.equal(call.body.version, 3);
    throw new Error("connection lost after commit");
  }});
  await assert.rejects(workflow.invoke("hand_start", { task_id: "q1", hand: "coding",
    body: { actor: "host", request_id: "request-1", version: 3, guidance: "compute" } }),
    (err) => err.code === "outcome_unknown");
  assert.equal(count, 1);
});

test("unregistered approval/export calls and path traversal do not reach transport", async () => {
  let count = 0;
  const workflow = createNexusmoreWorkflow({ request: async () => { count++; return {}; } });
  for (const operation of ["approve", "hand_decision", "export", "constructor", "__proto__"]) {
    await assert.rejects(workflow.invoke(operation), (err) => err.code === "unsupported_operation");
  }
  for (const task_id of ["../other", "a/b", "a?version=1", "a#x"]) {
    await assert.rejects(workflow.invoke("task_status", { task_id }), (err) => err.code === "invalid_request");
  }
  assert.equal(count, 0);
});

test("invalid mutation binding fails before transport and valid payload is isolated", async () => {
  let count = 0;
  const workflow = createNexusmoreWorkflow({ request: async (call) => { count++; call.body.guidance = "changed"; return { run: "new" }; } });
  const body = { actor: "host", request_id: "request-1", version: 1, guidance: "original" };
  for (const version of [0, 1.5, "1"]) {
    await assert.rejects(workflow.invoke("modeling_start", { task_id: "q1", body: { ...body, version } }),
      (err) => err.code === "invalid_request");
  }
  assert.deepEqual(await workflow.invoke("modeling_start", { task_id: "q1", body }), { run: "new" });
  assert.equal(body.guidance, "original");
  assert.equal(count, 1);
});

test("single advance and resume are distinct core calls, without implicit loops", async () => {
  const calls = [];
  const workflow = createNexusmoreWorkflow({ request: async (call) => { calls.push(call); return { status: "pending" }; } });
  await workflow.invoke("hand_advance", { task_id: "q1", run_id: "run-1" });
  await workflow.invoke("task_resume", { task_id: "q1" });
  assert.deepEqual(calls.map((c) => c.path), ["/tasks/q1/hand-runs/run-1/advance", "/tasks/q1/resume"]);
});
