/** Trusted native human-command bridge; no model tool or HTTP approval route.
 * The local OS account/installed host remains the trust boundary, not JSON labels.
 */
import { spawn } from 'node:child_process';
import { randomUUID, createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { isAbsolute, resolve } from 'node:path';

export const PROTOCOL = 'nexusmore-dsh-decisions/1';
const MAX_FRAME = 8 * 1024 * 1024;
const INSTANCE = randomUUID();
const keys = { '--project':'project_id', '--task':'task_id', '--run':'run_id', '--build':'build_id' };

export function parseScope(raw) {
  const words = raw.trim() ? raw.trim().split(/\s+/) : [];
  const scope = {};
  if (words.length % 2) throw new Error('Expected scope flags');
  for (let i=0;i<words.length;i+=2) {
    const key=Object.hasOwn(keys,words[i])?keys[words[i]]:undefined, value=words[i+1];
    if (!key || Object.hasOwn(scope,key) || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/.test(value)) throw new Error('Invalid scope');
    scope[key]=value;
  }
  if (!scope.project_id || !!scope.task_id===!!scope.build_id || scope.run_id&&!scope.task_id) throw new Error('Project and task[/run] or build required');
  return scope;
}

export function backendConfiguration(ctx) {
  const entries=ctx.configEditor.entries().filter(x=>x.options?.id==='nexusmore-workflow');
  if (entries.length!==1 || entries[0].options.name!=='@deepseek-ai/dsh-mcp-client') throw new Error('Ambiguous installed backend');
  return validateBackend(entries[0].options.config);
}

export function validateBackend(c) {
  if (!c || c.transport!=='stdio' || c.serverName!=='nexusmore'
      || !isAbsolute(c.command??'') || !isAbsolute(c.cwd??'')
      || JSON.stringify(c.args)!==JSON.stringify(['-m','modelcrew.workflow_mcp'])
      || !isAbsolute(c.env?.MODELCREW_WORKSPACE??'') || resolve(c.cwd)!==resolve(c.env.MODELCREW_WORKSPACE)) throw new Error('Invalid installed backend');
  return { command:c.command, cwd:c.cwd };
}

async function* frames(stream) {
  let buffered=Buffer.alloc(0);
  for await (const chunk of stream) {
    buffered=Buffer.concat([buffered,Buffer.from(chunk)]);
    let end;
    while ((end=buffered.indexOf(10))>=0) {
      if (end>MAX_FRAME) throw new Error('Oversized private response');
      const line=buffered.subarray(0,end);buffered=buffered.subarray(end+1);
      yield JSON.parse(line.toString('utf8'));
    }
    if (buffered.length>MAX_FRAME) throw new Error('Oversized private response');
  }
  if (buffered.length) throw new Error('Truncated private response');
}

export async function runNativeReview({ userQuestions, agent, signal, backend, scope, mode='review', engineeringOnly=false, spawnWorker=spawn }) {
  signal.throwIfAborted();
  if (!agent || typeof agent.id!=='string' || !['review','status'].includes(mode)) throw new Error('Live native session required');
  // Validate the parsed scope again; UI arguments supply no identity or decisions.
  parseScope(Object.entries(scope).map(([k,v])=>Object.entries(keys).find(([,key])=>key===k)?.[0]+' '+v).join(' '));
  if (!backend || !isAbsolute(backend.command??'') || !isAbsolute(backend.cwd??'')) throw new Error('Explicit backend required');
  const host={instance_id:INSTANCE,session_id:agent.id,pid:process.pid,
    adapter_sha256:createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'),engineering_only:engineeringOnly};
  const child=spawnWorker(backend.command,['-m','modelcrew.dsh_decisions','--private-stdio'],{
    cwd:backend.cwd,env:{...process.env,MODELCREW_WORKSPACE:backend.cwd,PYTHONIOENCODING:'utf-8'},
    windowsHide:true,shell:false,stdio:['pipe','pipe','pipe'],
  });
  const abort=()=>child.kill();
  signal.addEventListener('abort',abort,{once:true});
  child.on('error',()=>child.stdout.destroy(new Error('Private worker unavailable')));
  child.stdin.on('error',()=>{});
  child.stderr.on('data',()=>{}); // Never forward DSNs, traces or user text to logs.
  const write=async value=>{
    signal.throwIfAborted();const data=JSON.stringify(value)+'\n';
    if(Buffer.byteLength(data)>MAX_FRAME)throw new Error('Oversized private request');
    await new Promise((resolve,reject)=>child.stdin.write(data,'utf8',error=>error?reject(error):resolve()));
  };
  let captured=false;
  try {
    await write({protocol:PROTOCOL,mode,scope,host});
    for await (const frame of frames(child.stdout)) {
      signal.throwIfAborted();
      if (frame.type==='questions' && mode==='review' && !captured) {
        if (!/^[a-f0-9]{64}$/.test(frame.frame_id??'') || !Array.isArray(frame.questions) || !frame.questions.length) throw new Error('Invalid native frame');
        const result=await userQuestions.ask({agent,signal,questions:frame.questions});
        signal.throwIfAborted();
        await write({type:'answer',frame_id:frame.frame_id,result});
      } else if (frame.type==='captured' && mode==='review' && !captured) {
        if (!/^[a-f0-9]{64}$/.test(frame.request_sha256??'')) throw new Error('Invalid capture receipt');
        captured=true;
        await write({type:'submit',request_sha256:frame.request_sha256});
      } else if (frame.type==='result') {
        if (!frame.result || typeof frame.result!=='object') throw new Error('Invalid decision response');
        return frame.result;
      } else throw new Error('Private bridge stopped; check original operation status');
    }
    throw new Error('Private bridge disconnected; check original operation status');
  } finally {
    signal.removeEventListener('abort',abort);child.stdin.end();child.kill();
  }
}

/** One short parent-bound operation. No live question/card or human wait. */
export async function runChatReview({agent,signal,backend,scope,mode,payload,engineeringOnly=false,spawnWorker=spawn}){
  signal.throwIfAborted();
  if(!agent?.id||!['preview','confirm'].includes(mode))throw Error('Invalid chat review mode');
  parseScope(Object.entries(scope).map(([k,v])=>Object.entries(keys).find(([,key])=>key===k)?.[0]+' '+v).join(' '));
  const host={instance_id:INSTANCE,session_id:agent.id,pid:process.pid,
    adapter_sha256:createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'),engineering_only:engineeringOnly};
  const child=spawnWorker(backend.command,['-m','modelcrew.dsh_chat','--private-stdio'],{
    cwd:backend.cwd,env:{...process.env,MODELCREW_WORKSPACE:backend.cwd,PYTHONIOENCODING:'utf-8'},
    windowsHide:true,shell:false,stdio:['pipe','pipe','pipe']});
  const abort=()=>child.kill();signal.addEventListener('abort',abort,{once:true});
  child.on('error',()=>child.stdout.destroy(Error('Private chat worker unavailable')));
  child.stdin.on('error',()=>{});child.stderr.on('data',()=>{});
  try{
    signal.throwIfAborted();
    child.stdin.end(JSON.stringify({protocol:'nexusmore-dsh-chat/1',mode,scope,host,payload})+'\n');
    for await(const frame of frames(child.stdout)){
      signal.throwIfAborted();
      if(frame.type!=='result'||!frame.result)throw Error(frame.code==='stale_binding'?'待审内容已更新，请先查看新稿再确认。':'确认未完成；请先查询原回执，不要重复提交。');
      return frame.result;
    }
    throw Error('确认连接中断，请先查询原回执。');
  }finally{signal.removeEventListener('abort',abort);child.kill();}
}

export function registerDecisions(ctx) {
  const active=new Set();
  for(const mode of ['review','status']) ctx.commands.register({
    name:mode==='review'?'nexusmore-review':'nexusmore-review-status',recordInput:false,
    description:mode==='review'?'枢模：原生审阅并提交一笔可信用户决定':'枢模：只读查询原生决定回执，绝不重发',
    async handler({agent,rawInput,signal}) {
      let scope,key;
      try {
        scope=parseScope(rawInput);key=scope.project_id+':'+(scope.task_id??scope.build_id);
        if(mode==='review'&&active.has(key))throw new Error('Review already active');
      } catch {return {kind:'error',text:'使用 --project PROJECT_ID --task TASK_ID [--run RUN_ID]，或 --project PROJECT_ID --build BUILD_ID；不接受决定或身份参数。'};}
      if(mode==='review')active.add(key);
      try {
        const result=await runNativeReview({userQuestions:ctx.userQuestions,agent,
          signal:AbortSignal.any([signal,AbortSignal.timeout(600000)]),backend:backendConfiguration(ctx),scope,mode});
        return {kind:['error','outcome_unknown'].includes(result.status)?'error':'success',text:JSON.stringify(result,null,2)};
      } catch {return {kind:'error',text:'原生审阅已取消、中断或无法完成。若已最终确认，请先用 /nexusmore-review-status 加原对象参数查询原回执；不要换键重发。'};}
      finally {if(mode==='review')active.delete(key);}
    },
  });
}
