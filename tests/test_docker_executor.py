"""Executor boundary tests without running generated code on the host."""
import base64,json
from pathlib import Path
import pytest
from modelcrew.code_executor_mcp import ExecutionTools,definitions
from modelcrew.docker_executor import DockerExecutor,ExecutorError,Limits,register_job,relative_name,sha,atomic

@pytest.fixture
def job(tmp_path):
    code=tmp_path/'code.py';code.write_text("print('TEST_ONLY')",encoding='utf-8')
    root=tmp_path/'executor'
    value=register_job(root,'test-job',code,[],{'mode':'verification'})
    return root,value

@pytest.mark.parametrize('name',['../outside','/absolute','a/../b','C:/secret','a\\b','a//b','./x'])
def test_archive_rejects_traversal_names(name):
    with pytest.raises(ExecutorError):relative_name(name)

def test_registered_code_is_immutable(job):
    root,value=job
    (root/'jobs/test-job/solver.py').write_text('changed',encoding='utf-8')
    with pytest.raises(ExecutorError,match='changed'):DockerExecutor(root).job('test-job')

def test_input_hash_and_path_checked_before_registration(tmp_path):
    code=tmp_path/'x.py';code.write_text('pass')
    source=tmp_path/'data';source.write_bytes(b'data')
    with pytest.raises(ExecutorError,match='hash'):register_job(tmp_path/'one','test',code,[{'name':'data','path':str(source),'sha256':'wrong'}],{'mode':'verification'})
    with pytest.raises(ExecutorError):register_job(tmp_path/'two','test',code,[{'name':'../data','path':str(source),'sha256':sha(b'data')}],{'mode':'verification'})
    assert not (tmp_path/'one/jobs/test').exists()

def test_verification_cannot_bypass_default_server(job):
    root,value=job
    with pytest.raises(ExecutorError,match='disabled'):DockerExecutor(root).authorize(value)

def test_archive_size_and_duplicate_paths_are_bounded(tmp_path):
    engine=DockerExecutor(tmp_path);run=tmp_path/'runs/test';run.mkdir(parents=True)
    item={'name':'result.json','size_bytes':2,'base64':base64.b64encode(b'{}').decode()}
    result=engine._archive(run,[item],Limits().model_dump())
    assert result[0]['sha256']==sha(b'{}')
    with pytest.raises(ValueError):engine._archive(run,[item,item],Limits().model_dump())
    with pytest.raises(ValueError):engine._archive(run,[{**item,'size_bytes':3}],Limits().model_dump())
    with pytest.raises(ExecutorError):engine._archive(run,[{**item,'name':'../outside'}],Limits().model_dump())

def test_cached_receipt_must_match_job(job):
    root,value=job;run=root/'runs/test-job';run.mkdir(parents=True)
    atomic(run/'result.json',{'job_sha256':'wrong'})
    with pytest.raises(ExecutorError,match='different job'):DockerExecutor(root).status('test-job')

def test_tool_does_not_accept_code_paths_or_approval_flags(tmp_path):
    class Forbidden:
        def execute(self,*args):raise AssertionError('Invalid request dispatched')
    tool=ExecutionTools(Forbidden(),log_path=tmp_path/'calls.jsonl')
    for args in [{'job_id':'test','code':'print(1)'},{'job_id':'test','approved':True},{'job_id':'../other'}]:
        result=tool.invoke('code_execute',args)
        assert result.isError and result.structuredContent['error']['code']=='invalid_request'
    assert all(d.inputSchema['additionalProperties'] is False for d in definitions())

def test_execution_failure_is_distinct_from_tool_failure(tmp_path):
    class Fixed:
        def execute(self,job_id):return {'run_id':job_id,'job_sha256':'TEST','status':'code_error','failure_domain':'code','artifacts':[]}
    result=ExecutionTools(Fixed(),log_path=tmp_path/'calls.jsonl').invoke('code_execute',{'job_id':'test'})
    assert not result.isError and result.structuredContent['data']['status']=='code_error'

def test_audit_failure_prevents_dispatch(tmp_path):
    class Forbidden:
        def execute(self,*args):raise AssertionError('Unlogged dispatch')
    result=ExecutionTools(Forbidden(),log_path=tmp_path).invoke('code_execute',{'job_id':'test'})
    assert result.isError and result.structuredContent['error']['code']=='audit_or_storage_unavailable'

def test_status_never_reexecutes(job):
    root,value=job
    with pytest.raises(ExecutorError,match='not been dispatched'):DockerExecutor(root).status('test-job')
    assert not (root/'runs/test-job').exists()


def test_concurrent_server_cannot_claim_same_run(job):
    import portalocker
    root,value=job;path=root/'locks/test-job.lock';path.parent.mkdir(parents=True)
    with portalocker.Lock(str(path),mode='a',timeout=1):
        with pytest.raises(ExecutorError,match='in progress'):
            DockerExecutor(root,allow_test_jobs=True).execute('test-job')
    assert not (root/'runs/test-job').exists()


def test_cached_receipt_rechecks_archived_bytes(job):
    root,value=job;run=root/'runs/test-job';run.mkdir(parents=True)
    artifact=run/'output.json';artifact.write_bytes(b'changed')
    atomic(run/'result.json',{'job_sha256':value['job_sha256'],'artifacts':[{'path':str(artifact.relative_to(root)),'sha256':sha(b'original'),'size_bytes':len(b'original')}]})
    with pytest.raises(ExecutorError,match='missing or changed'):
        DockerExecutor(root).status('test-job')


def test_status_recovery_enforces_deadline_after_monitor_death(job,monkeypatch):
    root,value=job;run=root/'runs/test-job';run.mkdir(parents=True)
    atomic(run/'claim.json',{'job_sha256':value['job_sha256'],'container_name':'TEST_CONTAINER','started_at':0})
    engine=DockerExecutor(root);calls=[]
    monkeypatch.setattr(engine,'inspect',lambda name,job:{'State':{'Running':True}})
    monkeypatch.setattr(engine,'docker',lambda *args,**kwargs:calls.append(args))
    monkeypatch.setattr(engine,'_finish',lambda run,job,info,forced_status=None:{'status':forced_status})
    result=engine.status('test-job')
    assert result['status']=='timeout' and calls==[('kill','TEST_CONTAINER')]


def test_pending_receipt_cannot_publish_wrong_job(job):
    root,value=job;run=root/'runs/test-job';run.mkdir(parents=True)
    with pytest.raises(ExecutorError,match='differs from registered'):
        DockerExecutor(root)._publish(run,value,{'job_sha256':'wrong'})
    assert not (run/'result.json').exists()
