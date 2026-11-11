"""Real DB/checkpointer with simulated tool responses; no real user confirmations."""
import copy
import json
import uuid
from pathlib import Path

import psycopg
import pytest

from modelcrew.contracts import digest
from modelcrew.docker_executor import register_job,sha
from modelcrew.mcp_client import McpTransportError
from modelcrew.paper_search_mcp import SearchTool
from modelcrew.web_references import PublicWeb
from modelcrew.workflow import Workflow,WorkflowError
from scripts.c5_fixture import contract_for,CODE


class Page(PublicWeb):
    def fetch(self,url):
        return {'url':url,'content':b'<title>External example</title><main>General external reference</main>',
                'content_type':'text/html','retrieved_at':'2026-11-06T00:00:00Z'}


class Client:
    def __init__(self,folder):
        self.adapter=SearchTool(log_path=folder/'calls.jsonl',web=Page());self.calls=[]
    def call(self,service,tool,args):
        self.calls.append((service,tool,args))
        return self.adapter.invoke(tool,args).structuredContent


@pytest.fixture
def setup_task(tmp_path):
    path=tmp_path/'numbers.json';path.write_text('[1,2,3]')
    contract=contract_for(path);task='test-c5-'+uuid.uuid4().hex;client=Client(tmp_path)
    with Workflow(mcp_client=client) as w:w.create(task,contract,project='automated-tests')
    return task,contract,client


def retrieve(w,task,key='search'):
    return w.retrieve_references(task,version=1,tool='web_read',arguments={'url':'https://example.org/reference'},actor='TEST_MODEL_STUB',request_id=key)


def approve(w,task,key='approve',**kwargs):
    return w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id=key,**kwargs)


def discuss(w,task,ref,decision='rejected',key='proposal',kind='proposal'):
    return w.discuss_references(task,version=1,kind=kind,text='TEST ONLY external idea considered; chosen plan recorded for review',references=[{'reference_id':ref,'decision':decision}],actor='TEST_MODEL_STUB' if kind=='proposal' else 'TEST_SIMULATED_USER',request_id=key)


def test_retrieval_is_version_bound_idempotent_and_does_not_approve(setup_task):
    task,contract,client=setup_task
    with Workflow(mcp_client=client) as w:
        first=retrieve(w,task);again=retrieve(w,task)
        assert first==again and len(client.calls)==1
        assert not w.task(task)['model_approved'] and w.task(task)['phase']=='WAITING_MODEL_APPROVAL'
        evidence=w.tool_evidence(task)
        assert len(evidence['mcp_traces'])==2 and len(evidence['references'])==1
        assert all(t['contract_sha256']==digest(contract) for t in evidence['mcp_traces'])
        with pytest.raises(WorkflowError,match='Idempotency'):
            w.retrieve_references(task,version=1,tool='web_read',arguments={'url':'https://example.org/other'},actor='TEST_MODEL_STUB',request_id='search')
        with pytest.raises(WorkflowError,match='Only reference'):
            w.retrieve_references(task,version=1,tool='code_execute',arguments={},actor='TEST_MODEL_STUB',request_id='illegal')


def test_discussion_required_and_approval_freezes_source_snapshot(setup_task):
    task,contract,client=setup_task
    with Workflow(mcp_client=client) as w:
        result=retrieve(w,task);ref=result['envelope']['data']['hits'][0]['citation']['reference_id']
        with pytest.raises(WorkflowError,match='proposal discussion'):approve(w,task)
        discuss(w,task,ref,'considered')
        with pytest.raises(WorkflowError,match='Resolve considered'):approve(w,task)
        discuss(w,task,ref,'adopted','feedback','feedback')
        state=approve(w,task)
        event=next(e for e in state['events'] if e['kind']=='model_approve')
        assert event['payload']['reference_snapshot']['references'][0]['decision']=='adopted'
        snapshot=event['payload']['reference_snapshot'];assert snapshot['sha256']==digest({k:v for k,v in snapshot.items() if k!='sha256'})
        assert state['task']['phase']=='WAITING_RESULT_APPROVAL' and not state['task']['result_approved']
        assert w.version_dossier(task)['references'][0]['reference_id']==ref
        with pytest.raises(WorkflowError,match='unapproved'):retrieve(w,task,'post-approval')
        with pytest.raises(WorkflowError,match='new model version'):discuss(w,task,ref,key='late')


def test_reference_lookup_preserves_id_and_does_not_duplicate(setup_task):
    task,contract,client=setup_task
    with Workflow(mcp_client=client) as w:
        ref=retrieve(w,task)['envelope']['data']['hits'][0]['citation']['reference_id']
        value=w.retrieve_references(task,version=1,tool='reference_get',arguments={'reference_id':ref},actor='TEST_MODEL_STUB',request_id='lookup')
        assert value['envelope']['status']=='ok'
        assert len(w.tool_evidence(task)['references'])==1


def test_cross_task_and_old_version_citations_not_silently_inherited(setup_task):
    task,contract,client=setup_task
    with Workflow(mcp_client=client) as w:
        ref=retrieve(w,task)['envelope']['data']['hits'][0]['citation']['reference_id']
        other='test-c5-other-'+uuid.uuid4().hex;w.create(other,contract,project='automated-tests')
        with pytest.raises(WorkflowError,match='not bound'):discuss(w,other,ref)
        changed=copy.deepcopy(contract);changed['risks'].append('TEST version boundary')
        w.action(task,version=1,kind='revise_model',contract=changed,reason='TEST change',actor='TEST_SIMULATED_USER',request_id='v2')
        with pytest.raises(WorkflowError,match='Stale'):retrieve(w,task,'stale')
        assert w.tool_evidence(task)['references']==[]
        assert len(w.tool_evidence(task,1)['references'])==1


def test_transport_failure_has_started_and_error_trace_without_false_empty_success(setup_task):
    task,contract,_=setup_task
    class Broken:
        def call(self,*args):raise RuntimeError('secret transport')
    with Workflow(mcp_client=Broken()) as w:
        with pytest.raises(McpTransportError):retrieve(w,task)
        assert [r['phase'] for r in w.tool_evidence(task)['mcp_traces']]==['started','transport_error']
        assert not w.task(task)['model_approved'] and not w.tool_evidence(task)['references']


def test_source_and_trace_tables_are_immutable(setup_task):
    task,contract,client=setup_task
    with Workflow(mcp_client=client) as w:
        ref=retrieve(w,task)['envelope']['data']['hits'][0]['citation']['reference_id'];discuss(w,task,ref)
        for table in ('mc_mcp_traces','mc_references','mc_reference_discussions'):
            with pytest.raises(psycopg.Error,match='immutable'):w.db.execute(f'DELETE FROM {table} WHERE task_id=%s',(task,))


@pytest.fixture
def execution_task(tmp_path,monkeypatch):
    root=tmp_path/'execution';monkeypatch.setenv('MODELCREW_EXECUTION_ROOT',str(root))
    data=tmp_path/'numbers.json';data.write_text('[1,2,3]');contract=contract_for(data)
    code=tmp_path/'solver.py';code.write_text(CODE)
    task='test-c5-exec-'+uuid.uuid4().hex;job_id='test-'+uuid.uuid4().hex
    job=register_job(root,job_id,code,[{'input_id':'numbers','name':'numbers.json','path':str(data),'sha256':sha(data.read_bytes())}],
                     {'mode':'workflow','task_id':task,'version':1,'contract_sha256':digest(contract)})
    config={'job_id':job_id,'job_sha256':job['job_sha256']}
    class ExecutionClient:
        calls=[]
        lose_ack=False
        outcome='succeeded'
        def call(self,service,tool,args):
            self.calls.append(tool)
            output=root/'runs'/job_id/'artifacts/result.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text('{"total":14}')
            if tool=='code_execute' and self.lose_ack:raise RuntimeError('TEST lost acknowledgement')
            return {'schema_version':'1.0.0','tool':tool,'call_id':str(uuid.uuid4()),'status':'ok','elapsed_ms':1.,'error':None,
                    'data':{'run_id':job_id,'job_sha256':job['job_sha256'],'code_sha256':job['code_sha256'],'authorization':job['authorization'],
                            'status':self.outcome,'artifacts':[{'name':'result.json','path':output.relative_to(root).as_posix(),'role':'execution_output','sha256':sha(output.read_bytes()),'size_bytes':output.stat().st_size}],
                            'cleanup':{'removed':True},'image_id':'TEST_SIMULATED_IMAGE'}}
    client=ExecutionClient()
    with Workflow(mcp_client=client) as w:w.create(task,contract,project='automated-tests',executor_key='mcp-code-executor',executor_config=config)
    return task,contract,client,job


def test_mcp_execution_uses_confirmed_job_and_keeps_result_gate(execution_task):
    task,contract,client,job=execution_task
    assert client.calls==[]
    with Workflow(mcp_client=client) as w:
        state=approve(w,task)
        assert client.calls==['code_execute'] and state['task']['phase']=='WAITING_RESULT_APPROVAL'
        assert state['execution']['mode']=='solver' and state['result']['review']['status']=='unknown'
        with pytest.raises(WorkflowError,match='human review reason'):
            w.action(task,version=1,kind='result',decision='approve',result_revision=1,actor='TEST_SIMULATED_USER',request_id='result')
        w.resume(task);approve(w,task)
        assert client.calls==['code_execute']
        w.action(task,version=1,kind='result',decision='approve',result_revision=1,reason='TEST ONLY verified fixed total 14; no proof of modeling quality',actor='TEST_SIMULATED_USER',request_id='result')
        assert w.task(task)['phase']=='COMPLETED'
        assert len(w.version_dossier(task)['mcp_traces'])==2


def test_unknown_execution_recovers_status_without_redispatch(execution_task):
    task,contract,client,job=execution_task;client.lose_ack=True
    with Workflow(mcp_client=client) as w:
        with pytest.raises(McpTransportError):approve(w,task)
        assert w.task(task)['phase']=='SOLVING' and not w.inspect(task)['execution']
    with Workflow(mcp_client=client) as w:
        state=w.resume(task)
        assert state['task']['phase']=='WAITING_RESULT_APPROVAL'
        assert client.calls==['code_execute','code_execution_status']
        assert state['execution_receipts'][0]['payload']['details']['recovered_via_status'] is True


def test_code_failure_is_not_published_as_result(execution_task):
    task,contract,client,job=execution_task;client.outcome='code_error'
    with Workflow(mcp_client=client) as w:
        with pytest.raises(ValueError,match='solver failed'):approve(w,task)
        state=w.inspect(task)
        assert state['task']['phase']=='SOLVING' and state['execution'] is None and state['result'] is None
        assert state['execution_attempts'][-1]['payload']['failure_domain']=='code'
        assert not state['task']['result_approved']


def test_job_binding_rejects_wrong_task_or_reuse_after_revision(execution_task):
    task,contract,client,job=execution_task
    with Workflow(mcp_client=client) as w:
        with pytest.raises(ValueError,match='authorization differs'):
            w.create('test-c5-wrong-'+uuid.uuid4().hex,contract,project='automated-tests',executor_key='mcp-code-executor',executor_config={'job_id':job['job_id'],'job_sha256':job['job_sha256']})
        changed=copy.deepcopy(contract);changed['risks'].append('TEST revision needs fresh job')
        with pytest.raises(ValueError,match='authorization differs'):
            w.action(task,version=1,kind='revise_model',contract=changed,reason='TEST new version',actor='TEST_SIMULATED_USER',request_id='revision')
        assert w.task(task)['current_version']==1 and not client.calls


def test_http_reference_operations_surface_discussion_and_reject_execution_tool(setup_task):
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    task,contract,transport=setup_task
    with TestClient(create_app(lambda:Workflow(mcp_client=transport))) as client:
        prefix='/tasks/'+task
        response=client.post(prefix+'/references/retrieve',json={'version':1,'tool':'web_read','arguments':{'url':'https://example.org/reference'},'actor':'TEST_MODEL_STUB','request_id':'http-retrieve'})
        assert response.status_code==200
        ref=response.json()['envelope']['data']['hits'][0]['citation']['reference_id']
        assert client.post(prefix+'/references/retrieve',json={'version':1,'tool':'code_execute','arguments':{'job_id':'anything'},'actor':'TEST_MODEL_STUB','request_id':'illegal'}).status_code==422
        discussion=client.post(prefix+'/references/discussions',json={'version':1,'kind':'proposal','text':'TEST MODEL STUB: reject unrelated reference','references':[{'reference_id':ref,'decision':'rejected'}],'actor':'TEST_MODEL_STUB','request_id':'http-discussion'})
        assert discussion.status_code==200
        assert client.get(prefix+'/proposal').json()['reference_evidence']['references'][0]['reference_id']==ref
        assert len(client.get(prefix+'/tool-evidence').json()['reference_discussions'])==1
        assert client.get(prefix+'/versions/1').json()['references'][0]['payload']['citation']['modeler_generated'] is False
        assert len(transport.calls)==1


def test_result_confirmation_rechecks_mcp_artifact_integrity(execution_task,monkeypatch):
    task,contract,client,job=execution_task
    with Workflow(mcp_client=client) as w:
        approve(w,task)
        monkeypatch.setattr('modelcrew.reviews.artifact_status',lambda artifact:'changed')
        with pytest.raises(WorkflowError,match='artifacts changed'):
            w.action(task,version=1,kind='result',decision='approve',result_revision=1,reason='TEST review reason cannot bypass integrity',actor='TEST_SIMULATED_USER',request_id='result')
        assert not w.task(task)['result_approved']
