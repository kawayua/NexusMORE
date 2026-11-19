/** Conversation UX only. Business state and decisions remain in Python/PostgreSQL. */
import { createHash, randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, lstatSync, readdirSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { spawn } from 'node:child_process';
import { backendConfiguration, runNativeReview, runChatReview } from './nexusmore-dsh-decisions.mjs';
const ID=/^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/;
const hash=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const reviewBinding=b=>hash(['project_id','task_id','version','contract_sha256'].map(k=>b?.[k]));
const ok=x=>x&&x.contract_version==='1.0.0'&&['ok','running','needs_user_input'].includes(x.status);
export function decodeBusiness(result, operation, includeError=false) {
  if(result?.isError&&!includeError)return;
  // DSH's rendered content may be shortened or rewritten. Its canonical MCP
  // value retains the complete structured receipt; use that for host decisions.
  const structured=result?.value?.structuredContent??result?.structuredContent;
  if(structured!==undefined)return structured?.contract_version==='1.0.0'&&structured.operation===operation?structured:undefined;
  for(const part of result?.value?.content??result?.content??[])if(part.type==='text')try{
    const body=JSON.parse(includeError?part.text.replace(/^Error:\s*/, ''):part.text);
    if(body.contract_version==='1.0.0'&&body.operation===operation)return body;
  }catch{}
}
/** Immutable references only; never stores workflow phase, approvals or receipts. */
export class SessionLinks {
  constructor(root){this.root=join(root,'runs','host-bindings','dsh');}
  file(session,kind='task'){
    if(!ID.test(session))throw new Error('Invalid native session');
    return join(this.root,hash(session)+'.'+kind+'.json');
  }
  get(session,kind='task'){
    const file=this.file(session,kind);
    try{
      if(lstatSync(file).isSymbolicLink())throw new Error('Linked session metadata');
      const value=JSON.parse(readFileSync(file,'utf8'));
      if(value.schema!==1||value.session_id!==session||!ID.test(value.project_id)
        ||kind==='task'&&!ID.test(value.task_id))throw new Error('Invalid session reference');
      return value;
    }catch(error){if(error.code==='ENOENT')return;throw error;}
  }
  boundElsewhere(project,task,session){
    let files;try{files=readdirSync(this.root);}catch(error){if(error.code==='ENOENT')return false;throw error;}
    for(const name of files.filter(n=>n.endsWith('.task.json'))){
      const file=join(this.root,name);if(lstatSync(file).isSymbolicLink())throw new Error('Linked reference');
      const value=JSON.parse(readFileSync(file,'utf8'));
      if(this.file(value.session_id)!==file)throw new Error('Invalid reference identity');
      const link=this.get(value.session_id);
      if(link.session_id!==session&&link.project_id===project&&link.task_id===task)return true;
    }
    return false;
  }

  children(session){
    const prefix=hash(session)+'.next.';
    let files;try{files=readdirSync(this.root);}catch(error){if(error.code==='ENOENT')return [];throw error;}
    return files.filter(n=>n.startsWith(prefix)&&n.endsWith('.json')).sort().map(name=>{
      const file=join(this.root,name);if(lstatSync(file).isSymbolicLink())throw new Error('Linked navigation');
      const value=JSON.parse(readFileSync(file,'utf8'));
      if(value.schema!==1||value.parent_session_id!==session||!ID.test(value.session_id)||!ID.test(value.project_id)
        ||name!==prefix+hash(value.session_id)+'.json')throw new Error('Invalid question navigation');
      return value;
    });
  }
  addChild(parent,child,project){
    if(!ID.test(parent)||!ID.test(child)||parent===child||!ID.test(project))throw new Error('Invalid navigation');
    const value={schema:1,parent_session_id:parent,session_id:child,project_id:project};
    mkdirSync(this.root,{recursive:true});
    writeFileSync(join(this.root,hash(parent)+'.next.'+hash(child)+'.json'),JSON.stringify(value)+'\n',{encoding:'utf8',flag:'wx'});
  }

  put(session,scope,kind='task'){
    if(!ID.test(scope.project_id)||kind==='task'&&!ID.test(scope.task_id))throw new Error('Invalid binding');
    if(kind==='task'&&this.boundElsewhere(scope.project_id,scope.task_id,session))throw new Error('Task already linked to another native chat');
    const value={schema:1,session_id:session,project_id:scope.project_id,...kind==='task'?{task_id:scope.task_id}:{}};
    mkdirSync(this.root,{recursive:true});
    try{writeFileSync(this.file(session,kind),JSON.stringify(value)+'\n',{encoding:'utf8',flag:'wx'});}
    catch(error){if(error.code!=='EEXIST')throw error;}
    const stored=this.get(session,kind);
    if(JSON.stringify(stored)!==JSON.stringify(value))throw new Error('Session already belongs to another task');
    return stored;
  }
}
/** Only host-admitted user RPC messages may become original text; never model paths. */
export function nativeText(messages){
  const message=[...messages].reverse().find(m=>m.role==='user'&&m.source?.kind==='user'&&ID.test(m.source.rpcId??''));
  if(!message)return;
  if(!ID.test(message.id??'')||!message.content?.length||message.content.some(p=>p.type!=='text'))throw Error('当前只支持原生文本题目；附件需可信导入后再建题。');
  const text=message.content.map(p=>p.text).join('\n');
  if(!text.trim()||Buffer.byteLength(text)>65536)throw Error('题目为空或超过文本导入上限。');
  return {id:message.id,rpc_id:message.source.rpcId,text};
}
export class NativeIntake {
  constructor(links){this.links=links;this.pending=new Map();}
  file(id){return this.links.file(id,'input');}
  read(id){try{
    const file=this.file(id);if(lstatSync(file).isSymbolicLink())throw Error('Linked native intake');
    const v=JSON.parse(readFileSync(file,'utf8'));
    if(v.schema!==1||v.session_id!==id||!ID.test(v.project_id)||v.result?.status!=='prepared'
        ||v.result.owner?.project_id!==v.project_id||!ID.test(v.result.owner?.task_id))throw Error('Invalid input receipt');
    return v;
  }catch(e){if(e.code==='ENOENT')return;throw e;}}
  capture(agent,messages){if(this.links.get(agent.id)||this.read(agent.id))return;const source=nativeText(messages);if(source)this.pending.set(agent.id,source);}
  store(id,project,result){
    const value={schema:1,session_id:id,project_id:project,result};mkdirSync(this.links.root,{recursive:true});
    try{writeFileSync(this.file(id),JSON.stringify(value)+'\n',{encoding:'utf8',flag:'wx'});}catch(e){if(e.code!=='EEXIST')throw e;}
    const stored=this.read(id);if(JSON.stringify(stored)!==JSON.stringify(value))throw Error('Intake already belongs elsewhere');
    this.pending.delete(id);return stored;
  }
}
export async function prepareNativeInput(backend,agent,project,message,signal){
  signal.throwIfAborted();
  const host={instance_id:'native-intake',session_id:agent.id,pid:process.pid,
    adapter_sha256:createHash('sha256').update(readFileSync(new URL('./nexusmore-dsh-decisions.mjs',import.meta.url))).digest('hex'),engineering_only:false};
  const child=spawn(backend.command,['-m','modelcrew.dsh_inputs','--private-stdio'],{cwd:backend.cwd,
    env:{...process.env,MODELCREW_WORKSPACE:backend.cwd,PYTHONIOENCODING:'utf-8'},windowsHide:true,shell:false,stdio:['pipe','pipe','pipe']});
  let bytes=0,chunks=[];child.stderr.on('data',()=>{});child.stdin.on('error',()=>{});
  const abort=()=>child.kill();signal.addEventListener('abort',abort,{once:true});
  try{return await new Promise((accept,reject)=>{
    child.on('error',reject);child.stdout.on('data',data=>{bytes+=data.length;if(bytes>1048576){child.kill();reject(Error('Oversized intake receipt'));}else chunks.push(data);});
    child.on('close',code=>{try{signal.throwIfAborted();const v=JSON.parse(Buffer.concat(chunks).toString('utf8'));if(code!==0||v.type!=='result'||v.result?.status!=='prepared')throw Error('可信原题导入未完成；请保留当前会话重试。');accept(v.result);}catch(e){reject(e);}});
    signal.throwIfAborted();child.stdin.end(JSON.stringify({protocol:'nexusmore-dsh-input/1',host,project_id:project,message})+'\n');
  });}finally{signal.removeEventListener('abort',abort);child.kill();}
}
/** UI receipts only. The authoritative review and approval stay in Python. */
export class ChatReviewStore {
  constructor(links){this.links=links;}
  read(id){try{const file=this.links.file(id,'review');if(lstatSync(file).isSymbolicLink())throw Error('Linked review pointer');
    const v=JSON.parse(readFileSync(file,'utf8'));if(v.session_id!==id||v.schema!==1)throw Error('Invalid review pointer');return v;
  }catch(e){if(e.code==='ENOENT')return;throw e;}}
  write(id,value){mkdirSync(this.links.root,{recursive:true});const file=this.links.file(id,'review');
    try{if(lstatSync(file).isSymbolicLink())throw Error('Linked review pointer');}catch(e){if(e.code!=='ENOENT')throw e;}
    const tmp=file+'.'+randomUUID()+'.tmp';writeFileSync(tmp,JSON.stringify({schema:1,session_id:id,...value})+'\n',{encoding:'utf8',flag:'wx'});renameSync(tmp,file);
  }
}
const MODEL_APPROVAL=/^(?:我?确认(?:你的|你|上述|以上|这)?(?:三个|三项|3个|3项)?口径[，,、；; ]*)?我?(?:同意|通过|确认通过|审核通过)(?:当前|这份|本版)?(?:建模方案|模型方案)(?:[，,、；; ]*(?:并|请|可以)?(?:进入|继续进入)(?:代码手|代码手阶段))?$/u;
export function isChatApproval(text,kind){
  if(typeof text!=='string')return false;
  const value=text.trim().replace(/[。！!]+$/u,'');
  if(new Set(['同意','确认','通过','审核通过','确认通过','确认审核','确认当前版本','确认当前版本，继续','确认这个版本，继续','通过，继续']).has(value))return true;
  return (kind===undefined||kind==='model')&&!/[\r\n]/u.test(value)&&MODEL_APPROVAL.test(value);
}
export function nativeFileLink(session,path){
  return 'dsh-resource://file/session/'+encodeURIComponent(session)+'/'+path.replace(/\\/g,'/').split('/').map(x=>encodeURIComponent(x).replace(/%3A/gi,':')).join('/');
}
export function chatReplyAfterPreview(messages,record){
  // DSH pre-step messages are freshly claimed inbox entries, NOT history.
  // The file notice must have entered a previous step before a user reply
  // can authorize it. Never approve a message queued in the same batch.
  if(!record||record.state!=='waiting_for_user'||record.delivered!==true)return;
  if(messages.some(m=>m.id===record.notice_id))return;
  const message=nativeText(messages);
  return message?.id!==record.after_message?.id&&message?.rpc_id!==record.after_message?.rpc_id?message:undefined;
}
/** User-owned scratch cwd for the native sandbox; backend workspace remains fixed. */
export async function sandboxWorkspace(ctx,backend){
  const root=resolve(process.env.LOCALAPPDATA??join(homedir(),'.local','share'),'NexusMORE','dsh-workspaces',hash(backend.cwd).slice(0,24),randomUUID());
  for(let path=root;;){try{if(lstatSync(path).isSymbolicLink())throw Error('Linked scratch workspace');}catch(e){if(e.code!=='ENOENT')throw e;}const parent=resolve(path,'..');if(parent===path)break;path=parent;}
  mkdirSync(root,{recursive:true});
  return await ctx.workspaceRegistry.resolveByPath(root)??await ctx.workspaceRegistry.create(root);
}
const hostNotice=text=>Object.freeze({id:randomUUID(),role:'user',source:Object.freeze({kind:'cordis-host-runner'}),content:Object.freeze([{type:'text',text}])});
/** DSH UserMessage wire value. The source is a host notice, never a human signature. */
export function continueAgent(agent,scope){
  const content=Object.freeze([Object.freeze({type:'text',text:
    '枢模宿主状态通知：本会话的新模型批准已由可信桥接提交，后端已允许推进。'
    +'请先调用 task_status 读取当前任务与阶段，再继续后端允许的下一步；不得重复批准、跳过独立审查或假定代码/结果已完成。'
    +'任务引用：'+JSON.stringify(scope)})]);
  agent.followup(Object.freeze({id:randomUUID(),role:'user',source:Object.freeze({kind:'cordis-host-runner'}),content}));
}
/** A bound chat may read other material, but cannot mutate another question. */
export function admission(links,exec,intake){
  if(!exec.agent||!exec.name?.startsWith('mcp__nexusmore__'))return;
  const args=exec.arguments?.arguments,link=links.get(exec.agent.id),hint=links.get(exec.agent.id,'project');
  const operation=exec.name.slice('mcp__nexusmore__'.length);
  const reads=new Set(["projects_list", "tasks_list", "task_status", "versions_list", "version_read", "proposal_read", "modeling_status", "assembly_status", "assembly_build_status", "hand_status", "result_read", "artifacts_list", "mathematics_read", "tool_evidence_read", "capabilities_read", "project_read", "pending_list", "operation_status", "artifact_read", "assembly_artifacts_list"]);
  if(reads.has(operation))return;
  if(operation==='task_create'&&intake){
    const prepared=intake.read(exec.agent.id);
    if(!prepared||prepared.result.owner.task_id!==args?.body?.id||prepared.project_id!==args?.project_id)
      return {kind:'deny',reason:'请等待宿主可信原题导入通知，并使用其中的 task_id 与 input artifact 引用；不要猜测或自行登记文件。'};
  }
  if(operation==='task_create'&&links.boundElsewhere(args?.project_id,args?.body?.id,exec.agent.id))
    return {kind:'deny',reason:'下一题必须使用新的任务编号，不能复用其他会话的小题。'};
  if(link&&(args?.task_id&&args.task_id!==link.task_id||args?.project_id&&args.project_id!==link.project_id)
    ||hint&&args?.project_id&&args.project_id!==hint.project_id
    ||operation==='task_create'&&link&&(args?.body?.id!==link.task_id||args?.project_id!==link.project_id))
    return {kind:'deny',reason:'当前会话已绑定小题或项目；请使用继续下一题入口。'};
}
/** Fixed read-only native sandbox probe; no model request or configurable command. */
export async function probeSandbox(tools,agent,signal){
  signal.throwIfAborted();
  const batch=await tools.execute({agent,signal,calls:[{id:'nexusmore-sandbox-'+randomUUID(),name:'pwsh',arguments:JSON.stringify({command:'$PSVersionTable.PSVersion.ToString()',description:'Read native PowerShell version in the current question workspace'})}]});
  const result=batch?.results?.[0]?.result;
  const version=result?.content?.filter(p=>p.type==='text').map(p=>p.text).join('').trim();
  if(result?.isError||!/^\d+\.\d+\.\d+$/.test(version??''))throw Error('Native sandbox unavailable');
  return {status:'passed',powershell_version:version,model_request_sent:false,user_approval_created:false};
}
export class ConversationFlow {
  constructor({links,call,review,prepare,accept,store,notify=continueAgent}){Object.assign(this,{links,call,review,prepare,accept,store,notify});this.latestUser=new Map();this.active=new Map();this.seen=new Set();this.notified=new Set();this.feedback=new Map();this.closed=false;this.queuedReviews=new Map();}
  observe(exec,result){
    if(this.closed||!exec.agent||!exec.name?.startsWith('mcp__nexusmore__'))return;
    const operation=exec.name.slice('mcp__nexusmore__'.length),body=decodeBusiness(result,operation,true);
    if(result?.isError&&body?.status!=='blocked'||!ok(body)&&!(body?.status==='blocked'&&body?.data?.host_review))return;
    const session=exec.agent.id;
    try{
      if(operation==='task_create'){
        const args=exec.arguments?.arguments;
        if(!args||body.binding?.project_id!==args.project_id||body.binding?.task_id!==args.body?.id)return;
        const hint=this.links.get(session,'project');
        if(hint&&hint.project_id!==body.binding.project_id)throw new Error('Next question changed project');
        this.links.put(session,body.binding);
      }
      const link=this.links.get(session);
      if(!link||body.binding?.task_id!==link.task_id||body.binding?.project_id!==link.project_id)return;
      if(body.pending?.length){
        const readiness=body.data?.host_review;
        const running=this.active.get(link.project_id+':'+link.task_id);
        if(running?.binding&&running.binding!==reviewBinding(body.binding))running.abort();
        if(body.pending.some(p=>p.kind==='model')&&readiness?.model_ready!==true&&!readiness?.open_questions?.length){
          this.feedback.set(session,{state:'preparing_model',message:'数学基线、独立 M1 与当前版本尚未就绪，暂不发起方案批准。'});return;
        }
        const key=hash([session,body.pending,this.latestUser.get(session)?.id]);
        if(this.seen.has(key)||String(exec.callId??'').startsWith('nexusmore-flow-'))return;
        this.queuedReviews.set(session,{agent:exec.agent,key});
        // A tool-result observer never blocks or changes the tool outcome.
        queueMicrotask(()=>void this.flushReview(session));
      }
    }catch{this.feedback.set(session,{state:'binding_conflict',message:'本会话已有其他小题，请在下一题会话中继续。'});}
  }
  async flushReview(session){
    const queued=this.queuedReviews.get(session);if(!queued||this.closed)return;
    const scope=this.links.get(session);if(!scope||this.active.has(scope.project_id+':'+scope.task_id))return;
    this.queuedReviews.delete(session);
    if(this.seen.has(queued.key))return;
    try{
      const result=await this.run(queued.agent);
      if(['waiting_for_user','choose_required','waiting_for_facts'].includes(result.status))this.seen.add(queued.key);
    }catch{
      this.feedback.set(session,{state:'publication_failed',message:'宿主待审文件未发布，尚不能确认；下一条用户消息将重新核对并展示当前稿。'});
      queued.agent.followup(hostNotice('宿主待审文件尚未发布，不能把模型自行附上的文件当成已登记审阅稿。请说明审阅发布未完成并停止等待；后续先恢复正式待审文件展示，不要求用户运行终端，也不能代用户批准。'));
    }
  }
  async run(agent,mode='review',outerSignal,kind){
    const scope=this.links.get(agent.id);if(!scope)throw new Error('No task linked');
    const key=scope.project_id+':'+scope.task_id;
    if(this.active.has(key))return {status:'busy'};
    const controller=new AbortController();this.active.set(key,controller);
    const abort=()=>controller.abort();outerSignal?.addEventListener('abort',abort,{once:true});if(outerSignal?.aborted)controller.abort();
    this.feedback.set(agent.id,{state:mode==='status'?'checking_receipt':'waiting_for_user'});
    try{
      let current;
      if(mode==='review'){
        current=await this.call(agent,'task_status',{task_id:scope.task_id},controller.signal);
        controller.binding=reviewBinding(current?.binding);
        controller.signal.throwIfAborted();
        if(!ok(current)||current.pending?.some(p=>p.kind==='model')&&current.data?.host_review?.model_ready!==true){
          const questions=current.data?.host_review?.open_questions;
          if(questions?.length&&this.clarify){
            this.feedback.set(agent.id,{state:'clarification_required',message:'请补充题目信息；这不是方案批准。'});
            const answer=await this.clarify(agent,questions,current.binding,controller.signal);
            if(answer?.conversation_wait){this.feedback.set(agent.id,{state:'waiting_for_facts',message:'请在对话中补充上述信息。'});return {status:'waiting_for_facts'};}
            const fresh=await this.call(agent,'task_status',{task_id:scope.task_id},controller.signal);
            if(reviewBinding(fresh.binding)!==reviewBinding(current.binding))throw Error('Clarification version changed');
            agent.followup(hostNotice('枢模宿主资料补充（不是业务批准）：'+JSON.stringify({binding:current.binding,answers:answer})
              +'。只补充原题缺失事实；使用新请求重新运行建模与独立 M1，保留旧运行，不得因回复资料而执行或批准。'));
            this.feedback.set(agent.id,{state:'clarification_received'});return {status:'clarification_received'};
          }
          this.feedback.set(agent.id,{state:'preparing_model',message:'当前版本尚未具备方案审阅条件；先完成数学基线、独立 M1 和必要澄清。'});
          return {status:'not_ready'};
        }
      }
      let result;
      if(mode==='review'&&this.prepare){
        const preview=await this.prepare(agent,{project_id:scope.project_id,task_id:scope.task_id},this.latestUser.get(agent.id)??null,controller.signal,kind);
        if(preview.status==='waiting_for_user'){
          const old=this.store.read(agent.id);
          // A refreshed waiting document needs no second model response.
          if(old?.state==='waiting_for_user'&&old.preview.preview_id===preview.preview_id){
            this.feedback.set(agent.id,{state:'waiting_for_user',title:preview.title,file_link:old.file_link});return preview;
          }
          const file_link=nativeFileLink(agent.id,preview.local_path);
          const notice=hostNotice('待审文件已准备好（尚未批准）：['+preview.title+' · v'+preview.binding.version+']('+file_link+')。'
            +(preview.confirmation_scope==='manuscript_and_figures'?'这是正文和带图候选清单的合并审阅页，一次确认同时批准当前正文与当前暂列入文配图。':'')
            +'请在本轮最终回复中展示这个原生文件链接，简要说明待审核内容，然后结束本轮并等待用户。用户可提出修改意见，或回复“通过”确认刚展示的这个对象和版本；不要求输入命令或运行工具，不展示内部 JSON，不重复建模。');
          this.store.write(agent.id,{state:'waiting_for_user',preview,file_link,notice_id:notice.id,delivered:false,after_message:this.latestUser.get(agent.id)??null});
          agent.followup(notice);
          this.feedback.set(agent.id,{state:'waiting_for_user',title:preview.title,file_link});return preview;
        }
        if(preview.status==='choose_required'){
          this.store.write(agent.id,{state:'choose_required'});
          agent.followup(hostNotice('当前存在多个不同任务或版本的待审对象，请先确定要审阅哪一个。同一写作版本的正文和配图应合并展示并一次确认；不要要求用户分别批准。'));
        }
        this.feedback.set(agent.id,{state:preview.status,message:preview.status==='choose_required'?'有多个待审对象，请确定要审阅的任务或版本。':'当前没有可展示的待审稿。'});return preview;
      }
      result=await this.review(agent,{project_id:scope.project_id,task_id:scope.task_id},mode,controller.signal);
      await this.afterDecision(agent,result,mode,controller.signal);
      return result;
    }catch(error){this.feedback.set(agent.id,{state:'paused',message:'已暂停；若已最终确认，请先查询原回执，勿重复提交。'});throw error;}
    finally{outerSignal?.removeEventListener('abort',abort);this.active.delete(key);if(this.queuedReviews.has(agent.id))queueMicrotask(()=>void this.flushReview(agent.id));}
  }
  async afterDecision(agent,result,mode,signal,wake=true){
    const scope=this.links.get(agent.id);
      // A status read, replay, rejection, cancellation, or uncertain result never resumes a workflow.
      const decision=result?.data?.user_decision;
      if(mode==='review'&&ok(result)&&result.replayed!==true&&result.operation==='task_decide'
          &&decision?.decision==='approve'&&decision.kind==='model'){
        const current=await this.call(agent,'task_status',{task_id:scope.task_id},signal);
        const approved=decision.confirmed_binding;
        if(!ok(current)||!approved||['project_id','task_id','version','contract_sha256'].some(k=>current.binding?.[k]!==approved[k]))throw new Error('Changed after decision');
        if(!decision.event_reference?.event_id||current.data?.task?.model_approved!==true)throw new Error('Approval not committed');
        const resumed=await this.call(agent,'task_resume',{task_id:scope.task_id},signal,
          {request_id:'dsh-resume-'+hash(decision.event_reference).slice(0,48),expected_binding:current.binding});
        this.feedback.set(agent.id,{state:resumed.status==='outcome_unknown'?'outcome_unknown':ok(resumed)?'continued':'blocked',phase:resumed.phase});
        if(ok(resumed)&&!resumed.pending?.length&&!signal.aborted&&!this.closed){
          const event=hash(decision.event_reference);
          if(!this.notified.has(event)){
            // Claim before delivering: an uncertain notification must not silently dispatch twice.
            this.notified.add(event);if(wake)await this.notify(agent,{project_id:scope.project_id,task_id:scope.task_id});
          }
        }
      }else this.feedback.set(agent.id,{state:mode==='status'?'receipt_checked':!ok(result)?'blocked':decision?.decision==='reject'?'revision_requested':'review_completed'});

  }
  async onUser(agent,messages,signal){
    let message;try{message=nativeText(messages);}catch{return;}
    if(message)this.latestUser.set(agent.id,message);
    const record=this.store?.read(agent.id);
    if(record?.state==='waiting_for_user'&&messages.some(m=>m.id===record.notice_id&&m.role==='user'&&m.source?.kind==='cordis-host-runner')){
      this.store.write(agent.id,{...record,delivered:true});return;
    }
    const needsPublication=!record||(['waiting_for_user','discussion'].includes(record.state)&&record.preview?.kind==='model'&&record.preview.renderer_version!=='readable-model/1');
    if(needsPublication&&message&&this.links.get(agent.id)&&this.prepare){
      // Restart or an earlier publication failure: show the current version now,
      // never apply this already-arrived message retroactively to a new preview.
      try{
        const preview=await this.run(agent,'review',signal);
        if(preview.status==='waiting_for_user')return hostNotice('宿主刚恢复并发布当前版本的正式待审文件。本条用户消息早于此次展示，未登记为批准；请展示通知中的原生文件链接，结束本轮并等待用户再次明确确认。');
      }catch{
        this.feedback.set(agent.id,{state:'publication_failed',message:'正式待审文件发布失败；尚未提交任何确认。'});
        return hostNotice('正式待审文件未能发布，本条消息未登记为批准。请说明宿主审阅发布失败并停止推进，不要求用户运行终端或替用户批准。');
      }
    }
    if(!record||!message)return;
    if(record.state==='choose_required'){
      const kind=({'看正文':'manuscript','先看正文':'manuscript','看配图':'figures','先看配图':'figures','看图':'figures','先看图':'figures'})[message.text.trim()];
      if((kind||isChatApproval(message.text))&&record.last_message!==message.id){
        this.store.write(agent.id,{...record,last_message:message.id});
        await this.run(agent,'review',signal,kind);
      }
      return;
    }
    const reply=chatReplyAfterPreview(messages,record);if(!reply)return;
    const scope=this.links.get(agent.id);if(!scope)return;
    if(!isChatApproval(reply.text,record.preview?.kind)){
      this.store.write(agent.id,{...record,state:'discussion',last_message:reply.id});
      this.feedback.set(agent.id,{state:'discussion',message:'已收到意见；待新稿展示后再确认。'});return;
    }
    // Claim before entering the worker: retries query the original receipt,
    // never recapture or synthesize a user response after a lost connection.
    this.store.write(agent.id,{...record,state:'confirming',last_message:reply.id});
    try{
      const result=await this.accept(agent,{project_id:scope.project_id,task_id:scope.task_id},record.preview.preview_id,reply,signal);
      const state=result?.status==='outcome_unknown'?'outcome_unknown':ok(result)?'confirmed':'confirmation_blocked';
      this.store.write(agent.id,{...record,state,last_message:reply.id});
      await this.afterDecision(agent,result,'review',signal,false);
      return hostNotice(ok(result)?'宿主已记录用户对所展示版本的真实确认。先调用 task_status，再推进后端允许的下一步；不得重复批准。':'用户确认尚未提交成功或结果未知；先读取 task_status 与原回执，不得假定通过、自动重试或换键提交。');
    }catch{
      this.store.write(agent.id,{...record,state:'confirmation_blocked',last_message:reply.id});
      this.feedback.set(agent.id,{state:'confirmation_blocked',message:'待审版本可能已变更，或确认结果未明；请先查询原回执并查看当前稿。'});
      return hostNotice('本次用户确认未能核实提交。先查询原回执与 task_status；不得代用户批准或重复提交。若版本已变化，重新展示当前待审文件并等待下一条用户确认。');
    }
  }
  close(){this.closed=true;for(const controller of this.active.values())controller.abort();}
}
export function registerConversation(ctx,{engineeringOnly=false}={}){
  const backend=backendConfiguration(ctx),links=new SessionLinks(backend.cwd),intake=new NativeIntake(links);
  const noticeSent=new Set(),store=new ChatReviewStore(links);
  const call=async(agent,operation,args,signal,extra={})=>{
    const request={contract_version:'1.0.0',operation,arguments:args,...extra};
    const batch=await ctx.tools.execute({agent,signal,calls:[{id:'nexusmore-flow-'+randomUUID(),name:'mcp__nexusmore__'+operation,arguments:JSON.stringify(request)}]});
    const body=decodeBusiness(batch?.results?.[0]?.result,operation);
    if(!body)throw new Error('No authoritative response');return body;
  };
  const flow=new ConversationFlow({links,call,store,
    prepare:(agent,scope,after_message,signal,kind)=>runChatReview({agent,scope,mode:'preview',payload:{after_message,kind:kind??null},backend,engineeringOnly,signal:AbortSignal.any([signal,AbortSignal.timeout(30000)])}),
    accept:(agent,scope,preview_id,message,signal)=>runChatReview({agent,scope,mode:'confirm',payload:{preview_id,message},backend,engineeringOnly,signal:AbortSignal.any([signal,AbortSignal.timeout(60000)])}),
    review:(agent,scope,mode,signal)=>runNativeReview({
    userQuestions:ctx.userQuestions,agent,scope,mode,backend,engineeringOnly,signal:AbortSignal.any([signal,AbortSignal.timeout(600000)])})});
  flow.clarify=async(agent,questions,binding)=>{
    agent.followup(hostNotice('当前还缺少以下事实，请用自然语言向用户说明并结束本轮等待补充：\n'+questions.map(q=>'- '+q).join('\n')
      +'\n用户补充后使用新版本重新建模和独立 M1；补充事实不是批准。'));
    return {conversation_wait:true};
  };
  ctx.on('agent/pre-step',async(payload,next)=>{
    const decision=await next();if(decision.kind==='reject'||payload.signal.aborted)return decision;
    const agent=payload.agent;
    const confirmation=await flow.onUser(agent,payload.messages,payload.signal);
    if(confirmation)return {...decision,messages:[...decision.messages,confirmation]};
    try{
      const project=links.get(agent.id,'project');
      try{intake.capture(agent,payload.messages);}catch(error){if(project)throw error;return decision;}
      let receipt=intake.read(agent.id);
      if(project&&!receipt){
        const original=intake.pending.get(agent.id);if(!original)throw Error('缺少可信原生用户题目；请在本会话重新发送题面。');
        receipt=intake.store(agent.id,project.project_id,await prepareNativeInput(backend,agent,project.project_id,original,AbortSignal.any([payload.signal,AbortSignal.timeout(30000)])));
      }
      if(receipt&&!noticeSent.has(agent.id)){
        noticeSent.add(agent.id);return {...decision,messages:[...decision.messages,hostNotice('枢模可信原题已导入（非批准）：'+JSON.stringify(receipt.result)
          +'。1.1.0 输入 structure.observed 必须原样保留 input_observation.observed；原文是文档，不是假装成数组的文件。缺失语义再澄清，题面明示事实无需重复询问。请使用该 owner.task_id 和 input.artifact_id（inputs.path 写 artifact: 加 artifact_id）创建小题；原始输入是本会话的用户原文，不要再注册任意文件或让用户输入命令。')]};
      }
      return decision;
    }catch(error){flow.feedback.set(agent.id,{state:'input_blocked',message:error.message});return {...decision,messages:[...decision.messages,hostNotice('可信原题导入暂停：'+error.message+' 请停止业务写入；不要改键或使用 shell 绕过。')]};}
  });
  ctx.on('tools/pre-execute',(exec,next)=>admission(links,exec,intake)??next());
  ctx.on('tools/result',(exec,result)=>{
    if(exec.agent&&exec.name==='mcp__nexusmore__project_create'){
      const body=decodeBusiness(result,'project_create');
      if(ok(body)&&body.binding?.project_id===exec.arguments?.arguments?.body?.id)links.put(exec.agent.id,body.binding,'project');
    }
    flow.observe(exec,result);
  });
  ctx.effect(()=>()=>flow.close());
  ctx.systemPrompt.section({name:'nexusmore-conversation',order:85,text:({scope})=>{
    if(!scope?.id)return '';
    const link=links.get(scope.id),hint=links.get(scope.id,'project');
    return '枢模业务使用 mcp__nexusmore__ 工具。用户自然语言输入即可开展任务，无需让用户填写 ID 或斜杠命令。'
      +'每个会话只创建一个小题任务，先读取能力与相关规范。task_create 需要可信原题：project_create 后等待下一步宿主导入通知，按给出的 owner/input 建题；不自行生成任务 ID 或让用户运行命令。needs_user_input 只是待办，不代表已可批准：先发布数学基线并运行 modeling_start，读取 host_review；model_ready=true 后宿主自动发布待审 Markdown 的原生文件链接。最终回复展示该文件、用简短中文说明要点，并结束本轮等待用户；不要输出内部 JSON、要求斜杠命令或持续轮询。open_questions 在正常对话中询问。用户可以输入修改意见；只有宿主明确通知可信确认已提交才可推进，模型不能自行把“通过”或工具许可当成批准。'
      +'业务规范和资源的只读根目录是 '+backend.cwd+'；原生 shell 在用户专属工作区运行，不要将业务根目录设为 shell cwd。手动文件限当前用户工作区；业务产物由 MCP 登记生成。'
      +'方案批准后的宿主推进只进入后端允许的阶段，不代表代码执行、质检或论文已完成。'
      +(link?'当前绑定：'+JSON.stringify({project_id:link.project_id,task_id:link.task_id})
        :hint?'下一小题沿用项目 '+hint.project_id+'，创建新的 task_id；不得复制上题批准或假定未确认结果有效。':'尚未绑定任务；根据用户题目使用项目和任务创建工具。');
  }});
  for(const mode of ['review','status'])ctx.commands.register({
    name:mode==='review'?'nexusmore-current-review':'nexusmore-current-status',recordInput:false,
    description:mode==='review'?'展示当前小题待审文件，在对话中确认':'查询当前小题的原确认回执，不重发',
    async handler({agent,rawInput,signal}){
      if(rawInput.trim())return {kind:'error',text:'此入口不接受参数。'};
      try{const value=await flow.run(agent,mode,signal);return {kind:'success',text:value.status==='waiting_for_user'?'待审核：['+value.title+']('+nativeFileLink(agent.id,value.local_path)+')。请查看后在对话中回复“通过”，也可直接提出修改意见。':JSON.stringify(value)};}
      catch{return {kind:'error',text:'当前小题尚未绑定或已暂停；最终确认后请先查询原回执。'};}
    }
  });
  ctx.commands.register({name:'nexusmore-sandbox-check',recordInput:false,description:'只读检查当前题目的原生 PowerShell 沙箱',async handler({agent,rawInput,signal}){
    if(rawInput.trim())return {kind:'error',text:'此诊断不接受参数。'};
    try{return {kind:'success',text:JSON.stringify(await probeSandbox(ctx.tools,agent,signal))};}
    catch{return {kind:'error',text:'原生沙箱探针未通过；请检查本题工作区权限，不要关闭沙箱或扩大目录权限。'};}
  }});
  ctx.commands.register({name:'nexusmore-start-question',recordInput:false,description:'在用户专属沙箱工作区开始小题',async handler({rawInput}){
    if(rawInput.trim())return {kind:'error',text:'此入口不接受参数。'};
    try{const workspace=await sandboxWorkspace(ctx,backend);const created=await ctx.sessionController.create({workspaceId:workspace.id});return {kind:'success',text:JSON.stringify({session_id:created.sessionId})};}
    catch{return {kind:'error',text:'未能创建小题工作区；请检查本机用户目录访问权限。'};}
  }});
  ctx.commands.register({name:'nexusmore-next-question',recordInput:false,description:'在同项目创建下一小题的独立会话',
    async handler({agent,rawInput,signal}){
      if(rawInput.trim())return {kind:'error',text:'此入口不接受参数。'};
      try{
        const link=links.get(agent.id);if(!link)throw new Error('No linked task');
        const workspace=await sandboxWorkspace(ctx,backend);
        const created=await ctx.sessionController.create({workspaceId:workspace.id});
        links.put(created.sessionId,{project_id:link.project_id},'project');
        links.addChild(agent.id,created.sessionId,link.project_id);
        return {kind:'success',text:JSON.stringify({session_id:created.sessionId,project_id:link.project_id})};
      }catch{return {kind:'error',text:'无法创建下一题；请检查当前任务和 DSH 工作区绑定。'};}
    }});
  // No decision payload, identity, dynamic tool proxy or HTTP approval endpoint.
  ctx.connection.fetch.register({path:'/api/nexusmore/conversation',methods:['GET'],requestBody:'buffered',fetch:request=>{
    const id=new URL(request.url).searchParams.get('session');
    try{return Response.json({link:links.get(id)??null,project:links.get(id,'project')??null,children:links.children(id),feedback:flow.feedback.get(id)??null},{headers:{'Cache-Control':'no-store'}});}
    catch{return Response.json({error:'invalid_session'},{status:400});}
  }});
  return flow;
}
