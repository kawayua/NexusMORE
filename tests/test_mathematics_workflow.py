"""Real PostgreSQL/checkpointer/HTTP tests; TEST_SIMULATED_USER only, no actual solve."""
import copy,json,os,subprocess,sys,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from modelcrew.api import create_app
from modelcrew.config import ROOT
from modelcrew.workflow import Workflow,WorkflowError
from modelcrew.mathematics import MathematicsError,latest,assert_gate_binding
from modelcrew.contracts import digest
from modelcrew.executors import receipt
from modelcrew.inputs import file_hash

class FixedBackend:
    replay_safe=True
    def execute(self,request):
        return receipt(request,[{'path':request.config['path'],'sha256':request.config['sha256'],'role':'TEST_ONLY_bplus_fixture'}],details={'TEST_ONLY':True,'not_new_solve':True})
def workflow():return Workflow(executors={'bplus-test':FixedBackend()})
@pytest.fixture
def bundle(tmp_path):
    c=json.loads((ROOT/'stage-b-plus/examples/contract-v2-snapshot.json').read_text(encoding='utf-8'))
    p=json.loads((ROOT/'stage-b-plus/examples/valid-bench-dragon.json').read_text(encoding='utf-8'))
    f=tmp_path/'fixture.json';f.write_text('{"TEST_ONLY":true}',encoding='utf-8')
    task='test-bplus-'+uuid.uuid4().hex
    config={'path':str(f),'sha256':file_hash(f)}
    with workflow() as w:w.create(task,c,project='bplus-tests',executor_key='bplus-test',executor_config=config,math_package=p)
    return task,c,p

def action(w,task,kind='model',version=1,request=None,**kw):
    return w.action(task,actor='TEST_SIMULATED_USER',request_id=request or uuid.uuid4().hex,version=version,kind=kind,reason='TEST_ONLY reviewed mathematical conditions and evidence',**kw)
def approve(w,task,version=1,**kw):
    sha=w.mathematical_proposal(task,version)['semantic_sha256']
    return action(w,task,version=version,decision='approve',math_semantic_sha256=sha,**kw)

def test_both_approvals_bind_same_contract_math_and_result(bundle):
    task,c,p=bundle
    with workflow() as w:
        s=w.inspect(task);sha=s['mathematics']['semantic_sha256'];assert s['execution'] is None
        s=approve(w,task);eid=s['task']['execution_id'];assert s['task']['phase']=='WAITING_RESULT_APPROVAL'
        s=approve(w,task,kind='result',result_revision=1);assert s['task']['phase']=='COMPLETED'
        events=[e for e in s['events'] if e['kind'] in ['model_approve','result_approve']]
        assert len(events)==2
        for e in events:
            b=e['payload']['math_snapshot'];assert b['semantic_sha256']==sha and b['contract_sha256']==digest(c)
        assert events[-1]['payload']['math_snapshot']['execution_id']==str(eid)
        assert w.version_dossier(task)['mathematical_history'][0]['revision']==1

@pytest.mark.parametrize('sha',[None,'0'*64])
def test_missing_stale_math_hash_cannot_solve(bundle,sha):
    task,c,p=bundle
    with workflow() as w:
        with pytest.raises(MathematicsError,match='semantic hash'):action(w,task,decision='approve',math_semantic_sha256=sha)
        assert w.inspect(task)['execution'] is None and not w.task(task)['model_approved']

def test_explicit_review_reason_required(bundle):
    task,c,p=bundle
    with workflow() as w:
        with pytest.raises(MathematicsError,match='review reason'):w.action(task,actor='TEST_SIMULATED_USER',request_id='no-review',version=1,kind='model',decision='approve',math_semantic_sha256=w.mathematical_proposal(task)['semantic_sha256'])

def test_math_change_new_version_invalidates_both_gates_and_execution(bundle):
    task,c,p=bundle
    with workflow() as w:
        first=approve(w,task);oldsha=first['mathematics']['semantic_sha256'];eid=first['task']['execution_id']
        approve(w,task,kind='result',result_revision=1)
        changed=copy.deepcopy(p);changed['validation_plan'][0]['threshold']=1e-9
        s=action(w,task,kind='revise_mathematics',math_package=changed)
        assert s['task']['current_version']==2 and not s['task']['model_approved'] and not s['task']['result_approved'] and s['execution'] is None
        assert s['contract']['sha256']==digest(c) and s['mathematics']['semantic_sha256']!=oldsha
        history=w.version_dossier(task,2)
        assert history['changes_from_parent']==[]
        assert any(x['path']=='/validation_plan/0/threshold' or x['path']=='/validation_plan' for x in history['mathematical_changes_from_parent'])
        with pytest.raises(MathematicsError):action(w,task,version=2,decision='approve',math_semantic_sha256=oldsha)
        with pytest.raises(WorkflowError):action(w,task,version=1,decision='approve',math_semantic_sha256=oldsha)
        new=approve(w,task,version=2);assert new['task']['execution_id']!=eid
        assert len(w.version_dossier(task,1)['executions'])==1

def test_layout_keeps_both_approvals_and_execution(bundle):
    task,c,p=bundle
    with workflow() as w:
        first=approve(w,task);approve(w,task,kind='result',result_revision=1)
        p['presentation']['equation_spacing']='relaxed'
        response=w.publish_mathematics(task,version=1,package=p,actor='TEST_EDITOR',request_id='layout',reason='TEST_ONLY spacing')
        assert response['change']['kind']=='presentation' and response['revision']==2
        s=w.resume(task)
        assert s['task']['phase']=='COMPLETED' and s['task']['execution_id']==first['task']['execution_id']
        assert s['mathematics']['semantic_sha256']==first['mathematics']['semantic_sha256']
        assert s['mathematics']['package_sha256']!=first['mathematics']['package_sha256']
        assert_gate_binding(w,s['task'],'model');assert_gate_binding(w,s['task'],'result')
        d=w.version_dossier(task);assert len(d['mathematical_history'])==2

def test_semantic_edit_cannot_use_presentation_endpoint(bundle):
    task,c,p=bundle;p['dossier']['symbols'][0]['domain']='changed'
    with workflow() as w:
        with pytest.raises(WorkflowError,match='revise_mathematics'):w.publish_mathematics(task,version=1,package=p,actor='TEST_EDITOR',request_id='bad-layout',reason='pretend layout')
        assert latest(w,task,1)['revision']==1

def test_math_cannot_drop_on_model_change_and_invalid_bundle_rolls_back(bundle):
    task,c,p=bundle;changed=copy.deepcopy(c);changed['risks'].append('TEST_ONLY new risk')
    with workflow() as w:
        with pytest.raises(WorkflowError,match='silently dropped'):action(w,task,kind='revise_model',contract=changed)
        p['dossier']['equations'][0]['symbol_ids'].append('undefined')
        with pytest.raises(MathematicsError):action(w,task,kind='revise_model',contract=changed,math_package=p)
        assert w.task(task)['current_version']==1 and len(w.versions(task))==1

def test_restoration_copies_math_but_does_not_restore_approval(bundle):
    task,c,p=bundle
    with workflow() as w:
        approve(w,task);changed=copy.deepcopy(p);changed['validation_plan'][0]['threshold']=1e-9
        action(w,task,kind='revise_mathematics',math_package=changed)
        s=action(w,task,kind='restore_version',version=2,source_version=1)
        assert s['task']['current_version']==3 and not s['task']['model_approved'] and s['execution'] is None
        assert s['mathematics']['content']==p and s['mathematics']['semantic_sha256']!=w.mathematical_proposal(task,1)['semantic_sha256']
        assert s['contract']['restored_from_version']==1

def test_math_schema_immutability_database_trigger(bundle):
    import psycopg
    task,c,p=bundle
    with workflow() as w:
        with pytest.raises(psycopg.Error,match='immutable'):w.db.execute('UPDATE mc_math_packages SET reason=%s WHERE task_id=%s',('changed',task))
        with pytest.raises(psycopg.Error,match='immutable'):w.db.execute('DELETE FROM mc_math_packages WHERE task_id=%s',(task,))
        assert latest(w,task,1)['revision']==1

def test_duplicate_concurrent_math_approval_executes_once(bundle):
    task,c,p=bundle
    def call(_):
        with workflow() as w:return approve(w,task,request='same-approval')['task']['phase']
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(call,[1,2]))==['WAITING_RESULT_APPROVAL']*2
    with workflow() as w:assert len(w.version_dossier(task)['executions'])==1

def test_publication_crash_restart_and_idempotency(bundle):
    task,c,p=bundle;p['presentation']['equation_spacing']='relaxed'
    kw={'version':1,'package':p,'actor':'TEST_EDITOR','request_id':'layout-crash','reason':'TEST_ONLY spacing'}
    with workflow() as w:
        with pytest.raises(RuntimeError,match='Injected crash'):w.publish_mathematics(task,**kw,crash_after_commit=True)
    with workflow() as w:
        first=w.publish_mathematics(task,**kw);second=w.publish_mathematics(task,**kw)
        assert first==second and first['revision']==2
        bad=copy.deepcopy(kw);bad['reason']='different'
        with pytest.raises(WorkflowError,match='Idempotency'):w.publish_mathematics(task,**bad)
        assert w.resume(task)['task']['phase']=='WAITING_MODEL_APPROVAL'

def test_checkpoint_crash_math_confirmation_recovers(bundle):
    task,c,p=bundle
    with workflow() as w:
        with pytest.raises(RuntimeError,match='Injected crash'):approve(w,task,crash_after_commit=True)
    with workflow() as w:
        s=w.resume(task);assert s['task']['phase']=='WAITING_RESULT_APPROVAL'
        with pytest.raises(RuntimeError,match='Injected crash'):approve(w,task,kind='result',result_revision=1,crash_after_commit=True)
    with workflow() as w:
        assert w.resume(task)['task']['phase']=='COMPLETED'
        assert len(w.version_dossier(task)['executions'])==1

def test_new_process_reads_same_math_waiting_gates(bundle):
    task,c,p=bundle
    def show():
        run=subprocess.run([sys.executable,'-m','modelcrew','math-show',task],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=25)
        assert run.returncode==0,run.stderr
        return json.loads(run.stdout)
    sha=show()['semantic_sha256']
    with workflow() as w:approve(w,task)
    assert show()['semantic_sha256']==sha

def test_http_math_proposal_and_hash_gates(bundle):
    task,c,p=bundle;prefix=f'/tasks/{task}'
    with TestClient(create_app(workflow)) as client:
        response=client.get(prefix+'/proposal');assert response.status_code==200
        proposal=response.json()['mathematics'];assert '数学提案' in proposal['proposal_markdown']
        assert client.get(prefix+'/versions/1/mathematics').json()['content']==p
        action_body={'actor':'TEST_SIMULATED_USER','request_id':'http-math','version':1,'kind':'model','decision':'approve','reason':'TEST_ONLY mathematical review'}
        assert client.post(prefix+'/actions',json=action_body).status_code==422
        action_body['math_semantic_sha256']=proposal['semantic_sha256']
        assert client.post(prefix+'/actions',json=action_body).json()['task']['phase']=='WAITING_RESULT_APPROVAL'
        p['presentation']['equation_spacing']='relaxed'
        body={'package':p,'actor':'TEST_EDITOR','request_id':'http-layout','reason':'TEST_ONLY spacing'}
        assert client.post(prefix+'/versions/1/mathematics',json=body).json()['revision']==2
        assert client.get(prefix+'/versions/999/mathematics').status_code==404

def test_initial_attach_only_before_approval_and_no_legacy_confirmation_import(bundle):
    task,c,p=bundle
    fresh='test-bplus-legacy-'+uuid.uuid4().hex
    with workflow() as w:
        config=w.task(task)['executor_config'];w.create(fresh,c,executor_key='bplus-test',executor_config=config)
        assert w.mathematical_proposal(fresh) is None
        action(w,fresh,decision='approve')
        with pytest.raises(WorkflowError,match='Already approved'):w.publish_mathematics(fresh,version=1,package=p,actor='TEST_EDITOR',request_id='attach',reason='TEST_ONLY')
        s=action(w,fresh,kind='revise_mathematics',math_package=p)
        assert s['task']['current_version']==2 and not s['task']['model_approved']


def test_result_hash_and_revision_cannot_be_reused_after_interpretation_change(bundle):
    task,c,p=bundle
    with workflow() as w:
        first=approve(w,task);eid=first['task']['execution_id']
        approve(w,task,kind='result',result_revision=1)
        state=action(w,task,kind='revise_interpretation',result_revision=1)
        assert state['task']['result_revision']==2 and not state['task']['result_approved'] and state['task']['execution_id']==eid
        with pytest.raises(WorkflowError):approve(w,task,kind='result',result_revision=1)
        with pytest.raises(MathematicsError):action(w,task,kind='result',decision='approve',result_revision=2)
        assert approve(w,task,kind='result',result_revision=2)['task']['phase']=='COMPLETED'


def test_attach_initial_package_before_model_approval(bundle):
    task,c,p=bundle;fresh='test-bplus-initial-'+uuid.uuid4().hex
    with workflow() as w:
        w.create(fresh,c,executor_key='bplus-test',executor_config=w.task(task)['executor_config'])
        r=w.publish_mathematics(fresh,version=1,package=p,actor='TEST_EDITOR',request_id='initial',reason='TEST_ONLY new proposal')
        assert r['change']['kind']=='initial' and r['revision']==1
        assert not w.task(fresh)['model_approved'] and w.inspect(fresh)['execution'] is None
        assert approve(w,fresh)['task']['phase']=='WAITING_RESULT_APPROVAL'


def test_invalid_publish_returns_conflict_without_partial_records(bundle):
    task,c,p=bundle
    with TestClient(create_app(workflow)) as client:
        response=client.post(f'/tasks/{task}/versions/1/mathematics',json={'package':{},'actor':'TEST_EDITOR','request_id':'bad','reason':'TEST_ONLY malformed'})
        assert response.status_code in [409,422]
    with workflow() as w:assert latest(w,task,1)['revision']==1


def test_semantic_revise_replay_after_crash_does_not_create_another_version(bundle):
    task,c,p=bundle;p['validation_plan'][0]['threshold']=1e-9
    with workflow() as w:
        with pytest.raises(RuntimeError,match='Injected crash'):action(w,task,kind='revise_mathematics',math_package=p,request='math-crash',crash_after_commit=True)
    with workflow() as w:
        s=action(w,task,kind='revise_mathematics',math_package=p,request='math-crash')
        assert s['task']['current_version']==2 and not s['task']['model_approved']
        assert len(w.versions(task))==2 and s['checkpoint_next']==['model_gate']


def test_format_change_and_bad_math_cannot_bypass_initial_validation(bundle):
    task,c,p=bundle
    with workflow() as w:
        bad=copy.deepcopy(p);bad['presentation']['latex_override']='1=2'
        with pytest.raises(MathematicsError):w.publish_mathematics(task,version=1,package=bad,actor='TEST_EDITOR',request_id='hidden-equation',reason='TEST_ONLY')
        assert latest(w,task,1)['revision']==1
