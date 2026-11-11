import copy,json,os,subprocess,sys,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from modelcrew.workflow import Workflow,WorkflowError
from modelcrew.config import database_url,ROOT

@pytest.fixture
def example():return json.loads((ROOT/'contracts/examples/valid-2024-a-q1.json').read_text(encoding='utf-8'))
@pytest.fixture
def task(example):
    task='test-'+uuid.uuid4().hex
    with Workflow() as w:w.create(task,example,project='automated-tests')
    return task

def act(w,task,kind='model',version=1,request='req-1',decision='approve',revision=None,reason='',contract=None,**kwargs):
    return w.action(task,actor='TEST_SIMULATED_USER',request_id=request,version=version,kind=kind,decision=decision,result_revision=revision,reason=reason,contract=contract,**kwargs)

def test_two_gates_survive_new_process_and_no_auto_approval(task):
    def show():
        p=subprocess.run([sys.executable,'-m','modelcrew','resume',task],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=25)
        assert p.returncode==0,p.stderr
        return json.loads(p.stdout)
    assert show()['task']['phase']=='WAITING_MODEL_APPROVAL'
    with Workflow() as w:
        assert not w.inspect(task)['execution']
        state=act(w,task);assert state['task']['phase']=='WAITING_RESULT_APPROVAL'
        assert not w.db.execute('SELECT 1 FROM mc_summaries WHERE task_id=%s',(task,)).fetchone()
    assert show()['task']['phase']=='WAITING_RESULT_APPROVAL'
    with Workflow() as w:
        state=act(w,task,kind='result',request='result-1',revision=1)
        assert state['task']['phase']=='COMPLETED'
        assert w.db.execute('SELECT count(*) AS n FROM mc_summaries WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_duplicate_and_payload_conflict(task):
    with Workflow() as w:
        act(w,task);act(w,task)
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1
        with pytest.raises(WorkflowError):act(w,task,decision='reject',reason='different')
        with pytest.raises(WorkflowError):act(w,task,request='different-key')

def test_rejection_and_guidance_version_history(task,example):
    with Workflow() as w:
        s=act(w,task,decision='reject',reason='需要补充说明');assert s['task']['phase']=='WAITING_MODEL_APPROVAL';assert not s['execution']
        changed=copy.deepcopy(example);changed['risks'].append('用户要求增加图表核验')
        s=act(w,task,kind='revise_model',request='edit',contract=changed,reason='补充图表核验');assert s['task']['current_version']==2
        with pytest.raises(WorkflowError):act(w,task,request='old',version=1)
        assert w.db.execute('SELECT count(*) AS n FROM mc_contracts WHERE task_id=%s',(task,)).fetchone()['n']==2
        s=act(w,task,version=2,request='new');assert s['execution']['version']==2

def test_interpretation_reuses_execution_and_invalidates_confirmation(task):
    with Workflow() as w:
        first=act(w,task);eid=first['task']['execution_id']
        act(w,task,kind='result',request='r1',revision=1)
        state=act(w,task,kind='revise_interpretation',request='explain',revision=1,reason='修改结果解释，不改变计算')
        assert state['task']['execution_id']==eid
        assert state['task']['result_revision']==2 and not state['task']['result_approved']
        assert state['task']['phase']=='WAITING_RESULT_APPROVAL'
        with pytest.raises(WorkflowError):act(w,task,kind='result',request='stale-result',revision=1)
        with pytest.raises(WorkflowError,match='explicit human review reason'):act(w,task,kind='result',request='r2',revision=2)
        act(w,task,kind='result',request='r2',revision=2,reason='TEST_SIMULATED_USER reviewed the changed explanation and unknown semantic status')
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_model_revision_invalidates_execution(task,example):
    with Workflow() as w:
        first=act(w,task);eid=first['task']['execution_id'];changed=copy.deepcopy(example);changed['parameters'][0]['value']=.6
        s=act(w,task,kind='revise_model',request='edit',contract=changed,reason='修改螺距')
        assert s['task']['phase']=='WAITING_MODEL_APPROVAL' and not s['task']['execution_id'] and not s['task']['result_revision']
        s=act(w,task,version=2,request='v2');assert s['task']['execution_id']!=eid
        assert s['execution']['mode']=='fixture' # not a claim that historical outputs satisfy changed math
        assert s['result']['review']['status']=='unknown'

def test_business_commit_before_checkpoint_recovers(task):
    with Workflow() as w:
        with pytest.raises(RuntimeError,match='Injected crash'):act(w,task,crash_after_commit=True)
    with Workflow() as w:
        s=w.resume(task);assert s['task']['phase']=='WAITING_RESULT_APPROVAL'
        with pytest.raises(RuntimeError):act(w,task,kind='result',request='r',revision=1,crash_after_commit=True)
    with Workflow() as w:
        s=w.resume(task);assert s['task']['phase']=='COMPLETED'
        act(w,task,kind='result',request='r',revision=1)
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_lost_checkpoint_reconstructs_without_execution_duplication(task):
    with Workflow() as w:
        act(w,task);tid=w.task(task)['thread_id'];w.saver.delete_thread(tid)
    with Workflow() as w:
        assert w.resume(task)['task']['phase']=='WAITING_RESULT_APPROVAL'
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_concurrent_identical_approval_does_not_repeat_execution(task):
    def confirm(_):
        with Workflow() as w:return act(w,task)['task']['phase']
    with ThreadPoolExecutor(max_workers=2) as ex:results=list(ex.map(confirm,range(2)))
    assert results==['WAITING_RESULT_APPROVAL']*2
    with Workflow() as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_result_approval_before_model_gate_rejected(task):
    with Workflow() as w:
        with pytest.raises(WorkflowError):act(w,task,kind='result',revision=1)
        assert not w.inspect(task)['execution']

def test_raw_graph_resume_is_not_authorization(task):
    from langgraph.types import Command
    with Workflow() as w:
        t=w.task(task)
        with w.lock(task):
            with pytest.raises(WorkflowError,match='approval missing'):
                w.graph.invoke(Command(resume={'approved':True}),{'configurable':{'thread_id':t['thread_id']}})
        assert not w.task(task)['model_approved']
        assert not w.inspect(task)['execution']

def test_contract_history_cannot_be_overwritten(task):
    import psycopg
    with Workflow() as w:
        with pytest.raises(psycopg.Error,match='immutable audit record'):
            w.db.execute("UPDATE mc_contracts SET guidance='overwrite' WHERE task_id=%s",(task,))
        assert w.inspect(task)['contract']['guidance']=='Initial proposal'

@pytest.fixture
def fake_validated_solver(monkeypatch):
    from modelcrew import solver_validation,workflow
    monkeypatch.setattr(workflow,'snapshot_artifacts',lambda items:items) # Transaction-only solver fixture
    def fake(run,contract):
        return {'passed':True,'test_only':True},[{'path':'TEST_ONLY_NOT_REAL_ARTIFACT','sha256':'0'*64,'role':'simulated_validator_for_transaction_test'}]
    monkeypatch.setattr(solver_validation,'validate_run',fake)
    return ROOT/'stage-b/runs'/('simulated-solver-'+uuid.uuid4().hex)

def test_solver_attach_requires_current_model_approval(task,fake_validated_solver):
    with Workflow() as w:
        with pytest.raises(WorkflowError,match='current approved'):w.attach_solver_result(task,version=1,run_dir=fake_validated_solver)
        assert not w.task(task)['execution_id']

def test_solver_attachment_new_revision_preserves_fixture_and_waits(task,fake_validated_solver):
    with Workflow() as w:
        old=act(w,task);fixture_id=old['task']['execution_id']
        s=w.attach_solver_result(task,version=1,run_dir=fake_validated_solver)
        assert s['task']['result_revision']==2 and s['execution']['mode']=='solver'
        assert s['task']['execution_id']!=fixture_id and not s['task']['result_approved']
        assert s['task']['phase']=='WAITING_RESULT_APPROVAL' and s['checkpoint_next']==['result_gate']
        again=w.attach_solver_result(task,version=1,run_dir=fake_validated_solver)
        assert again['task']['execution_id']==s['task']['execution_id'] and again['task']['result_revision']==2
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==2
        with pytest.raises(WorkflowError):act(w,task,kind='result',request='old-fixture',revision=1)
        act(w,task,kind='result',request='real-result',revision=2)
        summary=w.db.execute('SELECT content FROM mc_summaries WHERE task_id=%s',(task,)).fetchone()['content']
        assert summary['kind']=='confirmed_solver_summary'

def test_solver_attachment_rejects_changed_artifacts(task,fake_validated_solver,monkeypatch):
    from modelcrew import solver_validation
    with Workflow() as w:
        act(w,task);w.attach_solver_result(task,version=1,run_dir=fake_validated_solver)
        monkeypatch.setattr(solver_validation,'validate_run',lambda *args:({'passed':True},[{'path':'changed'}]))
        with pytest.raises(WorkflowError,match='artifacts changed'):w.attach_solver_result(task,version=1,run_dir=fake_validated_solver)

def test_solver_attachment_validation_failure_keeps_pending_fixture(task,monkeypatch):
    from modelcrew import solver_validation
    def failed(*args):raise solver_validation.ResultError('Bad binding')
    monkeypatch.setattr(solver_validation,'validate_run',failed)
    with Workflow() as w:
        before=act(w,task)
        with pytest.raises(solver_validation.ResultError):w.attach_solver_result(task,version=1,run_dir=ROOT/'stage-b/runs/bad-simulated-test')
        after=w.inspect(task)
        assert after['task']['execution_id']==before['task']['execution_id']
        assert after['task']['result_revision']==1 and not after['task']['result_approved']

def test_version_entries_are_atomic_idempotent_and_immutable(task,monkeypatch):
    import psycopg
    with Workflow() as w:
        kwargs=dict(version=1,kind='feedback',text='TEST_ONLY feedback',actor='TEST_SIMULATED_USER',request_id='note-1')
        first=w.record_entry(task,**kwargs);assert w.record_entry(task,**kwargs)==first
        with pytest.raises(WorkflowError,match='different action'):w.record_entry(task,**{**kwargs,'text':'different'})
        assert w.db.execute('SELECT count(*) AS n FROM mc_version_entries WHERE task_id=%s',(task,)).fetchone()['n']==1
        with pytest.raises(psycopg.Error,match='immutable'):w.db.execute("UPDATE mc_version_entries SET actor='overwrite' WHERE task_id=%s",(task,))
        real_event=w._event
        monkeypatch.setattr(w,'_event',lambda *a:(_ for _ in ()).throw(RuntimeError('TEST injected event failure')))
        with pytest.raises(RuntimeError,match='injected'):w.record_entry(task,**{**kwargs,'request_id':'note-failed'})
        assert not w.db.execute('SELECT 1 FROM mc_requests WHERE task_id=%s AND request_id=%s',(task,'note-failed')).fetchone()
        assert w.db.execute('SELECT count(*) AS n FROM mc_version_entries WHERE task_id=%s',(task,)).fetchone()['n']==1
        monkeypatch.setattr(w,'_event',real_event)
        w.record_entry(task,**{**kwargs,'request_id':'note-failed'})

def test_creation_with_draft_entries_rolls_back_as_one_transaction(example):
    task='test-create-atomic-'+uuid.uuid4().hex
    entries=[dict(kind='proposal',text='TEST_ONLY proposal',actor='TEST_SIMULATED_USER',request_id='proposal'),dict(kind='next_step',text=' ',actor='TEST_SIMULATED_USER',request_id='next')]
    with Workflow() as w:
        with pytest.raises(WorkflowError):w.create(task,example,project='automated-tests',entries=entries)
        for table in ['mc_tasks','mc_contracts','mc_version_entries','mc_requests','mc_events']:
            column='id' if table=='mc_tasks' else 'task_id'
            assert not w.db.execute(f'SELECT 1 FROM {table} WHERE {column}=%s',(task,)).fetchone()
        entries[1]['text']='TEST_ONLY await approval'
        s=w.create(task,example,project='automated-tests',entries=entries)
        assert not s['task']['model_approved'] and not s['execution']
        assert len(w.version_dossier(task)['entries']['proposal'])==1

def test_concurrent_entry_replay_is_single_insert(task):
    def submit(_):
        with Workflow() as w:return w.record_entry(task,version=1,kind='next_step',text='TEST_ONLY next step',actor='TEST_SIMULATED_USER',request_id='concurrent-note')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,range(2)))
    assert results[0]==results[1]
    with Workflow() as w:assert w.db.execute('SELECT count(*) AS n FROM mc_version_entries WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_restore_creates_new_version_and_replays_after_crash(task,example):
    with Workflow() as w:
        act(w,task);changed=copy.deepcopy(example);changed['risks'].append('TEST_ONLY new risk')
        act(w,task,kind='revise_model',request='v2',contract=changed,reason='TEST_ONLY change')
        act(w,task,version=2,request='approve-v2')
        with pytest.raises(RuntimeError,match='Injected crash'):
            act(w,task,kind='restore_version',version=2,source_version=1,request='restore-1',reason='TEST_ONLY restore v1',crash_after_commit=True)
    with Workflow() as w:
        s=w.resume(task)
        assert s['task']['current_version']==3 and s['task']['phase']=='WAITING_MODEL_APPROVAL'
        assert not s['task']['model_approved'] and not s['task']['result_approved'] and s['execution'] is None
        assert s['contract']['content']==example and s['contract']['parent_version']==2 and s['contract']['restored_from_version']==1
        replay=act(w,task,kind='restore_version',version=2,source_version=1,request='restore-1',reason='TEST_ONLY restore v1')
        assert replay['task']['current_version']==3 and len(w.versions(task))==3
        with pytest.raises(WorkflowError):act(w,task,kind='restore_version',version=3,source_version=2,request='restore-1',reason='different')
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==2
        dossier=w.version_dossier(task,3)
        assert dossier['changes_from_parent'] and dossier['contract']['restored_from_version']==1

def test_restore_refuses_changed_original_inputs(example):
    from modelcrew.inputs import file_hash
    folder=ROOT/'stage-b/runs'/('restore-input-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    path=folder/'input.txt';path.write_text('TEST_ONLY original',encoding='utf-8')
    c=copy.deepcopy(example);c['inputs']=[{**c['inputs'][0],'path':str(path),'sha256':file_hash(path)}]
    task='test-restore-input-'+uuid.uuid4().hex
    with Workflow() as w:
        w.create(task,c,project='automated-tests');changed=copy.deepcopy(c);changed['risks'].append('TEST_ONLY risk')
        act(w,task,kind='revise_model',contract=changed,reason='TEST_ONLY edit')
        path.write_text('TEST_ONLY changed',encoding='utf-8')
        with pytest.raises(WorkflowError,match='input missing or changed'):act(w,task,version=2,kind='restore_version',source_version=1,request='restore',reason='TEST_ONLY restore')
        assert w.task(task)['current_version']==2 and len(w.versions(task))==2
        assert not w.db.execute('SELECT 1 FROM mc_requests WHERE task_id=%s AND request_id=%s',(task,'restore')).fetchone()

def test_schema_11_approval_rejection_rolls_back_and_preserves_wait(example):
    from modelcrew.inputs import draft_inputs,resolve_question,pending_questions
    c=draft_inputs(example);task='test-input-approval-'+uuid.uuid4().hex
    with Workflow() as w:
        w.create(task,c,project='automated-tests')
        with pytest.raises(ValueError,match='Unresolved'):act(w,task)
        assert not w.task(task)['model_approved'] and not w.task(task)['execution_id']
        assert not w.db.execute('SELECT 1 FROM mc_requests WHERE task_id=%s',(task,)).fetchone()
        for q in pending_questions(c):c=resolve_question(c,q['input_id'],q['id'],'TEST_SIMULATED_USER reviewed this input')
        act(w,task,kind='revise_model',request='resolved',contract=c,reason='TEST_ONLY clarify input')
        s=act(w,task,version=2,request='approve-resolved')
        assert s['task']['phase']=='WAITING_RESULT_APPROVAL'

def test_backend_failure_recovers_without_repeating_business_approval(example):
    class Failing:
        def artifacts(self,contract):raise RuntimeError('TEST injected backend failure')
    class Fixed:
        calls=0
        def artifacts(self,contract):
            self.calls+=1
            from modelcrew.executors import HistoricalFixture
            return HistoricalFixture().artifacts(contract)
    task='test-backend-'+uuid.uuid4().hex
    with Workflow(executors={'test-backend':Failing()}) as w:
        w.create(task,example,project='automated-tests',executor_key='test-backend')
        with pytest.raises(RuntimeError,match='backend failure'):act(w,task)
        assert w.task(task)['model_approved']
        assert not w.db.execute('SELECT 1 FROM mc_executions WHERE task_id=%s',(task,)).fetchone()
    with Workflow() as w:
        with pytest.raises(WorkflowError,match='backend unavailable'):w.resume(task)
    fixed=Fixed()
    with Workflow(executors={'test-backend':fixed}) as w:
        s=w.resume(task);w.resume(task)
        assert s['task']['phase']=='WAITING_RESULT_APPROVAL' and fixed.calls==1
        assert w.db.execute("SELECT count(*) AS n FROM mc_events WHERE task_id=%s AND kind='model_approve'",(task,)).fetchone()['n']==1

def test_failed_interpretation_integrity_blocks_approval_without_new_execution(task,monkeypatch):
    from modelcrew import reviews
    with Workflow() as w:
        first=act(w,task)
        monkeypatch.setattr(reviews,'artifact_status',lambda a:'changed')
        s=act(w,task,kind='revise_interpretation',request='new-explanation',revision=1,reason='TEST_ONLY changed explanation')
        assert s['result']['review']['status']=='failed' and s['result']['review']['execution_id']==str(first['task']['execution_id'])
        assert s['result']['review']['artifacts'] and s['task']['execution_id']==first['task']['execution_id']
        with pytest.raises(WorkflowError,match='Failed review'):act(w,task,kind='result',request='cannot-approve',revision=2,reason='TEST_ONLY acknowledge')
        assert not w.task(task)['result_approved']
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_interpretation_rechecks_artifacts_at_approval(task,monkeypatch):
    from modelcrew import reviews
    with Workflow() as w:
        act(w,task)
        s=act(w,task,kind='revise_interpretation',request='edit',revision=1,reason='TEST_ONLY new explanation')
        assert s['result']['review']['integrity_status']=='passed'
        monkeypatch.setattr(reviews,'artifact_status',lambda a:'missing')
        with pytest.raises(WorkflowError,match='fresh review'):act(w,task,kind='result',request='approve-missing',revision=2,reason='TEST_ONLY acknowledge unknown')
        assert not w.task(task)['result_approved']

def test_recorded_artifact_remains_available_when_source_is_overwritten(task):
    from modelcrew.inputs import file_hash
    from modelcrew.reviews import artifact_status
    folder=ROOT/'stage-b/runs'/('entry-artifact-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    p=folder/'code.py';p.write_text('# TEST_ONLY '+uuid.uuid4().hex,encoding='utf-8')
    artifact={'path':str(p),'sha256':file_hash(p),'role':'code'}
    kwargs=dict(version=1,kind='code',text='TEST_ONLY preserved source',actor='TEST_SIMULATED_USER',request_id='code-snapshot',artifacts=[artifact])
    with Workflow() as w:
        first=w.record_entry(task,**kwargs)
        p.write_text('# TEST_ONLY overwritten',encoding='utf-8')
        assert w.record_entry(task,**kwargs)==first
        saved=w.version_dossier(task)['entries']['code'][0]['body']['artifacts'][0]
        assert saved['origin_path']==str(p) and saved['integrity']=='verified'

def test_manifest_backend_selected_and_resumed_in_fresh_cli(example):
    from modelcrew.contracts import digest
    from modelcrew.inputs import file_hash
    folder=ROOT/'stage-b/runs'/('manifest-test-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    artifact=folder/'fixed.json';artifact.write_text('{"TEST_ONLY":true}',encoding='utf-8')
    manifest=folder/'manifest.json';manifest.write_text(json.dumps({'contract_sha256':digest(example),'artifacts':[{'path':str(artifact),'sha256':file_hash(artifact),'role':'fixed_fixture'}],'description':'TEST_ONLY fixture'}),encoding='utf-8')
    config={'manifest_path':str(manifest),'manifest_sha256':file_hash(manifest)};task='test-manifest-'+uuid.uuid4().hex
    with Workflow() as w:
        s=w.create(task,example,project='automated-tests',executor_key='manifest-fixture',executor_config=config)
        assert not s['execution'] and not s['execution_attempts']
    p=subprocess.run([sys.executable,'-m','modelcrew','act',task,'--kind','model','--version','1','--actor','TEST_SIMULATED_USER','--request-id','cli-manifest','--decision','approve'],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=30)
    assert p.returncode==0,p.stderr;s=json.loads(p.stdout)
    assert s['execution']['backend_key']=='manifest-fixture' and s['execution']['mode']=='fixture'
    assert s['result']['review']['status']=='unknown' and len(s['execution_receipts'])==1
    assert [a['phase'] for a in s['execution_attempts']]==['started','succeeded']
    with Workflow() as w:
        assert w.resume(task)['task']['phase']=='WAITING_RESULT_APPROVAL'
        assert w.inspect(task)['contract']['executor_key']=='manifest-fixture'

def test_receipt_survives_execution_registration_failure_without_backend_replay(example,monkeypatch):
    from modelcrew.executors import receipt,HistoricalFixture
    class Backend:
        replay_safe=True
        calls=0
        def execute(self,request):self.calls+=1;return receipt(request,HistoricalFixture().artifacts(request.contract))
    backend=Backend();task='test-receipt-crash-'+uuid.uuid4().hex
    with Workflow(executors={'test-receipt':backend}) as w:
        w.create(task,example,project='automated-tests',executor_key='test-receipt')
        original=w._event
        def event(*args):
            if args[1]=='execution_receipt_registered':raise RuntimeError('TEST publication crash')
            return original(*args)
        monkeypatch.setattr(w,'_event',event)
        with pytest.raises(RuntimeError,match='publication crash'):act(w,task)
        assert w.db.execute('SELECT count(*) AS n FROM mc_backend_receipts WHERE task_id=%s',(task,)).fetchone()['n']==1
        assert not w.db.execute('SELECT 1 FROM mc_executions WHERE task_id=%s',(task,)).fetchone()
    # No injected backend is available in this new instance; durable receipt is sufficient.
    with Workflow() as w:
        s=w.resume(task);assert s['task']['phase']=='WAITING_RESULT_APPROVAL'
        assert len(s['execution_receipts'])==1 and len(s['execution_attempts'])==2 and backend.calls==1
        w.resume(task);assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_unsafe_backend_requires_recovery_instead_of_blind_reexecution(example):
    class Backend:
        replay_safe=False
        calls=0
        def execute(self,request):self.calls+=1;raise RuntimeError('TEST dispatch acknowledgement lost')
    backend=Backend();task='test-unknown-dispatch-'+uuid.uuid4().hex
    with Workflow(executors={'unknown-backend':backend}) as w:
        w.create(task,example,project='automated-tests',executor_key='unknown-backend')
        with pytest.raises(RuntimeError,match='acknowledgement lost'):act(w,task)
        with pytest.raises(WorkflowError,match='outcome unknown'):w.resume(task)
        assert backend.calls==1 and w.task(task)['phase']=='SOLVING'
        assert [a['phase'] for a in w.inspect(task)['execution_attempts']]==['started','unknown']
        assert not w.task(task)['result_approved']

def test_wrong_backend_receipt_is_rejected_and_failure_recorded(example):
    from modelcrew.executors import receipt,HistoricalFixture
    class Wrong:
        replay_safe=True
        def execute(self,request):
            value=receipt(request,HistoricalFixture().artifacts(request.contract));value['contract_sha256']='0'*64;return value
    task='test-bad-receipt-'+uuid.uuid4().hex
    with Workflow(executors={'wrong':Wrong()}) as w:
        w.create(task,example,project='automated-tests',executor_key='wrong')
        with pytest.raises(ValueError,match='binding mismatch'):act(w,task)
        s=w.inspect(task);assert s['execution'] is None and s['execution_attempts'][-1]['phase']=='failed'
        assert not s['execution_receipts']

def test_execution_settings_change_requires_new_version_and_confirmation(task,example):
    with Workflow() as w:
        with pytest.raises(WorkflowError,match='new contract version'):act(w,task,executor_key='historical-fixture')
        changed=copy.deepcopy(example);changed['risks'].append('TEST_ONLY configuration revision')
        s=act(w,task,kind='revise_model',contract=changed,reason='TEST_ONLY revision',executor_key='historical-fixture',executor_config={})
        assert s['task']['current_version']==2 and not s['task']['model_approved']
        assert s['contract']['executor_key']=='historical-fixture' and s['contract']['executor_config']=={}

def test_interpretation_claims_pass_fail_and_preserve_execution(task,example):
    from modelcrew.reviews import render_claims
    with Workflow() as w:
        first=act(w,task)
        array=next(a for a in first['execution']['artifacts'] if a['origin_path'].endswith('trajectories.npz'))
        claims={'schema_version':'1.0.0','claims':[{'id':'head_speed_at_zero','source':{'artifact_sha256':array['sha256'],'output_id':'arrays','field':'speed_m_s','selector':{'index':[0,0]}},'operator':'eq','expected':1.,'unit':'m/s','abs_tolerance':1e-9}]}
        s=act(w,task,kind='revise_interpretation',request='structured-good',revision=1,reason='TEST_ONLY verify head speed',claims=claims,structured_only=True)
        assert s['result']['review']['status']=='passed' and s['task']['interpretation']==render_claims(claims)
        assert s['task']['execution_id']==first['task']['execution_id'] and s['task']['result_revision']==2
        act(w,task,kind='result',request='approve-structured',revision=2)
        claims['claims'][0]['expected']=999.
        s=act(w,task,kind='revise_interpretation',request='structured-bad',revision=2,reason='TEST_ONLY wrong claim',claims=claims,structured_only=True)
        assert s['result']['review']['status']=='failed' and not s['task']['result_approved']
        with pytest.raises(WorkflowError,match='Failed review'):act(w,task,kind='result',request='approve-bad',revision=3)
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1

def test_backend_receipts_and_attempts_are_immutable(task):
    import psycopg
    with Workflow() as w:
        act(w,task)
        for table in ['mc_backend_receipts','mc_backend_attempts']:
            with pytest.raises(psycopg.Error,match='immutable'):w.db.execute(f'DELETE FROM {table} WHERE task_id=%s',(task,))

def test_backend_recovery_query_resolves_unknown_without_second_dispatch(example):
    from modelcrew.executors import receipt,HistoricalFixture
    class Recoverable:
        replay_safe=False
        dispatches=0
        recoveries=0
        def execute(self,request):self.dispatches+=1;raise RuntimeError('TEST ack lost')
        def recover(self,request):
            self.recoveries+=1
            return receipt(request,HistoricalFixture().artifacts(request.contract),details={'recovered_by_operation_key':request.operation_key})
    backend=Recoverable();task='test-backend-recovery-'+uuid.uuid4().hex
    with Workflow(executors={'recoverable':backend}) as w:
        w.create(task,example,project='automated-tests',executor_key='recoverable')
        with pytest.raises(RuntimeError,match='ack lost'):act(w,task)
    with Workflow(executors={'recoverable':backend}) as w:
        s=w.resume(task)
        assert s['task']['phase']=='WAITING_RESULT_APPROVAL'
        assert backend.dispatches==1 and backend.recoveries==1
        assert s['execution_receipts'][0]['payload']['details']['recovered_by_operation_key']==s['execution']['operation_key']
        w.resume(task);assert backend.dispatches==1 and backend.recoveries==1

def test_manifest_contract_mismatch_records_failure_and_no_result(example):
    from modelcrew.inputs import file_hash
    folder=ROOT/'stage-b/runs'/('bad-manifest-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    path=folder/'manifest.json';path.write_text(json.dumps({'contract_sha256':'0'*64,'artifacts':[],'description':'TEST_ONLY wrong binding'}),encoding='utf-8')
    task='test-bad-manifest-'+uuid.uuid4().hex
    with Workflow() as w:
        w.create(task,example,project='automated-tests',executor_key='manifest-fixture',executor_config={'manifest_path':str(path),'manifest_sha256':file_hash(path)})
        with pytest.raises(ValueError,match='binding mismatch'):act(w,task)
        s=w.inspect(task)
        assert s['task']['model_approved'] and s['task']['phase']=='SOLVING' and s['result'] is None
        assert s['execution_attempts'][-1]['phase']=='failed' and not s['execution_receipts']

def test_reviewed_run_backend_preserves_solver_mode_and_requires_validator(example,monkeypatch):
    from modelcrew import solver_validation
    from modelcrew.inputs import file_hash
    folder=ROOT/'stage-b/runs'/('reviewed-backend-test-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    path=folder/'TEST_ONLY.json';path.write_text('{"test":true}',encoding='utf-8')
    calls=[]
    def validate_existing(run,contract):
        calls.append((run,contract));return {'passed':True,'TEST_ONLY_mock_numeric_validator':True},[{'path':str(path),'sha256':file_hash(path),'role':'test_evidence'}]
    monkeypatch.setattr(solver_validation,'validate_run',validate_existing)
    task='test-reviewed-mode-'+uuid.uuid4().hex
    with Workflow() as w:
        w.create(task,example,project='automated-tests',executor_key='reviewed-run',executor_config={'run_dir':str(folder)})
        assert not calls
        s=act(w,task)
        assert len(calls)==1 and calls[0][1]==example
        assert s['execution']['mode']=='solver' and s['execution']['backend_key']=='reviewed-run'
        assert s['result']['review']['status']=='passed' and not s['task']['result_approved']
        w.resume(task);assert len(calls)==1

def test_executor_authorization_uses_durable_model_approval_and_exact_inputs(task,example):
    from modelcrew.docker_executor import DockerExecutor,ExecutorError
    with Workflow() as w:
        contract=w.inspect(task)['contract']
        job={'authorization':{'mode':'workflow','task_id':task,'version':1,'contract_sha256':contract['sha256']},
             'inputs':[{'input_id':i['id'],'sha256':i['sha256']} for i in example['inputs']]}
        executor=DockerExecutor()
        with pytest.raises(ExecutorError,match='approval required'):executor.authorize(job)
        act(w,task)
        executor.authorize(job)
        bad=copy.deepcopy(job);bad['inputs'][0]['sha256']='wrong'
        with pytest.raises(ExecutorError,match='snapshot differs'):executor.authorize(bad)
        changed=copy.deepcopy(example);changed['risks'].append('TEST_ONLY stale executor authorization')
        act(w,task,kind='revise_model',request='executor-stale',reason='TEST_ONLY revision',contract=changed)
        with pytest.raises(ExecutorError,match='approval required'):executor.authorize(job)

def test_D4_submission_keeps_user_gate_and_rechecks_P2_on_result_approval(task,monkeypatch):
    from modelcrew import full_result,workflow
    monkeypatch.setattr(workflow,'snapshot_artifacts',lambda items:items)
    execution_id=str(uuid.uuid4());name='simulated-D4-'+uuid.uuid4().hex
    calls=[];blocked=[False]
    def validated(w,identifier,version,folder):
        calls.append((identifier,version))
        if blocked[0]:raise ValueError('Frozen P2 snapshot changed')
        return {'passed':True,'review_kind':'d4_P2_review','execution_id':execution_id,'result_revision':1,
                'source_run':'stage-d/runs/full/'+name,'P2_receipt_sha256':'0'*64},[
                {'path':'TEST_ONLY_NOT_REAL_D4_ARTIFACT','sha256':'0'*64,'role':'simulated_D4_transaction_test'}]
    monkeypatch.setattr(full_result,'validate_full_run',validated)
    with Workflow() as w:
        pending=act(w,task,defer_execution=True)
        assert pending['execution'] is None
        state=w.attach_solver_result(task,version=1,run_dir=ROOT/'stage-d/runs/full'/name)
        assert str(state['task']['execution_id'])==execution_id and state['task']['result_revision']==1
        assert state['task']['phase']=='WAITING_RESULT_APPROVAL' and not state['task']['result_approved']
        assert state['result']['review']['kind']=='d4_P2_review'
        assert len(state['execution_attempts'])==0
        blocked[0]=True
        with pytest.raises(ValueError,match='P2 snapshot changed'):
            act(w,task,kind='result',revision=1,request='D4-failed-confirmation')
        assert not w.task(task)['result_approved']
        blocked[0]=False
        act(w,task,kind='result',revision=1,request='D4-good-confirmation')
        assert w.task(task)['phase']=='COMPLETED' and len(calls)==3


def test_D4_failed_validation_cannot_create_result(task,monkeypatch):
    from modelcrew import full_result
    def failed(*args):raise ValueError('Independent P2 PASS required')
    monkeypatch.setattr(full_result,'validate_full_run',failed)
    with Workflow() as w:
        act(w,task,defer_execution=True)
        with pytest.raises(ValueError,match='P2 PASS'):
            w.attach_solver_result(task,version=1,run_dir=ROOT/'stage-d/runs/full'/('simulated-D4-fail-'+uuid.uuid4().hex))
        assert w.task(task)['result_revision']==0 and w.inspect(task)['execution'] is None

def test_pending_code_creation_is_pending_without_fixture_dispatch(example):
    identifier='test-pending-code-'+uuid.uuid4().hex
    with Workflow() as w:
        state=w.create(identifier,example,project='automated-tests',executor_key='pending-code')
        assert state['task']['phase']=='WAITING_MODEL_APPROVAL' and state['execution'] is None
        event=w.db.execute("SELECT payload FROM mc_events WHERE task_id=%s AND kind='created'",(identifier,)).fetchone()['payload']
        assert event['mode']=='pending' and event['executor_key']=='pending-code'
        state=w.action(identifier,actor='TEST_SIMULATED_USER',request_id='deferred',version=1,kind='model',decision='approve',defer_execution=True)
        assert state['task']['model_approved'] and state['execution'] is None
        assert not w.db.execute('SELECT 1 FROM mc_backend_attempts WHERE task_id=%s',(identifier,)).fetchone()
