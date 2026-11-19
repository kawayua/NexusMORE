import {runInNewContext} from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {SessionLinks,ConversationFlow,decodeBusiness,continueAgent,admission,nativeText,NativeIntake,sandboxWorkspace,probeSandbox} from '../../src/harness/nexusmore-dsh-conversation.mjs';
const agent={id:'session-synthetic-a',followup:()=>{}},scope={project_id:'p',task_id:'q1',version:1,contract_sha256:'a'.repeat(64)};
const body=(status='needs_user_input',extra={})=>({contract_version:'1.0.0',operation:'task_create',status,binding:scope,pending:[{pending_id:'pending-1',kind:'model'}],...extra,data:{host_review:{model_ready:true},...extra.data}});
const result=value=>({content:[{type:'text',text:JSON.stringify(value)}]});
const exec={agent,name:'mcp__nexusmore__task_create',arguments:{arguments:{project_id:'p',body:{id:'q1'}}}};
function fixture(review=async()=>{throw Error('cancel')},call=async()=>body('needs_user_input',{operation:'task_status'})){
 const root=mkdtempSync(join(tmpdir(),'nexusmore-conversation-')),links=new SessionLinks(root);
 return {links,flow:new ConversationFlow({links,review,call})};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('session references persist independently without workflow state or decisions',()=>{
 const {links}=fixture();links.put(agent.id,scope);assert.equal(new SessionLinks(links.root.split('runs')[0]).get(agent.id).task_id,'q1');
 const raw=readFileSync(links.file(agent.id),'utf8');assert.equal(/approved|phase|receipt|contract_sha256/.test(raw),false);
 assert.throws(()=>links.put(agent.id,{project_id:'p',task_id:'q2'}));
});
test('cross-question references and project hints remain separate',()=>{
 const {links}=fixture();links.put(agent.id,scope);links.put('session-b',{project_id:'p'},'project');
 assert.equal(links.get('session-b'),undefined);links.put('session-b',{project_id:'p',task_id:'q2'});
 assert.equal(links.get(agent.id).task_id,'q1');assert.equal(links.get('session-b').task_id,'q2');
});
test('tampered, invalid and mismatched session references fail closed',()=>{
 const {links}=fixture();assert.throws(()=>links.get('../escape'));links.put(agent.id,scope);
 writeFileSync(links.file(agent.id),JSON.stringify({schema:1,session_id:'session-other',project_id:'p',task_id:'q1'}));
 assert.throws(()=>links.get(agent.id));
});
test('actual task creation links and automatically presents one pending review',async()=>{
 let calls=0;const {flow,links}=fixture(async(a,s,mode)=>{calls++;assert.equal(a,agent);assert.deepEqual(s,{project_id:'p',task_id:'q1'});return {status:'cancelled'};});
 flow.observe(exec,result(body()));flow.observe(exec,result(body()));await tick();
 assert.equal(calls,1);assert.equal(links.get(agent.id).task_id,'q1');
});
test('unrelated, failed, malformed and mismatched tool results cannot bind a session',async()=>{
 for(const [e,r] of [[{...exec,name:'untrusted'},result(body())],[exec,result(body('error'))],[exec,{isError:true,...result(body())}],[exec,result(body('ok',{binding:{...scope,task_id:'other'}}))],[exec,result({operation:'other'})]]){
  const {flow,links}=fixture();flow.observe(e,r);await tick();assert.equal(links.get(agent.id),undefined);
 }
});
test('reading another task never rebinds or triggers its approval',async()=>{
 let calls=0;const {flow,links}=fixture(async()=>{calls++;return {status:'ok'};});links.put(agent.id,scope);
 flow.observe({...exec,name:'mcp__nexusmore__task_status'},result(body('needs_user_input',{operation:'task_status',binding:{...scope,task_id:'q2'}})));
 await tick();assert.equal(calls,0);assert.equal(links.get(agent.id).task_id,'q1');
});
test('next question cannot silently change the inherited project',async()=>{
 const {flow,links}=fixture();links.put(agent.id,{project_id:'other'},'project');flow.observe(exec,result(body()));await tick();assert.equal(links.get(agent.id),undefined);assert.equal(flow.feedback.get(agent.id).state,'binding_conflict');
});
test('parallel review requests for the same task are coalesced',async()=>{
 let finish;const {flow,links}=fixture(()=>new Promise(r=>finish=r));links.put(agent.id,scope);
 const first=flow.run(agent);assert.deepEqual(await flow.run(agent),{status:'busy'});finish({status:'ok'});await first;
});
test('only a newly committed model approval resumes with a stable event-derived key and fresh binding',async()=>{
 const calls=[];const decision={decision:'approve',kind:'model',confirmed_binding:scope,event_reference:{event_id:'event-1'}};
 const {flow,links}=fixture(async()=>body('ok',{operation:'task_decide',data:{user_decision:decision}}),async(a,op,args,signal,extra)=>{
  calls.push({op,args,extra});return op==='task_status'?body('ok',{data:{task:{model_approved:true}}}):body('ok',{phase:'CODING_REQUIRED',pending:[]});
 });links.put(agent.id,scope);await flow.run(agent);
 assert.deepEqual(calls.map(x=>x.op),['task_status','task_status','task_resume']);assert.match(calls[2].extra.request_id,/^dsh-resume-[a-f0-9]+$/);assert.deepEqual(calls[2].extra.expected_binding,scope);
});
for(const [name,extra,mode] of [
 ['reject',{data:{user_decision:{decision:'reject',kind:'model'}}},'review'],
 ['result approval',{data:{user_decision:{decision:'approve',kind:'result'}}},'review'],
 ['replayed approval',{replayed:true,data:{user_decision:{decision:'approve',kind:'model'}}},'review'],
 ['unknown',{status:'outcome_unknown'},'review'],['status read',{data:{user_decision:{decision:'approve',kind:'model'}}},'status'],
 ['hand approval',{operation:'hand_decide',data:{user_decision:{decision:'approve',kind:'model'}}},'review']]){
 test(name+' never auto-resumes',async()=>{let calls=0;const {flow,links}=fixture(async()=>body('ok',extra),async()=>{calls++;return body('needs_user_input',{operation:'task_status'});});links.put(agent.id,scope);await flow.run(agent,mode);assert.equal(calls,mode==='status'?0:1);});
}
test('changed approval target and uncommitted approval block continuation',async()=>{
 for(const current of [body('ok',{binding:{...scope,version:2}}),body('ok',{data:{task:{model_approved:false}}})]){
  let calls=0;const {flow,links}=fixture(async()=>body('ok',{operation:'task_decide',data:{user_decision:{decision:'approve',kind:'model',confirmed_binding:scope}}}),async()=>{calls++;return current;});links.put(agent.id,scope);await assert.rejects(flow.run(agent));assert.equal(calls,2);
 }
});
test('closing the plugin aborts active questions and suppresses queued ones',async()=>{
 let aborted=false;const {flow,links}=fixture((a,s,m,signal)=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>{aborted=true;reject(Error('abort'));})));
 links.put(agent.id,scope);const pending=flow.run(agent);await tick();flow.close();await assert.rejects(pending);assert.equal(aborted,true);
});
test('browser bundle preserves native session provider and exposes no approval HTTP payload',()=>{
 const code=readFileSync(new URL('../../src/harness/nexusmore-dsh-client.js',import.meta.url),'utf8');
 assert.match(code,/SessionProvider/);assert.match(code,/sessions.retain/);assert.match(code,/conversation.content/);
 assert.doesNotMatch(code,/<iframe|actor\s*:|decision\s*:/);assert.match(code,/conversation.session.header.utilities/);
 assert.doesNotMatch(code,/conversation.session.header.corner/);
});

test('continuation uses an immutable host notice rather than a human signature',()=>{
 let delivered;continueAgent({followup:m=>delivered=m},{project_id:'p',task_id:'q1'});
 assert.equal(delivered.source.kind,'cordis-host-runner');assert.equal(Object.isFrozen(delivered.content[0]),true);
 assert.match(delivered.content[0].text,/task_status/);assert.doesNotMatch(JSON.stringify(delivered),/TEST_SIMULATED_USER|user_event/);
});
test('successful approval wakes once, while blocked, pending, unknown and cancelled resumes never wake',async()=>{
 for(const status of ['ok','error','outcome_unknown','needs_user_input']){
  let notified=0;
  const {flow,links}=fixture(async()=>body('ok',{operation:'task_decide',data:{user_decision:{decision:'approve',kind:'model',confirmed_binding:scope,event_reference:{event_id:'same-event'}}}}),
    async(a,op)=>op==='task_status'?body('ok',{data:{task:{model_approved:true}}}):body(status,{pending:status==='needs_user_input'?[{}]:[]}));
  flow.notify=()=>{notified++;};links.put(agent.id,scope);await flow.run(agent);await flow.run(agent);
  assert.equal(notified,status==='ok'?1:0);
 }
});
test('bound native sessions refuse cross-question mutations but allow material reads',()=>{
 const {links}=fixture();links.put(agent.id,scope);
 for(const operation of ['task_revise','task_restore','hand_start','task_resume'])assert.equal(admission(links,{agent,name:'mcp__nexusmore__'+operation,arguments:{arguments:{task_id:'q2'}}}).kind,'deny');
 assert.equal(admission(links,{agent,name:'mcp__nexusmore__task_status',arguments:{arguments:{task_id:'q2'}}}),undefined);
});

test('next-question navigation survives a new host instance without copying business state',()=>{
 const {links}=fixture();links.addChild(agent.id,'session-b','p');links.addChild(agent.id,'session-c','p');
 const restored=new SessionLinks(links.root.split('runs')[0]);assert.equal(restored.children(agent.id).length,2);
 assert.deepEqual(restored.children('session-b'),[]);assert.throws(()=>links.addChild(agent.id,agent.id,'p'));
 assert.equal(restored.get('session-b'),undefined);
});

test('real SOLVING envelopes with running status deliver the native continuation',async()=>{
 let notified=0;const decision={decision:'approve',kind:'model',confirmed_binding:scope,event_reference:{event_id:'running-event'}};
 const {flow,links}=fixture(async()=>body('running',{operation:'task_decide',phase:'SOLVING',pending:[],data:{user_decision:decision}}),
   async(a,op)=>body('running',{phase:'SOLVING',pending:[],data:{task:{model_approved:true}}}));
 flow.notify=()=>{notified++;};links.put(agent.id,scope);await flow.run(agent);assert.equal(notified,1);assert.equal(flow.feedback.get(agent.id).state,'continued');
});

test('optional browser registration failure disposes contributions without rejecting host boot',async()=>{
 let plugin,disposed=0,failed=false,registrations=0;
 const code=readFileSync(new URL('../../src/harness/nexusmore-dsh-client.js',import.meta.url),'utf8');
 runInNewContext(code,{window:{__ModuleLoader__:{load:entry=>{plugin=entry.factory(()=>({createElement:()=>{}}));}}},console:{error:()=>{failed=true;}}});
 const ctx={remote:{commands:{}},sidebarRightTabs:{register:()=>()=>{}},slots:{inject:()=>{if(++registrations===2)throw Error('SDK registration mismatch');return ()=>{};}},
   effect:setup=>{const dispose=()=>{disposed++;};dispose.then=(a,b)=>Promise.resolve().then(setup).then(a,b);return dispose;}};
 await plugin.apply(ctx);assert.equal(failed,true);assert.equal(disposed,3);
});

test('a new child cannot reuse a task already linked to its parent or another chat',()=>{
 const {links}=fixture();links.put(agent.id,scope);const child={id:'session-new-child'};links.put(child.id,{project_id:'p'},'project');
 assert.equal(admission(links,{agent:child,name:exec.name,arguments:exec.arguments}).kind,'deny');
 assert.throws(()=>links.put(child.id,scope));assert.equal(links.get(child.id),undefined);
});

test('native original text accepts only actual user RPC messages, never model or host notices',()=>{
 const user={id:'message-1',role:'user',source:{kind:'user',rpcId:'rpc-1'},content:[{type:'text',text:'mean of 2,4,6'}]};
 assert.equal(nativeText([user]).text,'mean of 2,4,6');
 for(const value of [{...user,role:'assistant'},{...user,source:{kind:'cordis-host-runner'}},{...user,source:{kind:'user'}}])assert.equal(nativeText([value]),undefined);
 assert.throws(()=>nativeText([{...user,content:[{type:'image'}]}]));
});
test('task creation waits for immutable trusted intake and uses its exact task owner',()=>{
 const {links}=fixture(),intake=new NativeIntake(links);
 assert.equal(admission(links,exec,intake).kind,'deny');
 intake.store(agent.id,'p',{status:'prepared',owner:{project_id:'p',task_id:'q1',version:1}});
 assert.equal(admission(links,exec,intake),undefined);
 assert.throws(()=>intake.store(agent.id,'other',{status:'prepared',owner:{project_id:'other',task_id:'q2'}}));
});
test('task creation and unready M1 cannot automatically open a model decision',async()=>{
 for(const reason of ['modeling_required','independent_m1_required','evidence_not_ready']){
  let reviews=0;const {links,flow}=fixture(async()=>{reviews++;});
  flow.observe(exec,result(body('needs_user_input',{data:{host_review:{model_ready:false,reason}}})));await tick();
  assert.equal(links.get(agent.id).task_id,'q1');assert.equal(reviews,0);assert.equal(flow.feedback.get(agent.id).state,'preparing_model');
 }
});
test('manual review also rechecks current readiness and refuses the stale ready projection',async()=>{
 let reviews=0;const {links,flow}=fixture(async()=>{reviews++;},async()=>body('needs_user_input',{operation:'task_status',data:{host_review:{model_ready:false}}}));
 links.put(agent.id,scope);assert.equal((await flow.run(agent)).status,'not_ready');assert.equal(reviews,0);
});
test('clarification collects facts separately and never submits or resumes a decision',async()=>{
 const notices=[],a={...agent,followup:x=>notices.push(x)};let reviews=0;
 const {links,flow}=fixture(async()=>{reviews++;},async()=>body('needs_user_input',{operation:'task_status',data:{host_review:{model_ready:false,open_questions:['missing unit?']}}}));
 links.put(a.id,scope);flow.clarify=async()=>[{question:'missing unit?',answer:'m'}];
 assert.equal((await flow.run(a)).status,'clarification_received');assert.equal(reviews,0);assert.equal(notices.length,1);
 assert.equal(notices[0].source.kind,'cordis-host-runner');assert.match(notices[0].content[0].text,/不是业务批准/);
});

test('each new native question receives its own user scratch cwd',async()=>{
 const paths=[],registry={resolveByPath:async()=>undefined,create:async path=>{paths.push(path);return {id:'workspace-'+paths.length,path};}};
 const a=await sandboxWorkspace({workspaceRegistry:registry},{cwd:'D:/synthetic-business'});
 const b=await sandboxWorkspace({workspaceRegistry:registry},{cwd:'D:/synthetic-business'});
 assert.notEqual(a.path,b.path);assert.match(a.path,/NexusMORE[\\/]dsh-workspaces[\\/]/);assert.notEqual(a.path,'D:/synthetic-business');
});
test('clarification for an older version cannot be delivered into a changed task',async()=>{
 let calls=0,notices=0;const a={...agent,followup:()=>{notices++;}};
 const {links,flow}=fixture(async()=>{throw Error('No decision allowed');},async()=>body('needs_user_input',{operation:'task_status',binding:{...scope,version:++calls===1?1:2},data:{host_review:{model_ready:false,open_questions:['missing unit?']}}}));
 links.put(a.id,scope);flow.clarify=async()=>[{answer:'m'}];await assert.rejects(flow.run(a));assert.equal(notices,0);
});

test('native sandbox diagnosis uses one fixed read and never exposes a command proxy',async()=>{
 let calls=0;const tools={execute:async input=>{calls++;assert.equal(input.agent,agent);assert.equal(input.calls[0].name,'pwsh');assert.equal(JSON.parse(input.calls[0].arguments).command,'$PSVersionTable.PSVersion.ToString()');return {results:[{result:{content:[{type:'text',text:'7.6.9\r\n'}]}}]};}};
 assert.equal((await probeSandbox(tools,agent,new AbortController().signal)).powershell_version,'7.6.9');assert.equal(calls,1);
 await assert.rejects(probeSandbox(tools,agent,AbortSignal.abort()));assert.equal(calls,1);
});

// Persistent native-chat review: files and ordinary user replies, no modal wait.
import {ChatReviewStore,isChatApproval,nativeFileLink,chatReplyAfterPreview} from '../../src/harness/nexusmore-dsh-conversation.mjs';
const human=(text,id='user-confirm')=>({id,role:'user',source:{kind:'user',rpcId:'rpc-'+id},content:[{type:'text',text}]});
function chatFixture(){
 const f=fixture();f.store=new ChatReviewStore(f.links);f.flow.store=f.store;f.links.put(agent.id,scope);
 f.notices=[];f.agent={id:agent.id,followup:m=>f.notices.push(m)};
 f.preview={renderer_version:'readable-model/1',status:'waiting_for_user',preview_id:'c'.repeat(64),title:'建模方案待审稿',binding:scope,local_path:'D:/synthetic/review.md',markdown:'# Test plan'};
 f.flow.prepare=async()=>f.preview;return f;
}
test('native draft publication returns immediately, persists and emits a file link without native questions',async()=>{
 const f=chatFixture();let cards=0;f.flow.review=()=>{cards++;};
 assert.equal((await f.flow.run(f.agent)).status,'waiting_for_user');
 assert.equal(cards,0);assert.equal(f.notices.length,1);assert.equal(f.flow.active.size,0);
 assert.match(f.notices[0].content[0].text,/dsh-resource:\/\/file\/session\//);
 assert.match(f.notices[0].content[0].text,/结束本轮/);assert.equal(f.store.read(f.agent.id).state,'waiting_for_user');
 assert.equal(new ChatReviewStore(f.links).read(f.agent.id).preview.preview_id,f.preview.preview_id);
 await f.flow.run(f.agent);assert.equal(f.notices.length,1);
});
test('only a genuine user RPC after the published document can confirm',()=>{
 const record={state:'waiting_for_user',notice_id:'host-notice',delivered:true},notice={id:'host-notice',role:'user',source:{kind:'cordis-host-runner'},content:[{type:'text',text:'file'}]};
 assert.equal(chatReplyAfterPreview([human('通过'),notice],record),undefined);
 assert.equal(chatReplyAfterPreview([notice,{...human('通过'),source:{kind:'cordis-host-runner'}}],record),undefined);
 assert.equal(chatReplyAfterPreview([notice,{...human('通过'),role:'assistant'}],record),undefined);
 assert.equal(chatReplyAfterPreview([notice,human('通过')],record),undefined);
 assert.equal(chatReplyAfterPreview([human('通过')],record).text,'通过');
 assert.equal(chatReplyAfterPreview([human('通过')],{...record,delivered:false}),undefined);
});
test('negative, conditional, quoted and mixed edit replies never count as approval',()=>{
 for(const text of ['通过','通过。','确认当前版本，继续'])assert.equal(isChatApproval(text),true);
 for(const text of ['不通过','是否通过？','“通过”','通过，但先修改','如果没问题就通过','好的','继续','通过\n调整一下'])assert.equal(isChatApproval(text),false);
 assert.match(nativeFileLink('session-test','C:\\User Files\\待审.md'),/^dsh-resource:\/\/file\/session\/session-test\/C:\/User%20Files\//);
});
test('a chat approval is claimed once before dispatch; duplicate pre-steps never resubmit',async()=>{
 const f=chatFixture();let accepts=0;f.flow.accept=async(a,s,id,msg)=>{accepts++;assert.equal(msg.text,'通过');return body('ok',{operation:'task_decide',data:{user_decision:{kind:'result',decision:'approve'}}});};
 await f.flow.run(f.agent);await f.flow.onUser(f.agent,[f.notices[0]],new AbortController().signal);const messages=[human('通过')];
 const confirmation=await f.flow.onUser(f.agent,messages,new AbortController().signal);
 assert.match(confirmation.content[0].text,/真实确认/);assert.equal(accepts,1);
 await f.flow.onUser(f.agent,messages,new AbortController().signal);assert.equal(accepts,1);
 assert.equal(f.store.read(f.agent.id).state,'confirmed');
});
test('discussion invalidates the old one-word confirmation until a draft is shown again',async()=>{
 const f=chatFixture();let accepts=0;f.flow.accept=()=>{accepts++;};await f.flow.run(f.agent);
 await f.flow.onUser(f.agent,[f.notices[0]],new AbortController().signal);
 await f.flow.onUser(f.agent,[human('第二条修改一下','edit')],new AbortController().signal);
 assert.equal(f.store.read(f.agent.id).state,'discussion');
 await f.flow.onUser(f.agent,[human('通过')],new AbortController().signal);assert.equal(accepts,0);
 await f.flow.run(f.agent);assert.equal(f.notices.length,2);assert.equal(f.store.read(f.agent.id).state,'waiting_for_user');
});
test('an uncertain chat submission stays fenced and is never automatically recaptured',async()=>{
 const f=chatFixture();let calls=0;f.flow.accept=async()=>{calls++;throw Error('connection lost');};await f.flow.run(f.agent);
 await f.flow.onUser(f.agent,[f.notices[0]],new AbortController().signal);
 const messages=[human('通过')];await f.flow.onUser(f.agent,messages,new AbortController().signal);
 assert.equal(f.store.read(f.agent.id).state,'confirmation_blocked');
 await f.flow.onUser(f.agent,messages,new AbortController().signal);assert.equal(calls,1);
});

test('draft anchors open the existing native file tab without web navigation or approval input',async()=>{
 let plugin,click,removed=false;const opened=[];
 const document={addEventListener:(name,fn,capture)=>{assert.equal(name,'click');assert.equal(capture,true);click=fn;},removeEventListener:()=>{removed=true;}};
 runInNewContext(readFileSync(new URL('../../src/harness/nexusmore-dsh-client.js',import.meta.url),'utf8'),
  {document,window:{__ModuleLoader__:{load:e=>plugin=e.factory(()=>({createElement:()=>{}}))}},console:{error:()=>{}}});
 const ctx={remote:{commands:{}},sidebarRight:{openResourceIn:(...args)=>opened.push(args)},
  sidebarRightTabs:{register:()=>()=>{}},slots:{inject:()=>()=>{}},effect:setup=>setup()};
 await plugin.apply(ctx);assert.equal(typeof click,'function');
 let prevented=0;const event=href=>({button:0,target:{closest:()=>({getAttribute:()=>href})},preventDefault:()=>{prevented++;},stopPropagation:()=>{}});
 click(event('https://example.test/file.md'));assert.equal(opened.length,0);
 const href='dsh-resource://file/session/session-native-test/D:/reviews/plan.md';click(event(href));
 assert.equal(prevented,1);assert.equal(opened.length,1);assert.equal(opened[0][0],'session-native-test');assert.equal(opened[0][1],href);
 assert.equal(removed,false);
});

test('canonical MCP receipts publish a registered draft even when rendered text is truncated',async()=>{
 const f=chatFixture();let prepares=0;f.flow.prepare=async()=>{prepares++;return f.preview;};
 const receipt=body('needs_user_input',{operation:'modeling_start'});
 const canonical={isError:false,content:[{type:'text',text:'{"contract_version":"1.0.0", "data": [truncated'}],value:{content:[],structuredContent:receipt}};
 assert.equal(decodeBusiness(canonical,'modeling_start'),receipt);
 f.flow.observe({...exec,agent:f.agent,name:'mcp__nexusmore__modeling_start'},canonical);await tick();await tick();
 assert.equal(prepares,1);assert.equal(f.notices.length,1);
 assert.equal(f.store.read(f.agent.id).preview.preview_id,f.preview.preview_id);
 assert.equal(f.store.read(f.agent.id).delivered,false);
 assert.equal(decodeBusiness({...canonical,value:{structuredContent:{...receipt,operation:'other'}}},'modeling_start'),undefined);
});

test('a busy publication retains the newest observed review and does not lose its dedupe key',async()=>{
 const f=chatFixture();let finish;const old= f.flow.call;
 f.flow.call=()=>new Promise(resolve=>finish=resolve);
 const busy=f.flow.run(f.agent);
 f.flow.observe({...exec,agent:f.agent,name:'mcp__nexusmore__modeling_start'},result(body('needs_user_input',{operation:'modeling_start'})));
 await tick();assert.equal(f.notices.length,0);
 f.flow.call=old;finish(body('needs_user_input',{operation:'task_status'}));await busy;await tick();await tick();
 assert.equal(f.notices.length,1);assert.equal(f.flow.queuedReviews.size,0);
});

test('publication failures are visible and the same ready receipt can recover',async()=>{
 const f=chatFixture();let attempts=0;
 f.flow.prepare=async()=>{if(++attempts===1)throw Error('worker failure');return f.preview;};
 const e={...exec,agent:f.agent,name:'mcp__nexusmore__modeling_start'},r=result(body('needs_user_input',{operation:'modeling_start'}));
 f.flow.observe(e,r);await tick();await tick();
 assert.equal(f.flow.feedback.get(f.agent.id).state,'publication_failed');assert.equal(f.store.read(f.agent.id),undefined);
 assert.match(f.notices[0].content[0].text,/尚未发布/);
 f.flow.observe(e,r);await tick();await tick();assert.equal(f.store.read(f.agent.id).state,'waiting_for_user');assert.equal(attempts,2);
});

test('a restored chat without a preview publishes first and never approves its earlier confirmation',async()=>{
 const f=chatFixture();let accepts=0;f.flow.accept=()=>{accepts++;};
 const first=human('确认你的三个口径 通过建模方案 进入代码手','before-preview');
 const notice=await f.flow.onUser(f.agent,[first],new AbortController().signal);
 assert.equal(accepts,0);assert.match(notice.content[0].text,/未登记为批准/);
 assert.equal(f.store.read(f.agent.id).after_message.id,first.id);
 await f.flow.onUser(f.agent,[f.notices[0]],new AbortController().signal);
 await f.flow.onUser(f.agent,[first],new AbortController().signal);assert.equal(accepts,0);
});

test('explicit model approvals accept complete sentences and reject edits, other scopes and mixed decisions',()=>{
 for(const text of ['确认你的三个口径 通过建模方案 进入代码手','通过建模方案，进入代码手','同意建模方案','我同意当前建模方案，请进入代码手阶段！','确认上述三项口径，通过模型方案。']){
  assert.equal(isChatApproval(text,'model'),true,text);
  for(const kind of ['result','manuscript','figures'])assert.equal(isChatApproval(text,kind),false,text);
 }
 for(const text of ['不同意建模方案','是否通过建模方案','同意建模方案吗？','通过建模方案，但先修改第二条','如果没有问题就通过建模方案','他说“通过建模方案”','通过建模方案，同时通过正文','确认三个口径\n通过建模方案','先不要通过建模方案','通过旧版建模方案'])assert.equal(isChatApproval(text,'model'),false,text);
});

test('ready result to displayed review to explicit user approval resumes exactly once',async()=>{
 const f=chatFixture(),calls=[];let accepts=0,committed=false;
 f.preview.kind='model';
 f.flow.call=async(a,op,args,signal,extra)=>{
  calls.push(op);
  if(op==='task_resume'){assert.equal(committed,true);assert.equal(extra.expected_binding.version,1);return body('running',{operation:op,phase:'SOLVING',pending:[]});}
  return body(committed?'running':'needs_user_input',{operation:op,pending:committed?[]:[{pending_id:'pending-1',kind:'model'}],data:{task:{model_approved:committed}}});
 };
 f.flow.accept=async(a,s,id,msg)=>{
  accepts++;assert.equal(id,f.preview.preview_id);assert.equal(msg.text,'确认你的三个口径 通过建模方案 进入代码手');committed=true;
  return body('running',{operation:'task_decide',pending:[],data:{user_decision:{kind:'model',decision:'approve',confirmed_binding:scope,event_reference:{event_id:'complete-flow'}}}});
 };
 f.flow.observe({...exec,agent:f.agent,name:'mcp__nexusmore__modeling_start'},result(body('needs_user_input',{operation:'modeling_start'})));await tick();await tick();
 assert.equal(f.store.read(f.agent.id).state,'waiting_for_user');assert.equal(accepts,0);
 await f.flow.onUser(f.agent,[f.notices[0]],new AbortController().signal);
 const message=human('确认你的三个口径 通过建模方案 进入代码手');
 const completed=await f.flow.onUser(f.agent,[message],new AbortController().signal);
 assert.match(completed.content[0].text,/真实确认/);assert.equal(f.store.read(f.agent.id).state,'confirmed');
 assert.equal(calls.filter(x=>x==='task_resume').length,1);assert.equal(accepts,1);
 await f.flow.onUser(f.agent,[message],new AbortController().signal);assert.equal(accepts,1);
});

test('an old machine-oriented model preview is replaced before accepting any new confirmation',async()=>{
 const f=chatFixture();f.preview.kind='model';let accepts=0;f.flow.accept=()=>{accepts++;};
 f.store.write(f.agent.id,{state:'waiting_for_user',delivered:true,notice_id:'old-notice',preview:{...f.preview,preview_id:'d'.repeat(64),renderer_version:undefined}});
 const message=human('通过','arrived-before-readable-draft');
 const response=await f.flow.onUser(f.agent,[message],new AbortController().signal);
 assert.match(response.content[0].text,/未登记为批准/);assert.equal(accepts,0);
 assert.equal(f.store.read(f.agent.id).preview.renderer_version,'readable-model/1');
 assert.equal(f.store.read(f.agent.id).delivered,false);
 assert.equal(f.store.read(f.agent.id).after_message.id,message.id);
});

test('combined paper publishes both scopes then consumes one fresh explicit confirmation',async()=>{
 const f=chatFixture();let accepts=0;
 f.preview={...f.preview,kind:'manuscript',renderer_version:'readable-paper-bundle/1',confirmation_scope:'manuscript_and_figures',title:'论文正文与配图合并待审稿'};
 f.flow.accept=async(a,s,id,message)=>{accepts++;assert.equal(message.text,'确认');assert.equal(id,f.preview.preview_id);return body('ok',{operation:'hand_decide',data:{user_decision:{kind:'manuscript',decision:'approve',confirmation_scope:'manuscript_and_figures'}}});};
 await f.flow.run(f.agent);assert.match(f.notices[0].content[0].text,/一次确认同时批准/);
 await f.flow.onUser(f.agent,[human('确认','early')],new AbortController().signal);assert.equal(accepts,0);
 await f.flow.onUser(f.agent,[f.notices[0]],new AbortController().signal);
 await f.flow.onUser(f.agent,[human('确认','fresh')],new AbortController().signal);assert.equal(accepts,1);
 await f.flow.onUser(f.agent,[human('确认','fresh')],new AbortController().signal);assert.equal(accepts,1);
 assert.equal(f.store.read(f.agent.id).state,'confirmed');
});
test('old choose-required accepts look-at-images or confirmation only to publish, never approve',async()=>{
 for(const text of ['看图','确认']){
 const f=chatFixture();let accepts=0;f.flow.accept=async()=>{accepts++;};
 f.preview={...f.preview,kind:'manuscript',renderer_version:'readable-paper-bundle/1',confirmation_scope:'manuscript_and_figures'};
 f.store.write(f.agent.id,{state:'choose_required'});
 await f.flow.onUser(f.agent,[human(text)],new AbortController().signal);
 assert.equal(accepts,0);assert.equal(f.store.read(f.agent.id).state,'waiting_for_user');assert.equal(f.store.read(f.agent.id).delivered,false);
 }
});

test('plain consent is captured only after delivery and is not treated as discussion',async()=>{
 const f=chatFixture();let calls=0;f.preview={...f.preview,kind:'manuscript',renderer_version:'readable-paper-bundle/1',confirmation_scope:'manuscript_and_figures'};
 f.flow.accept=async(a,s,id,message)=>{calls++;assert.equal(message.text,'同意');return body('ok',{operation:'hand_decide'});};
 assert.equal(isChatApproval('同意'),true);
 for(const text of ['不同意','是否同意？','同意，但先修改','如果没问题就同意','他说同意','“同意”'])assert.equal(isChatApproval(text),false);
 await f.flow.run(f.agent);await f.flow.onUser(f.agent,[f.notices[0]],new AbortController().signal);
 await f.flow.onUser(f.agent,[human('同意')],new AbortController().signal);
 assert.equal(calls,1);assert.equal(f.store.read(f.agent.id).state,'confirmed');
});
