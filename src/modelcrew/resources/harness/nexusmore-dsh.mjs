/** Project-authored native human commands and read-only connection panel.
 * Uses the Host ToolRuntime pipeline, not Python or raw MCP direct invocation.
 * Exact Fetch routes inherit DSH owner admission. Only two fixed reads run.
 */
import { randomUUID, createHash } from 'node:crypto';
import { registerConversation } from './nexusmore-dsh-conversation.mjs';
import { registerDecisions } from './nexusmore-dsh-decisions.mjs';

export const name = 'nexusmore-connection-panel';
export const inject = ['connection', 'tools', 'commands', 'userQuestions', 'configEditor', 'agents', 'systemPrompt', 'sessionController', 'workspaceRegistry'];
const PREFIX = 'mcp__nexusmore__';
const HEADERS = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
const READS = ['capabilities_read', 'projects_list'];
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

export function registered(tools, agent) {
  return tools.schemas(agent).map(x => x.name).filter(x => x.startsWith(PREFIX)).sort();
}

export function decodeResult(batch, expectedOperation) {
  const result = batch?.results?.[0]?.result;
  if (!result || result.isError) return { status: 'error', code: result?.error?.info?.code ?? 'host_tool_failed' };
  for (const part of result.content ?? []) {
    if (part.type !== 'text') continue;
    try {
      const body = JSON.parse(part.text);
      if (body.contract_version === '1.0.0' && READS.includes(body.operation) && (!expectedOperation || body.operation === expectedOperation)) return { body };
    } catch { /* Content may include a non-JSON presentation before data. */ }
  }
  return { status: 'error', code: 'invalid_business_envelope' };
}

export async function diagnose(tools, signal, agent) {
  const names = registered(tools, agent);
  const calls = [];
  for (const operation of READS) {
    signal.throwIfAborted();
    const toolName = PREFIX + operation;
    if (!names.includes(toolName)) { calls.push({ operation, status: 'error', code: 'tool_not_registered' }); continue; }
    const started = Date.now();
    const batch = await tools.execute({
      calls: [{ id: 'nexusmore-diagnose-' + randomUUID(), name: toolName,
        arguments: JSON.stringify({ contract_version: '1.0.0', operation, arguments: {} }) }], signal,
      ...(agent ? { agent } : {}),
    });
    const decoded = decodeResult(batch, operation);
    if (!decoded.body) { calls.push({ operation, ...decoded }); continue; }
    const body = decoded.body;
    const item = { operation, status: body.status, elapsed_ms: Date.now() - started,
      response_sha256: digest(body), error_code: body.error?.code ?? null };
    if (operation === 'capabilities_read') {
      item.model_tool_count = body.data?.operations?.length ?? 0;
      const expected = body.data?.operations;
      item.expected_tools_registered = Array.isArray(expected) && expected.length === 40
        && new Set(expected).size === 40 && expected.every(x => names.includes(PREFIX + x));
      item.trusted_capture_channels = body.data?.trusted_capture_channels ?? [];
    } else {
      // Do not expose project names, identifiers, paths, or task contents here.
      const projects = Array.isArray(body.data) ? body.data : body.data?.projects;
      item.returned_project_count = Array.isArray(projects) ? projects.length : null;
      item.project_page_limit = 50;
    }
    calls.push(item);
  }
  return { scope: 'actual DSH ToolRuntime -> MCP -> Python Workflow; read-only engineering diagnosis',
    status: names.length === 40 && calls.length === 2 && calls.every(x => x.status === 'ok')
      && calls[0].expected_tools_registered === true && calls[1].returned_project_count !== null ? 'passed' : 'failed',
    registered_tool_count: names.length, registered_tools: names, calls,
    model_request_sent: false, user_decision_created: false, checked_at: new Date().toISOString() };
}

export function panelHtml() {
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>枢模 · NexusMORE 连接检查</title>
<style>body{font:16px/1.65 system-ui,sans-serif;max-width:960px;margin:48px auto;padding:0 24px;color:#182b37;background:#f7f9fb}h1{font-size:28px}button,a{font:inherit}button{background:#145e73;color:white;border:0;border-radius:6px;padding:10px 18px;cursor:pointer}button:disabled{opacity:.5}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;border:1px solid #d6dfe5;border-radius:8px}a{color:#145e73}</style>
<h1>枢模 · NexusMORE</h1><p>本地 DSH 连接检查 · 业务状态由 Python Workflow 与 PostgreSQL 提供。</p>
<p>运行检查只调用 capabilities_read 与 projects_list，不发送模型请求，不创建业务任务或用户批准。</p>
<button id="check">运行只读连接检查</button> <a href="/">返回 DSH</a><pre id="result" aria-live="polite">点击按钮，检查宿主实际注册与 MCP 调用。</pre><details><summary>查看检查原始回执与工具名</summary><pre id="detail">尚未检查</pre></details>
<p>用户决定可用 /nexusmore-review 原生问答或 G3 本地终端；正文与配图分别确认。此工程页没有批准按钮。</p>
<script>document.getElementById('check').addEventListener('click',async()=>{const b=document.getElementById('check');const p=document.getElementById('result');b.disabled=true;p.textContent='正在检查…';try{const r=await fetch('/api/nexusmore/diagnose',{method:'POST'});const v=await r.json();document.getElementById('detail').textContent=JSON.stringify(v,null,2);p.textContent=['连接检查：'+(v.status==='passed'?'通过':'未通过'),'宿主注册工具：'+v.registered_tool_count+' 项',...(v.calls??[]).map(x=>x.operation+'：'+x.status+'（'+(x.elapsed_ms??0)+' ms）'),'模型请求：未发送','用户批准：未创建','用户决定入口：DSH /nexusmore-review 或 G3 本地交互式终端','检查时间：'+v.checked_at].join('\\n')}catch(e){p.textContent='连接检查失败，请检查 DSH 插件与 Python 进程。'}finally{b.disabled=false}});</script></html>`;
}

export function formatDiagnosis(value) {
  return [
    '枢模 · NexusMORE：' + (value.status === 'passed' ? '本地连接检查通过' : '本地连接检查未通过'),
    'DSH 已注册业务 MCP 工具：' + value.registered_tool_count + ' 项',
    ...(value.calls ?? []).map(x => x.operation + '：' + x.status + '（' + (x.elapsed_ms ?? 0) + ' ms）'),
    '此命令只读，不调用模型，不创建业务任务或用户批准。',
    'DSH 原生确认：/nexusmore-review --project PROJECT_ID --task TASK_ID',
    '只读回执恢复：/nexusmore-review-status 加相同对象参数；本地终端回退：',
    'python -m modelcrew.trusted_decisions pending --project PROJECT_ID --task TASK_ID',
    'python -m modelcrew.trusted_decisions review --project PROJECT_ID --task TASK_ID',
    '正文和选图分别确认；聊天文字和宿主权限提示不等于业务批准。',
  ].join('\n');
}


/** Engineering-only native UI probe: fixed synthetic text, no business capture. */
export async function checkNativeUi(userQuestions, agent, signal) {
  signal.throwIfAborted();
  if (!agent || typeof agent.id !== 'string') throw new Error('A live session agent is required');
  const id = 'nexusmore-ui-probe-' + randomUUID();
  const result = await userQuestions.ask({ agent, signal, questions: [{
    id, header: 'G4.1 原生交互检查',
    question: '请选择检查结果；本卡不会批准任何业务内容。',
    detail: 'TEST_ENGINEERING_ONLY\n\n枢模 · NexusMORE 原生问答适配检查。\n'
      + '这里没有业务任务、正文或配图，也不会生成可信用户事件。\n'
      + '本次检查仅验证 DSH 原生问答卡的显示、选择、补充文字和取消行为。\n'
      + '检查标识：' + id,
    options: [{ label: '结束检查', description: '仅记录原生问答能够返回；不创建业务决定。' },
      { label: '取消检查', description: '退出工程检查；不创建业务决定。' }],
    multiSelect: false,
  }] });
  signal.throwIfAborted();
  const answers = result?.answers;
  if (!Array.isArray(answers) || answers.length !== 1 || answers[0]?.id !== id
      || !Array.isArray(answers[0].selected) || answers[0].selected.length !== 1
      || !['结束检查', '取消检查'].includes(answers[0].selected[0])) {
    throw new Error('Unexpected native question response');
  }
  // Never persist or echo custom user text; it is not business evidence.
  return { status: answers[0].selected[0] === '结束检查' ? 'passed' : 'cancelled',
    native_service: 'userQuestions.ask', presentation: 'native_question_card',
    engineering_only: true, model_request_sent: false, user_decision_created: false,
    business_decision_path_invoked: false };
}

export function apply(ctx) {
  registerDecisions(ctx);
  if(ctx.systemPrompt && ctx.sessionController)registerConversation(ctx);
  let pending;
  let nativeUiCheck = { status: 'not_run', engineering_only: true, user_decision_created: false };
  ctx.commands.register({
    name: 'nexusmore-ui-check', description: '枢模 · NexusMORE：G4.1 原生问答工程检查（不审批）', recordInput: false,
    async handler({ agent, rawInput, signal }) {
      if (rawInput.trim()) return { kind: 'error', text: '/nexusmore-ui-check 不接受参数。' };
      try {
        nativeUiCheck = { status: 'waiting', engineering_only: true, user_decision_created: false };
        const value = await checkNativeUi(ctx.userQuestions, agent,
          AbortSignal.any([signal, AbortSignal.timeout(120000)]));
        nativeUiCheck = { ...value, checked_at: new Date().toISOString() };
        return { kind: 'success', text: 'G4.1 原生问答检查：' + (value.status === 'passed' ? '已返回' : '已取消')
          + '。未发送模型请求，未创建业务决定；正式审阅请使用 /nexusmore-review。' };
      } catch {
        nativeUiCheck = { status: 'cancelled_or_failed', engineering_only: true, user_decision_created: false,
          business_decision_path_invoked: false, checked_at: new Date().toISOString() };
        return { kind: 'error', text: 'G4.1 原生问答检查未完成或已取消；未创建业务决定。' };
      }
    },
  });
  ctx.commands.register({
    name: 'nexusmore', description: '枢模 · NexusMORE：只读连接检查与用户确认入口说明', recordInput: false,
    async handler({ agent, rawInput, signal }) {
      if (rawInput.trim()) return { kind: 'error', text: '/nexusmore 不接受参数，仅执行只读连接检查。' };
      try {
        const value = await diagnose(ctx.tools, AbortSignal.any([signal, AbortSignal.timeout(30000)]), agent);
        return { kind: value.status === 'passed' ? 'success' : 'error', text: formatDiagnosis(value) };
      } catch { return { kind: 'error', text: '枢模连接检查失败，请检查 MCP 插件、Python 3.13 和数据库服务。' }; }
    },
  });
  ctx.connection.fetch.register({ path: '/api/nexusmore/status', methods: ['GET'], requestBody: 'buffered',
    fetch: () => Response.json({ registered_tools: registered(ctx.tools), user_decisions: 'trusted_local_cli_and_dsh_native', native_ui_check: nativeUiCheck }, { headers: HEADERS }) });
  ctx.connection.fetch.register({ path: '/api/nexusmore/diagnose', methods: ['POST'], requestBody: 'buffered',
    async fetch(request) {
      // Share concurrent diagnostics; no retries of business operations.
      pending ??= diagnose(ctx.tools, AbortSignal.any([request.signal, AbortSignal.timeout(30000)]))
        .finally(() => { pending = undefined; });
      try { return Response.json(await pending, { headers: HEADERS }); }
      catch { return Response.json({ status: 'failed', code: 'host_diagnosis_failed' }, { status: 503, headers: HEADERS }); }
    } });
  ctx.connection.fetch.register({ path: '/api/nexusmore/panel', methods: ['GET'], requestBody: 'buffered',
    fetch: () => new Response(panelHtml(), { headers: { ...HEADERS, 'Content-Type': 'text/html; charset=utf-8',
      'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'" } }) });
}
