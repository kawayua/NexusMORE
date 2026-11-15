/** NexusMORE business entry for host adapters. Authored for this project.
 * The Python Workflow owns state, permissions, reviews and idempotency.
 * This module does not load upstream plugins or create a parallel state file.
 * request({method, path, body}) must return the authoritative core response.
 */

export class WorkflowBridgeError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "WorkflowBridgeError";
    this.code = code;
  }
}

function identifier(value, field) {
  if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/.test(value)) {
    throw new WorkflowBridgeError("invalid_request", `Invalid ${field}`);
  }
  return value;
}

function payload(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new WorkflowBridgeError("invalid_request", "A request body is required");
  }
  // JSON data only: transport never receives functions or caller-owned objects.
  return JSON.parse(JSON.stringify(value));
}

function taskPath(args) {
  return `/tasks/${identifier(args.task_id, "task_id")}`;
}

function handPath(args) {
  return `${taskPath(args)}/hand-runs/${identifier(args.run_id, "run_id")}`;
}

const OPERATIONS = Object.freeze({
  project_create: (a) => ({ method: "POST", path: "/projects", body: payload(a.body) }),
  task_create: (a) => ({ method: "POST", path: `/projects/${identifier(a.project_id, "project_id")}/tasks`, body: payload(a.body) }),
  task_status: (a) => ({ method: "GET", path: taskPath(a) }),
  task_resume: (a) => ({ method: "POST", path: `${taskPath(a)}/resume` }),
  modeling_start: (a) => ({ method: "POST", path: `${taskPath(a)}/modeling/runs`, body: payload(a.body) }),
  modeling_status: (a) => ({ method: "GET", path: `${taskPath(a)}/modeling` }),
  hand_start: (a) => {
    if (!["coding", "writing"].includes(a.hand)) {
      throw new WorkflowBridgeError("invalid_request", "hand must be coding or writing");
    }
    return { method: "POST", path: `${taskPath(a)}/hands/${a.hand}/runs`, body: payload(a.body) };
  },
  hand_status: (a) => ({ method: "GET", path: handPath(a) }),
  hand_advance: (a) => ({ method: "POST", path: `${handPath(a)}/advance` }),
  artifacts_list: (a) => ({ method: "GET", path: `${taskPath(a)}/artifacts` }),
});

export const WORKFLOW_CAPABILITIES = Object.freeze({
  contract_version: "0.1.0",
  operations: Object.freeze(Object.keys(OPERATIONS)),
  authoritative_state: "modelcrew.Workflow",
  confirmation_submission: "not_exposed_requires_trusted_user_channel",
  knowledge_routing: "delegated_to_core_full_F6_pending",
  formal_export: "not_exposed_generic_export_integration_pending",
  host_adapters: "Codex_DSH_Claude_Code_planned_not_verified",
});

/** One explicit operation per call; no background progression or auto retry. */
export function createNexusmoreWorkflow({ request }) {
  if (typeof request !== "function") {
    throw new TypeError("A core request transport is required");
  }
  return Object.freeze({
    capabilities: WORKFLOW_CAPABILITIES,
    async invoke(operation, args = {}) {
      if (!Object.hasOwn(OPERATIONS, operation)) {
        throw new WorkflowBridgeError("unsupported_operation", "Operation is not registered");
      }
      if (!args || typeof args !== "object" || Array.isArray(args)) {
        throw new WorkflowBridgeError("invalid_request", "Arguments must be an object");
      }
      const call = OPERATIONS[operation](args);
      // Mutation identity and version are explicit caller input, never generated
      // afresh during recovery. The existing core validates the full schema.
      if (["modeling_start", "hand_start"].includes(operation)) {
        identifier(call.body.request_id, "request_id");
        if (!Number.isSafeInteger(call.body.version) || call.body.version < 1) {
          throw new WorkflowBridgeError("invalid_request", "A positive integer version is required");
        }
        if (typeof call.body.actor !== "string" || !call.body.actor.trim()) {
          throw new WorkflowBridgeError("invalid_request", "actor is required as an audit label");
        }
      }
      let response;
      try {
        response = await request(call);
      } catch {
        // An uncertain mutation may already have executed; never replay it here.
        throw new WorkflowBridgeError(call.method === "GET" ? "transport_unavailable" : "outcome_unknown",
          "Core response unavailable; inspect authoritative state before retrying");
      }
      if (response === undefined) {
        throw new WorkflowBridgeError(call.method === "GET" ? "invalid_response" : "outcome_unknown",
          "No authoritative core response received");
      }
      return response;
    },
  });
}
