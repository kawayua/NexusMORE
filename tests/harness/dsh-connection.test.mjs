import { Script } from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
import { apply, diagnose, decodeResult, registered, panelHtml, checkNativeUi } from '../../src/harness/nexusmore-dsh.mjs';
import { readFileSync } from 'node:fs';

const contract = JSON.parse(readFileSync(new URL('../../src/modelcrew/resources/contracts/business-tools-1.0.0.json', import.meta.url)));
const operations = contract.operations.filter(x => x.channel === 'model' && x.name !== 'figures_select').map(x => x.name).sort();
const names = operations.map(x => 'mcp__nexusmore__' + x);
const response = (operation, data, extras={}) => ({results:[{result:{content:[{type:'text',text:JSON.stringify({contract_version:'1.0.0',operation,status:'ok',data,...extras})}]}}]});

test('connection diagnosis invokes only fixed reads through the Host pipeline', async () => {
  const seen = [];
  const tools = { schemas: () => names.map(name => ({name})), async execute(input) {
    const call = input.calls[0]; seen.push(call);
    const args = JSON.parse(call.arguments);
    assert.deepEqual(Object.keys(args).sort(),['arguments','contract_version','operation']);
    assert.equal(call.name, 'mcp__nexusmore__'+args.operation);
    assert.equal(input.signal.aborted, false);
    return response(args.operation, args.operation === 'capabilities_read'
      ? {operations,trusted_capture_channels:['trusted_local_cli']}
      : [{id:'PRIVATE_PROJECT',title:'PRIVATE_TITLE'}]);
  }};
  const result = await diagnose(tools, new AbortController().signal);
  assert.equal(result.status,'passed');
  assert.deepEqual(seen.map(x=>x.name),['mcp__nexusmore__capabilities_read','mcp__nexusmore__projects_list']);
  assert.equal(result.calls[0].expected_tools_registered,true);
  assert.equal(result.calls[1].returned_project_count,1);
  assert.equal(result.user_decision_created,false);
  assert.equal(result.model_request_sent,false);
  assert.equal(JSON.stringify(result).includes('PRIVATE_'),false);
});

test('missing MCP registration never reports connected', async () => {
  const tools={schemas:()=>[],execute:()=>{throw new Error('must not call')}};
  const result=await diagnose(tools,new AbortController().signal);
  assert.equal(result.status,'failed');
  assert.equal(result.calls.every(x=>x.code==='tool_not_registered'),true);
});

test('host and business errors remain failures without raw diagnostic leakage',async()=>{
  for (const batch of [response('projects_list',null,{status:'error'}),{results:[{result:{isError:true,error:{message:'SECRET'},content:[]}}]}]) {
    const tools={schemas:()=>names.map(name=>({name})),execute:async()=>batch};
    const result=await diagnose(tools,new AbortController().signal);
    assert.equal(result.status,'failed');
    assert.equal(JSON.stringify(result).includes('SECRET'),false);
  }
});

test('route surface has no configurable tool proxy or approval route',()=>{
  const routes=[];
  apply({tools:{schemas:()=>[]},commands:{register:()=>{}},connection:{fetch:{register:route=>routes.push(route)}}});
  assert.deepEqual(routes.map(x=>[x.path,x.methods]),[
    ['/api/nexusmore/status',['GET']],['/api/nexusmore/diagnose',['POST']],['/api/nexusmore/panel',['GET']]]);
  assert.match(panelHtml(),/G3/);
  assert.equal(routes.every(x=>x.requestBody==='buffered'),true);
});

test('concurrent diagnosis shares one read batch and does not reissue writes',async()=>{
  const routes=[];let count=0;
  const tools={schemas:()=>names.map(name=>({name})),execute:async input=>{
    count++;await new Promise(resolve=>setTimeout(resolve,5));
    const operation=JSON.parse(input.calls[0].arguments).operation;
    return response(operation,operation==='capabilities_read'?{operations}:[]);
  }};
  apply({tools,commands:{register:()=>{}},connection:{fetch:{register:route=>routes.push(route)}}});
  const route=routes.find(x=>x.path.endsWith('/diagnose'));
  const [a,b]=await Promise.all([route.fetch(new Request('http://localhost/api/nexusmore/diagnose',{method:'POST'})),route.fetch(new Request('http://localhost/api/nexusmore/diagnose',{method:'POST'}))]);
  assert.equal((await a.json()).status,'passed');assert.equal((await b.json()).status,'passed');assert.equal(count,2);
});

test('malformed and unrelated output never counts as verified business response',()=>{
  for(const batch of [{},{results:[]},response('task_decide',{}),{results:[{result:{content:[{type:'text',text:'bad'}]}}]}]) {
    assert.equal(decodeResult(batch).status,'error');
  }
  assert.deepEqual(registered({schemas:()=>[{name:'another_tool'}]}),[]);
});

 test('wrong operation or incomplete capability list never passes',async()=>{
  for(const wrong of ['wrong-operation','incomplete-capabilities']) {
   const tools={schemas:()=>names.map(name=>({name})),execute:async input=>{
    const op=JSON.parse(input.calls[0].arguments).operation;
    if(op==='capabilities_read') return response(wrong==='wrong-operation'?'projects_list':op,{operations:operations.slice(0,39)});
    return response(op,[]);
   }};
   assert.equal((await diagnose(tools,new AbortController().signal)).status,'failed');
  }
 });

 test('human command is discoverable and never accepts tool parameters',async()=>{
  let command;
  apply({commands:{register:x=>{command=x}},tools:{schemas:()=>[]},connection:{fetch:{register:()=>{}}}});
  assert.equal(command.name,'nexusmore');
  assert.equal(command.recordInput,false);
  assert.equal((await command.handler({rawInput:' approve',signal:new AbortController().signal})).kind,'error');
 });

test('standalone panel script compiles as served HTML',()=>{ const script=panelHtml().match(/<script>([\s\S]*?)<\/script>/)[1]; assert.doesNotThrow(()=>new Script(script)); });


test('native probe uses the exact host agent and fixed synthetic content',async()=>{
 const agent={id:'TEST_ENGINEERING_AGENT'};let request;
 const result=await checkNativeUi({async ask(input){request=input;return {answers:[{id:input.questions[0].id,selected:['结束检查'],custom:'TEST_PRIVATE_TEXT'}]}}},agent,new AbortController().signal);
 assert.equal(request.agent,agent);assert.equal(request.questions.length,1);
 assert.match(request.questions[0].detail,/TEST_ENGINEERING_ONLY/);
 assert.equal(request.wait,undefined);assert.equal(request.questions[0].multiSelect,false);
 assert.equal(result.status,'passed');assert.equal(result.user_decision_created,false);
 assert.equal(result.business_decision_path_invoked,false);assert.equal(result.model_request_sent,false);
 assert.equal(JSON.stringify(result).includes('TEST_PRIVATE_TEXT'),false);
});

test('native explicit cancellation does not become successful approval',async()=>{
 const result=await checkNativeUi({async ask(q){return {answers:[{id:q.questions[0].id,selected:['取消检查']}]}}},{id:'TEST'},new AbortController().signal);
 assert.equal(result.status,'cancelled');assert.equal(result.user_decision_created,false);
});

test('native mismatches, skipped and freeform-only answers are rejected',async()=>{
 for(const kind of ['wrong-id','empty','freeform','multiple','unknown','wrong-shape']) {
  await assert.rejects(()=>checkNativeUi({async ask(q){const id=q.questions[0].id;return kind==='wrong-shape'?[]:{answers:kind==='empty'?[]:[{
   id:kind==='wrong-id'?'another-question':id,selected:kind==='freeform'?[]:kind==='multiple'?['结束检查','取消检查']:kind==='unknown'?['approve']:['结束检查'],custom:'TEST_SIMULATED_USER'}]}}},{id:'TEST'},new AbortController().signal));
 }
});

test('native close and timeout errors never escape as approval or raw diagnostics',async()=>{
 const commands=[];apply({commands:{register:x=>commands.push(x)},tools:{schemas:()=>[]},connection:{fetch:{register:()=>{}}},
  userQuestions:{ask:async()=>{throw new Error('PRIVATE_HOST_ERROR')}}});
 const command=commands.find(x=>x.name==='nexusmore-ui-check');assert.equal(command.recordInput,false);
 const result=await command.handler({agent:{id:'TEST'},rawInput:'',signal:new AbortController().signal});
 assert.equal(result.kind,'error');assert.equal(result.text.includes('PRIVATE_HOST_ERROR'),false);
});

test('native command rejects parameters before asking and registers no model tool',async()=>{
 const commands=[];let called=false;apply({commands:{register:x=>commands.push(x)},tools:{schemas:()=>[],register:()=>{throw new Error('No extra model tools')}},connection:{fetch:{register:()=>{}}},userQuestions:{ask:async()=>{called=true}}});
 const command=commands.find(x=>x.name==='nexusmore-ui-check');
 assert.equal((await command.handler({rawInput:' approve',signal:new AbortController().signal})).kind,'error');assert.equal(called,false);
});

test('native abort and missing session prevent the request',async()=>{
 let called=false;const service={ask:async()=>{called=true}};const signal=AbortSignal.abort();
 await assert.rejects(()=>checkNativeUi(service,{id:'TEST'},signal));
 await assert.rejects(()=>checkNativeUi(service,undefined,new AbortController().signal));assert.equal(called,false);
});

test('abort during native answer prevents a passed result',async()=>{
 const ac=new AbortController();await assert.rejects(()=>checkNativeUi({async ask(q){ac.abort();return {answers:[{id:q.questions[0].id,selected:['结束检查']}]}}},{id:'TEST'},ac.signal));
});


test('engineering status reports native result without exposing answers',async()=>{
 const routes=[],commands=[];apply({commands:{register:x=>commands.push(x)},tools:{schemas:()=>[]},connection:{fetch:{register:x=>routes.push(x)}},
  userQuestions:{async ask(q){return {answers:[{id:q.questions[0].id,selected:['结束检查'],custom:'PRIVATE_ANSWER'}]}}}});
 const route=routes.find(x=>x.path.endsWith('/status'));
 assert.equal((await route.fetch().json()).native_ui_check.status,'not_run');
 await commands.find(x=>x.name==='nexusmore-ui-check').handler({agent:{id:'TEST'},rawInput:'',signal:new AbortController().signal});
 const body=await route.fetch().json();assert.equal(body.native_ui_check.status,'passed');
 assert.equal(body.user_decisions,'trusted_local_cli_and_dsh_native');assert.equal(JSON.stringify(body).includes('PRIVATE_ANSWER'),false);
});
