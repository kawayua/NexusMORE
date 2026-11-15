"""C5 real MCP + BGE/Qdrant + Docker + PostgreSQL/checkpointer verification.

All decisions below are explicitly TEST_SIMULATED_USER fixtures, never real approvals.
"""
from modelcrew.project_assets import asset_path
import argparse
import json
import os
import uuid
from datetime import datetime,timezone
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.docker_executor import DockerExecutor,register_job,sha
from modelcrew.workflow import Workflow,WorkflowError
from scripts.c5_fixture import contract_for,CODE


def verify(folder):
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=False)
    execution=folder/'executor';old_root=os.environ.get('MODELCREW_EXECUTION_ROOT')
    os.environ['MODELCREW_EXECUTION_ROOT']=str(execution)
    task='test-c5-real-'+uuid.uuid4().hex;job_id='c5-'+uuid.uuid4().hex
    checks=[];evidence={};failure=None
    def check(identifier,passed,**details):checks.append({'id':identifier,'passed':bool(passed),**details})
    def save(name,value):(folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    try:
        data=folder/'numbers.json';data.write_text('[1,2,3]',encoding='utf-8')
        code=folder/'solver.py';code.write_text(CODE,encoding='utf-8');contract=contract_for(data);save('contract.json',contract)
        job=register_job(execution,job_id,code,[{'input_id':'numbers','name':'numbers.json','path':str(data),'sha256':sha(data.read_bytes())}],
                         {'mode':'workflow','task_id':task,'version':1,'contract_sha256':digest(contract)})
        with Workflow() as w:
            w.setup()
            formal_before=w.db.execute('SELECT current_version,phase,model_approved,result_approved,execution_id FROM mc_tasks WHERE id=%s',('dragon-q1',)).fetchone()
            w.create(task,contract,project='c5-engineering-verification',executor_key='mcp-code-executor',executor_config={'job_id':job_id,'job_sha256':job['job_sha256']})
            check('no_execution_before_model_approval',not (execution/'runs'/job_id).exists() and not w.task(task)['model_approved'])
            local=w.retrieve_references(task,version=1,tool='paper_search',arguments={'query':'brentq 求根函数的区间端点是否需要异号','limit':3,'filters':{'kind':'algorithm'}},actor='TEST_MODEL_STUB',request_id='local-reference')
            check('workflow_calls_real_bge_qdrant_mcp',local['envelope']['status']=='ok' and bool(local['envelope']['data']['hits']))
            official=w.retrieve_references(task,version=1,tool='web_search',arguments={'query':'A163','limit':2,'scope_url':'https://dxs.moe.gov.cn/zx/hd/sxjm/sxjmlw/2024qgdxssxjmjslwzs/'},actor='TEST_MODEL_STUB',request_id='official-reference')
            check('workflow_network_same_problem_reference_allowed',official['envelope']['status']=='ok' and any('A163' in h['title'] for h in official['envelope']['data']['hits']))
            refs=w.tool_evidence(task)['references'];count=len(refs)
            restored=w.retrieve_references(task,version=1,tool='reference_get',arguments={'reference_id':refs[0]['reference_id']},actor='TEST_MODEL_STUB',request_id='reference-lookup')
            check('reference_archive_restored_without_duplicate',restored['envelope']['status']=='ok' and len(w.tool_evidence(task)['references'])==count)
            denied=False
            try:w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id='approval')
            except WorkflowError as exc:denied='proposal discussion' in str(exc)
            check('approval_requires_reference_proposal',denied and not w.task(task)['model_approved'])
            decisions=[{'reference_id':r['reference_id'],'decision':'rejected'} for r in refs]
            w.discuss_references(task,version=1,kind='proposal',text='TEST MODEL STUB: these external sources are traceability fixtures and are not applicable to the fixed sum-of-squares operation. Reject all; execute only the registered fixed code. No LLM generated this proposal.',references=decisions,actor='TEST_MODEL_STUB',request_id='proposal')
            w.discuss_references(task,version=1,kind='feedback',text='TEST_SIMULATED_USER fixture: references remain external, irrelevant methods are not adopted. This is not a real user decision.',references=decisions,actor='TEST_SIMULATED_USER',request_id='feedback')
            original=w._event
            def injected_event(*args):
                if args[1]=='execution_receipt_registered':raise RuntimeError('TEST_C5 crash after durable receipt, before execution publication')
                return original(*args)
            w._event=injected_event
            injected=False
            try:w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id='approval',reason='TEST fixture approval, not real user approval')
            except RuntimeError as exc:injected='TEST_C5 crash' in str(exc)
            check('durable_mcp_receipt_survives_publication_interrupt',injected and len(w.inspect(task)['execution_receipts'])==1 and w.inspect(task)['execution'] is None)
            event=w.db.execute("SELECT payload FROM mc_events WHERE task_id=%s AND kind='model_approve'",(task,)).fetchone()
            check('approval_event_freezes_reference_snapshot',len(event['payload']['reference_snapshot']['references'])==count and all(r['decision']=='rejected' for r in event['payload']['reference_snapshot']['references']))
        with Workflow() as w:
            state=w.resume(task)
            check('fresh_workflow_resumes_to_result_gate',state['task']['phase']=='WAITING_RESULT_APPROVAL' and not state['task']['result_approved'])
            check('execution_does_not_claim_mathematical_review',state['result']['review']['status']=='unknown' and state['result']['review']['mathematical_review']=='not_performed')
            artifacts=state['execution']['artifacts'];output=next(a for a in artifacts if a['name']=='result.json')
            path=ROOT/output['path'];value=json.loads(path.read_text(encoding='utf-8'))
            check('actual_docker_output_is_14_with_verified_hash',value=={'total':14} and sha(path.read_bytes())==output['sha256'])
            blocked=False
            try:w.action(task,version=1,kind='result',decision='approve',result_revision=1,actor='TEST_SIMULATED_USER',request_id='result')
            except WorkflowError as exc:blocked='human review reason' in str(exc)
            check('unknown_solver_review_needs_explicit_reason',blocked)
            w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id='approval',reason='TEST fixture approval, not real user approval')
            w.resume(task)
            traces=w.tool_evidence(task)['mcp_traces']
            check('repeat_approval_and_replay_do_not_redispatch',sum(t['tool']=='code_execute' and t['phase']=='completed' for t in traces)==1 and len(w.inspect(task)['execution_receipts'])==1)
            w.action(task,version=1,kind='result',decision='approve',result_revision=1,reason='TEST_SIMULATED_USER independently read fixed output 14 and verified archive hash; not a real approval or mathematical modeling proof',actor='TEST_SIMULATED_USER',request_id='result')
            check('two_simulated_gates_complete_fixed_fixture',w.task(task)['phase']=='COMPLETED')
            dossier=w.version_dossier(task)
            check('dossier_contains_sources_discussions_traces_and_receipt',len(dossier['references'])==count and len(dossier['reference_discussions'])==2 and len(dossier['execution_receipts'])==1 and all(t['contract_sha256']==digest(contract) for t in dossier['mcp_traces']))
            late=False
            try:w.retrieve_references(task,version=1,tool='web_search',arguments={'query':'new source'},actor='TEST_MODEL_STUB',request_id='late-reference')
            except WorkflowError:late=True
            check('new_sources_cannot_mutate_approved_version',late)
            formal_after=w.db.execute('SELECT current_version,phase,model_approved,result_approved,execution_id FROM mc_tasks WHERE id=%s',('dragon-q1',)).fetchone()
            check('formal_task_unchanged',formal_before==formal_after)
            save('dossier.json',dossier)
        result=DockerExecutor(execution).status(job_id)
        check('owned_container_cleanup_confirmed',result['cleanup']['removed'] is True and result['restrictions']['network']=='none')
        evidence={'task_id':task,'job_id':job_id,'execution_root':str(execution),'reference_count':count,
                  'mcp_calls':sum(t['phase']=='completed' for t in traces),'code_dispatches':1}
    except Exception as exc:
        failure={'type':type(exc).__name__,'message':str(exc)}
        check('verification_exception',False,**failure)
    finally:
        if old_root is None:os.environ.pop('MODELCREW_EXECUTION_ROOT',None)
        else:os.environ['MODELCREW_EXECUTION_ROOT']=old_root
    report={'timestamp':datetime.now(timezone.utc).isoformat(),'status':'passed' if all(c['passed'] for c in checks) else 'failed',
            'checks':checks,'evidence':evidence,'failure':failure,'new_llm_calls':0,'new_formal_problem_solves':0,
            'new_real_user_approvals':0,'fixed_test_code_executions':1 if evidence else None,
            'actors':'TEST_MODEL_STUB and TEST_SIMULATED_USER only','stage_C_complete':False}
    save('verification.json',report);print(json.dumps(report,ensure_ascii=True))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    verify(parser.parse_args().output)
