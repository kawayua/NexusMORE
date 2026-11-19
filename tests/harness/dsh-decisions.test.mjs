import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough, Writable } from 'node:stream';
import { parseScope,backendConfiguration,validateBackend,runNativeReview,registerDecisions,PROTOCOL } from '../../src/harness/nexusmore-dsh-decisions.mjs';

const backend={command:process.execPath,cwd:process.cwd()};
const scope={project_id:'TEST_PROJECT',task_id:'TEST_TASK'};
const configuration={transport:'stdio',serverName:'nexusmore',command:backend.command,cwd:backend.cwd,args:['-m','modelcrew.workflow_mcp'],env:{MODELCREW_WORKSPACE:backend.cwd}};

test('native scope accepts only explicit identifiers, never approval or identity',()=>{
 assert.deepEqual(parseScope('--project p --task t --run r'),{project_id:'p',task_id:'t',run_id:'r'});
 assert.deepEqual(parseScope('--project p --build b'),{project_id:'p',build_id:'b'});
 for(const raw of ['', '--project p','--project p --task t --build b','--project p --task t --actor user',
  '--project p --task ../x','--project p --task t --task t','--project p --task t toString x','--project p --build b --run r'])assert.throws(()=>parseScope(raw));
});

test('backend is read only from the single installed managed MCP entry',()=>{
 const ctx={configEditor:{entries:()=>[{options:{id:'nexusmore-workflow',name:'@deepseek-ai/dsh-mcp-client',config:configuration}}]}};
 assert.deepEqual(backendConfiguration(ctx),backend);
 for(const changed of [{...configuration,args:['-c','arbitrary']},{...configuration,transport:'http'},{...configuration,command:'python'},
  {...configuration,env:{MODELCREW_WORKSPACE:'relative'}}])assert.throws(()=>validateBackend(changed));
 assert.throws(()=>backendConfiguration({configEditor:{entries:()=>[]}}));
});

function worker(onInput) {
 const child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();child.killed=false;
 child.emitFrame=x=>child.stdout.write(JSON.stringify(x)+'\n');
 child.stdin=new Writable({write(chunk,encoding,done){try{onInput(JSON.parse(chunk.toString()),child);done()}catch(e){done(e)}}});
 child.kill=()=>{child.killed=true;child.stdout.end();return true};return child;
}

test('native reply reaches only private worker; exact live agent and fixed module are retained',async()=>{
 let child,launch,asked=0;const seen=[];const agent={id:'TEST_ENGINEERING_AGENT'};
 const result=await runNativeReview({agent,scope,backend,signal:new AbortController().signal,
  spawnWorker:(...args)=>{launch=args;child=worker((frame,c)=>{
   seen.push(frame);
   if(frame.protocol)c.emitFrame({type:'questions',frame_id:'a'.repeat(64),questions:[{id:'native-bound-id',question:'TEST_ENGINEERING_ONLY',options:[{label:'reject'}]}]});
   else if(frame.type==='answer')c.emitFrame({type:'captured',request_sha256:'b'.repeat(64)});
   else if(frame.type==='submit')c.emitFrame({type:'result',result:{status:'ok',TEST_SIMULATED_USER:true}});
  });return child},
  userQuestions:{async ask(input){asked++;assert.equal(input.agent,agent);assert.equal(input.wait,undefined);return {answers:[{id:input.questions[0].id,selected:['reject']}]}}}});
 assert.equal(result.status,'ok');assert.equal(asked,1);assert.equal(child.killed,true);
 assert.equal(launch[0],backend.command);assert.deepEqual(launch[1],['-m','modelcrew.dsh_decisions','--private-stdio']);
 assert.equal(launch[2].shell,false);assert.equal(launch[2].windowsHide,true);
 assert.equal(launch[2].env.MODELCREW_WORKSPACE,backend.cwd);
 assert.equal(seen[0].protocol,PROTOCOL);assert.equal(seen[0].host.pid,process.pid);
 assert.deepEqual(seen.map(x=>x.type??'init'),['init','answer','submit']);
});

test('native cancellation terminates worker without submission',async()=>{
 let child;const sent=[];await assert.rejects(()=>runNativeReview({agent:{id:'TEST'},scope,backend,signal:new AbortController().signal,
  spawnWorker:()=>child=worker((f,c)=>{sent.push(f);c.emitFrame({type:'questions',frame_id:'a'.repeat(64),questions:[{id:'q'}]})}),
  userQuestions:{async ask(){throw new Error('ASK_CANCELLED')}}}));
 assert.equal(child.killed,true);assert.equal(sent.length,1);
});

test('status is read only and never asks questions or submits',async()=>{
 const sent=[];const result=await runNativeReview({agent:{id:'TEST'},scope,backend,mode:'status',signal:new AbortController().signal,
  spawnWorker:()=>worker((f,c)=>{sent.push(f);c.emitFrame({type:'result',result:{status:'ok',dispatch_performed:false,captures:[]}})}),
  userQuestions:{ask(){throw Error('No question in status')}}});
 assert.equal(result.dispatch_performed,false);assert.equal(sent.length,1);assert.equal(sent[0].mode,'status');
});

test('unexpected worker frames never dispatch or expose stderr',async()=>{
 for(const response of [{type:'error',code:'untrusted_user_event'},{type:'questions',frame_id:'wrong',questions:[]},{type:'captured',request_sha256:'wrong'}]) {
  const sent=[];await assert.rejects(()=>runNativeReview({agent:{id:'TEST'},scope,backend,signal:new AbortController().signal,
   spawnWorker:()=>worker((f,c)=>{sent.push(f);c.stderr.write('PRIVATE_DSN');c.emitFrame(response)}),userQuestions:{ask(){throw Error('No native call')}}}));
  assert.equal(sent.length,1);
 }
});

test('abort before capture starts no worker',async()=>{
 await assert.rejects(()=>runNativeReview({agent:{id:'TEST'},scope,backend,signal:AbortSignal.abort(),spawnWorker(){throw Error('Must not spawn')}}));
});

test('abort after native reply prevents submit acknowledgement',async()=>{
 const ac=new AbortController();const sent=[];await assert.rejects(()=>runNativeReview({agent:{id:'TEST'},scope,backend,signal:ac.signal,
  spawnWorker:()=>worker((f,c)=>{sent.push(f);c.emitFrame({type:'questions',frame_id:'a'.repeat(64),questions:[{id:'q'}]})}),
  userQuestions:{async ask(){ac.abort();return {answers:[{id:'q',selected:['approve']}]}}}}));
 assert.equal(sent.length,1);
});

test('registration adds only human commands; parameters cannot carry decisions',async()=>{
 const commands=[];registerDecisions({commands:{register:c=>commands.push(c)}});
 assert.deepEqual(commands.map(x=>x.name),['nexusmore-review','nexusmore-review-status']);
 assert.equal(commands.every(x=>x.recordInput===false),true);
 assert.equal((await commands[0].handler({rawInput:'--project p --task t --decision approve'})).kind,'error');
});

import {runChatReview} from '../../src/harness/nexusmore-dsh-decisions.mjs';
test('chat preview is one fixed short private operation with no human question or submit frame',async()=>{
 let launch;const inputs=[];
 const result=await runChatReview({agent:{id:'TEST_CHAT'},scope,backend,mode:'preview',payload:{after_message:null,kind:null},signal:new AbortController().signal,
  spawnWorker:(...args)=>{launch=args;return worker((f,c)=>{inputs.push(f);c.emitFrame({type:'result',result:{status:'waiting_for_user',local_path:'test.md'}});});}});
 assert.equal(result.status,'waiting_for_user');assert.equal(inputs.length,1);
 assert.deepEqual(launch[1],['-m','modelcrew.dsh_chat','--private-stdio']);assert.equal(inputs[0].host.pid,process.pid);
 assert.equal(launch[2].windowsHide,true);assert.equal(launch[2].shell,false);
});
test('chat bridge refuses question frames and is abortable without spawning',async()=>{
 await assert.rejects(runChatReview({agent:{id:'TEST_CHAT'},scope,backend,mode:'confirm',payload:{},signal:AbortSignal.abort(),spawnWorker(){throw Error('no spawn');}}));
 await assert.rejects(runChatReview({agent:{id:'TEST_CHAT'},scope,backend,mode:'preview',payload:{},signal:new AbortController().signal,
  spawnWorker:()=>worker((f,c)=>c.emitFrame({type:'questions',questions:[]}))}));
});
