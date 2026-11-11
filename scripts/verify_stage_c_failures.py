"""C6 real workflow/MCP/Docker failures. No real user decisions or contest solves."""
import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
import anyio
import psycopg
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
from modelcrew.config import ROOT,database_url
from modelcrew.contracts import digest
from modelcrew.docker_executor import DockerExecutor,ExecutorError,register_job,sha,read,atomic
from modelcrew.mcp_client import McpClient,McpTransportError
from modelcrew.workflow import Workflow,WorkflowError
from scripts.c5_fixture import CODE,contract_for


class FaultClient(McpClient):
    def __init__(self,root,folder,mode):super().__init__(database_url=database_url());self.root=root;self.folder=folder;self.mode=mode
    async def _call(self,service,tool,arguments):
        if service!='code-executor':return await super()._call(service,tool,arguments)
        marker=self.folder/(self.mode+'.json')
        params=StdioServerParameters(command=sys.executable,args=['-m','scripts.c6_fault_server','--root',str(self.root),'--mode',self.mode,'--marker',str(marker)],cwd=str(ROOT),env={'PYTHONIOENCODING':'utf-8','MODELCREW_DATABASE_URL':self.database_url})
        with (self.folder/(self.mode+'-stderr.log')).open('a',encoding='utf-8') as stderr:
            async with stdio_client(params,errlog=stderr) as (read_stream,write):
                async with ClientSession(read_stream,write,read_timeout_seconds=timedelta(seconds=50)) as session:
                    await session.initialize()
                    response=await session.call_tool(tool,arguments)
                    return response.structuredContent


class LostAckClient(McpClient):
    def call(self,service,tool,arguments):
        value=super().call(service,tool,arguments)
        if tool=='code_execute':raise McpTransportError('TEST_C6 response lost after actual server completion')
        return value


def verify(folder):
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=False)
    root=folder/'executor';old_root=os.environ.get('MODELCREW_EXECUTION_ROOT');os.environ['MODELCREW_EXECUTION_ROOT']=str(root)
    checks=[];cases=[];jobs=[];forced_cleanup=[];failures=[]
    def check(name,passed,**extra):
        checks.append({'id':name,'passed':bool(passed),**extra})
        print(json.dumps({'check':name,'passed':bool(passed)}),flush=True)
    def task_case(name,code=CODE,limits=None,client=None):
        case_folder=folder/name;case_folder.mkdir();data=case_folder/'numbers.json';data.write_text('[1,2,3]')
        script=case_folder/'solver.py';script.write_text(code,encoding='utf-8');contract=contract_for(data)
        task='test-c6-'+name+'-'+uuid.uuid4().hex[:12];job_id='c6-'+uuid.uuid4().hex
        job=register_job(root,job_id,script,[{'name':'numbers.json','input_id':'numbers','path':str(data),'sha256':sha(data.read_bytes())}],{'mode':'workflow','task_id':task,'version':1,'contract_sha256':digest(contract)},limits)
        jobs.append(job);cases.append({'name':name,'task_id':task,'job_id':job_id,'code_sha256':job['code_sha256']})
        with Workflow(mcp_client=client) as w:w.create(task,contract,project='c6-fault-verification',executor_key='mcp-code-executor',executor_config={'job_id':job_id,'job_sha256':job['job_sha256']})
        return task,job,contract,case_folder
    def approve(task,client=None):
        with Workflow(mcp_client=client) as w:
            return w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id='model-approval',reason='TEST ONLY fixed fixture decision, not real approval')
    def expect_error(fn):
        try:fn();return None
        except Exception as exc:return {'type':type(exc).__name__,'message':str(exc)}
    def evidence(task):
        with Workflow() as w:
            state=w.inspect(task);tools=w.tool_evidence(task)
            return state,tools
    def dispatch_count(tools):return sum(t['tool']=='code_execute' and t['phase']=='started' for t in tools['mcp_traces'])
    def wait_resume(task,seconds=35):
        deadline=time.monotonic()+seconds;last=None
        while time.monotonic()<deadline:
            with Workflow() as w:
                try:return w.resume(task)
                except Exception as exc:last=exc
            time.sleep(.3)
        raise last or RuntimeError('Recovery deadline exceeded')
    def run(name,fn):
        try:fn()
        except Exception as exc:
            failures.append({'case':name,'type':type(exc).__name__,'message':str(exc)})
            check(name+'_unexpected_exception',False,error=str(exc))
    with Workflow() as w:
        w.setup();formal_before=w.db.execute('SELECT current_version,phase,execution_id,result_approved FROM mc_tasks WHERE id=%s',('dragon-q1',)).fetchone()
    try:
        def missing_index():
            case_folder=folder/'missing-index';case_folder.mkdir();data=case_folder/'numbers.json';data.write_text('[1,2,3]');task='test-c6-retrieval-'+uuid.uuid4().hex
            with Workflow() as w:w.create(task,contract_for(data),project='c6-fault-verification')
            old=os.environ.get('MODELCREW_RETRIEVAL_CONFIG');os.environ['MODELCREW_RETRIEVAL_CONFIG']=str(case_folder/'missing.json')
            try:
                with Workflow() as w:
                    value=w.retrieve_references(task,version=1,tool='paper_search',arguments={'query':'generic reference'},actor='TEST_MODEL_STUB',request_id='missing-index')
                    check('missing_index_returns_explicit_error_not_empty_evidence',value['envelope']['status']=='error' and value['envelope']['error']['code']=='retrieval_unavailable' and not w.task(task)['model_approved'])
            finally:
                if old is None:os.environ.pop('MODELCREW_RETRIEVAL_CONFIG',None)
                else:os.environ['MODELCREW_RETRIEVAL_CONFIG']=old
            with Workflow() as w:
                value=w.retrieve_references(task,version=1,tool='web_read',arguments={'url':'https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.brentq.html'},actor='TEST_MODEL_STUB',request_id='restored-reference')
                check('retrieval_recovers_new_request_without_approval',value['envelope']['status']=='ok' and bool(w.tool_evidence(task)['references']) and not w.task(task)['model_approved'])
        run('missing_index',missing_index)

        def image_failure():
            task,job,_,_=task_case('missing-image');old=os.environ.get('MODELCREW_EXECUTION_IMAGE');os.environ['MODELCREW_EXECUTION_IMAGE']='modelcrew-c6-absent:'+uuid.uuid4().hex
            try:error=expect_error(lambda:approve(task))
            finally:
                if old is None:os.environ.pop('MODELCREW_EXECUTION_IMAGE',None)
                else:os.environ['MODELCREW_EXECUTION_IMAGE']=old
            state,tools=evidence(task)
            check('missing_image_is_infrastructure_failure_without_container',error and state['task']['phase']=='SOLVING' and state['execution'] is None and not (root/'runs'/job['job_id']).exists())
            with Workflow() as w:error=expect_error(lambda:w.resume(task))
            state,tools=evidence(task)
            check('ambiguous_unstarted_operation_does_not_auto_redispatch',error and dispatch_count(tools)==1 and any(t['tool']=='code_execution_status' for t in tools['mcp_traces']) and state['result'] is None)
        run('missing_image',image_failure)

        def completed_ack():
            task,job,_,_=task_case('lost-ack');error=expect_error(lambda:approve(task,LostAckClient()))
            state,tools=evidence(task)
            check('completed_server_response_loss_keeps_unknown_not_success',error and state['task']['phase']=='SOLVING' and state['result'] is None)
            state=wait_resume(task);_,tools=evidence(task)
            check('lost_response_recovers_via_status_once',state['task']['phase']=='WAITING_RESULT_APPROVAL' and dispatch_count(tools)==1 and not state['task']['result_approved'])
        run('completed_ack',completed_ack)

        def real_process_exit():
            case_folder=folder/'running-fault';case_folder.mkdir()
            task,job,_,_=task_case('running-exit',"import time\ntime.sleep(5)\n"+CODE,{'timeout_s':12})
            client=FaultClient(root,case_folder,'exit_running');error=expect_error(lambda:approve(task,client))
            check('actual_mcp_process_exits_while_container_running',error and (case_folder/'exit_running.json').exists())
            state=wait_resume(task);_,tools=evidence(task)
            result=DockerExecutor(root).status(job['job_id'])
            check('new_mcp_process_recovers_orphan_without_new_dispatch',state['task']['phase']=='WAITING_RESULT_APPROVAL' and dispatch_count(tools)==1 and result['status']=='succeeded' and result['cleanup']['removed'])
        run('real_process_exit',real_process_exit)

        def cleanup_failure():
            case_folder=folder/'cleanup-fault';case_folder.mkdir();task,job,_,_=task_case('cleanup')
            error=expect_error(lambda:approve(task,FaultClient(root,case_folder,'cleanup_fail')))
            run_folder=root/'runs'/job['job_id'];state,_=evidence(task)
            check('cleanup_error_leaves_pending_receipt_not_published_result',error and (run_folder/'pending-result.json').exists() and not (run_folder/'result.json').exists() and state['result'] is None)
            state=wait_resume(task);_,tools=evidence(task)
            result=DockerExecutor(root).status(job['job_id'])
            check('status_finishes_cleanup_then_publishes_same_run',state['task']['phase']=='WAITING_RESULT_APPROVAL' and result['cleanup']['removed'] and dispatch_count(tools)==1)
        run('cleanup_failure',cleanup_failure)

        def deadline_recovery():
            case_folder=folder/'deadline-fault';case_folder.mkdir()
            # Stop container PID1 supervisor from inside its isolated namespace. Host unaffected.
            code="import os,signal,time\nos.kill(1,signal.SIGSTOP)\nwhile True: time.sleep(1)\n"
            task,job,_,_=task_case('deadline',code,{'timeout_s':1})
            error=expect_error(lambda:approve(task,FaultClient(root,case_folder,'exit_running')))
            check('deadline_case_monitor_really_exited',error and (case_folder/'exit_running.json').exists())
            deadline=time.monotonic()+35;result=None
            while time.monotonic()<deadline:
                result=DockerExecutor(root).status(job['job_id'])
                if result['status']!='running':break
                time.sleep(.3)
            check('orphan_deadline_terminates_stopped_supervisor_and_cleans',result and result['status']=='timeout' and result['cleanup']['removed'])
            with Workflow() as w:error=expect_error(lambda:w.resume(task))
            state,tools=evidence(task)
            check('timeout_routes_to_code_failure_without_result_or_approval',error and state['result'] is None and not state['task']['result_approved'] and state['execution_attempts'][-1]['payload']['failure_domain']=='code' and dispatch_count(tools)==1)
        run('deadline_recovery',deadline_recovery)

        def missing_container():
            case_folder=folder/'missing-container-fault';case_folder.mkdir()
            task,job,_,_=task_case('missing-container',"import time\ntime.sleep(10)\n"+CODE,{'timeout_s':15})
            error=expect_error(lambda:approve(task,FaultClient(root,case_folder,'exit_running')))
            engine=DockerExecutor(root);claim=read(root/'runs'/job['job_id']/'claim.json')
            info=engine.inspect(claim['container_name'],job)
            if info is None:raise RuntimeError('Expected isolated test container missing before disappearance injection')
            engine.docker('rm','-f',claim['container_name'])
            with Workflow() as w:error=expect_error(lambda:w.resume(task))
            state,tools=evidence(task)
            check('vanished_container_stays_unknown_without_redispatch',error and 'outcome_unknown' in error['message'] and state['execution'] is None and dispatch_count(tools)==1 and not state['task']['result_approved'])
        run('missing_container',missing_container)

        def syntax_failure():
            task,job,_,_=task_case('syntax','def broken(:\n')
            error=expect_error(lambda:approve(task));state,tools=evidence(task)
            check('syntax_error_preserves_gate_and_code_failure_domain',error and state['execution'] is None and state['task']['phase']=='SOLVING' and state['execution_attempts'][-1]['payload']['failure_domain']=='code' and DockerExecutor(root).status(job['job_id'])['cleanup']['removed'])
        run('syntax_failure',syntax_failure)

        def result_corruption():
            task,job,_,_=task_case('artifact-corruption',CODE.replace("{'total':sum(x*x for x in values)}", "{'total':sum(x*x for x in values),'test_nonce':'"+uuid.uuid4().hex+"'}"))
            state=approve(task);artifact=state['execution']['artifacts'][0];path=(ROOT/artifact['path']).resolve()
            if not path.is_relative_to((ROOT/'artifacts').resolve()):raise RuntimeError('Unexpected snapshot location')
            # Unique nonce ensures this corruption cannot affect another task's shared snapshot.
            saved=path.read_bytes();path.write_bytes(saved+b'corrupted')
            try:
                with Workflow() as w:
                    error=expect_error(lambda:w.action(task,version=1,kind='result',decision='approve',result_revision=1,actor='TEST_SIMULATED_USER',request_id='result',reason='TEST corruption must block this fixture confirmation'))
                    check('corrupt_snapshot_blocks_even_explicit_result_confirmation',error and 'artifacts changed' in error['message'] and not w.task(task)['result_approved'])
            finally:path.write_bytes(saved)
            # Corrupt executor original after immutable DB snapshot, then status must fail.
            original=root/read(root/'runs'/job['job_id']/'result.json')['artifacts'][0]['path'];raw=original.read_bytes();original.write_bytes(raw+b'tampered')
            try:
                error=expect_error(lambda:DockerExecutor(root).status(job['job_id']))
                check('executor_archive_hash_mismatch_is_not_reexecuted',error and error['type']=='ExecutorError')
            finally:original.write_bytes(raw)
        run('result_corruption',result_corruption)

        def db_connection_failure():
            task,job,_,_=task_case('database-connection')
            with Workflow() as w:
                error=expect_error(lambda:w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id='model-approval',crash_after_commit=True))
                pid=w.db.info.backend_pid
                with psycopg.connect(database_url(),autocommit=True) as control:
                    control.execute('SELECT pg_terminate_backend(%s)',(pid,))
                dead=expect_error(lambda:w.task(task))
            state=wait_resume(task)
            check('terminated_own_db_connection_recovers_committed_gate',error and dead and state['task']['phase']=='WAITING_RESULT_APPROVAL' and not state['task']['result_approved'])
            with Workflow() as w:
                before=w.inspect(task)['execution']['id'];w.saver.delete_thread(w.task(task)['thread_id']);state=w.resume(task)
                check('deleted_test_checkpoint_rebuilt_without_new_execution',state['execution']['id']==before and state['task']['phase']=='WAITING_RESULT_APPROVAL')
        run('db_connection_failure',db_connection_failure)

        def pending_receipt_tamper():
            case_folder=folder/'pending-tamper-fault';case_folder.mkdir();task,job,_,_=task_case('pending-tamper')
            expect_error(lambda:approve(task,FaultClient(root,case_folder,'cleanup_fail')))
            pending=root/'runs'/job['job_id']/'pending-result.json';original=read(pending);changed=dict(original);changed['job_sha256']='0'*64;atomic(pending,changed)
            try:
                error=expect_error(lambda:DockerExecutor(root).status(job['job_id']))
                check('pending_receipt_wrong_job_blocks_publication',error and 'differs from registered' in error['message'] and not (pending.parent/'result.json').exists())
            finally:atomic(pending,original)
            state=wait_resume(task)
            check('restored_pending_receipt_recovers_without_new_dispatch',state['task']['phase']=='WAITING_RESULT_APPROVAL' and dispatch_count(evidence(task)[1])==1)
        run('pending_receipt_tamper',pending_receipt_tamper)
    finally:
        # Only containers whose claims and immutable job hashes belong to this new directory.
        for job in jobs:
            claim_path=root/'runs'/job['job_id']/'claim.json'
            if not claim_path.exists():continue
            try:
                claim=read(claim_path);engine=DockerExecutor(root)
                if claim['job_sha256']!=job['job_sha256']:raise RuntimeError('Cleanup claim mismatch')
                if engine.inspect(claim['container_name'],job) is not None:
                    engine.docker('rm','-f',claim['container_name']);forced_cleanup.append(claim['container_name'])
            except Exception as exc:failures.append({'case':'final_cleanup','message':str(exc)})
        check('no_owned_execution_container_left',not forced_cleanup and not any(f['case']=='final_cleanup' for f in failures),forced_cleanup=forced_cleanup)
        with Workflow() as w:
            after=w.db.execute('SELECT current_version,phase,execution_id,result_approved FROM mc_tasks WHERE id=%s',('dragon-q1',)).fetchone()
            check('formal_task_unchanged',formal_before==after)
            for case in cases:
                dossier=w.version_dossier(case['task_id']);(folder/(case['name']+'-dossier.json')).write_text(json.dumps(dossier,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            check('all_failure_tasks_remain_without_result_approval',all(not w.task(c['task_id'])['result_approved'] for c in cases))
        if old_root is None:os.environ.pop('MODELCREW_EXECUTION_ROOT',None)
        else:os.environ['MODELCREW_EXECUTION_ROOT']=old_root
    report={'timestamp':datetime.now(timezone.utc).isoformat(),'status':'passed' if all(c['passed'] for c in checks) and not failures else 'failed',
            'checks':checks,'cases':cases,'failures':failures,'new_llm_calls':0,'new_formal_solves':0,'new_real_user_approvals':0,
            'fault_methods':{'running_mcp_exit':'real os._exit in test-only server after Docker inspect confirms Running',
                             'cleanup_failure':'injected Docker rm call failure; real pending receipt/container recovery',
                             'lost_ack':'drop actual completed MCP response in client',
                             'database':'terminate only this test Workflow connection, not shared PostgreSQL service',
                             'deadline':'test code SIGSTOPs its own container PID1; status recovery enforces deadline'},
            'stage_C_user_acceptance':False,'stage_D_started':False}
    (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(checks),'passed':sum(c['passed'] for c in checks),'cases':len(cases),'failures':failures}),flush=True)
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'stage-c/runs'/('c6-faults-'+datetime.now().strftime('%Y%m%dT%H%M%S%f')))
    verify(parser.parse_args().output)
