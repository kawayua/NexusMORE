"""Synthetic lifecycle checks; real Writer receipts are exercised by E1 live audit."""
from contextlib import nullcontext
from copy import deepcopy
import json
import uuid

import pytest
from pydantic import ValidationError
from modelcrew import assembly_runtime as ar
from modelcrew.collaboration import sha_file
from modelcrew.workflow import WorkflowError


class Result:
    def __init__(self, value): self.value = value
    def fetchone(self): return self.value


class MemoryWorkflow:
    def __init__(self): self.rows = {}; self.db = self
    def lock(self, key): return nullcontext()
    def require_project(self, project): return {'id': project}
    def execute(self, sql, args):
        if sql.startswith('INSERT'):
            key, project, request, request_hash, payload = args
            self.rows[key] = {'id': key, 'project_id': project, 'request_id': request,
                              'request_sha256': request_hash, 'payload': deepcopy(payload.obj)}
            return Result(None)
        if 'request_id=%s' in sql:
            return Result(next((r for r in self.rows.values() if (r['project_id'],r['request_id']) == args),None))
        row = self.rows.get(args[0])
        return Result(row if row and row['project_id'] == args[1] else None)


@pytest.fixture
def setup_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, 'ROOT', tmp_path)
    monkeypatch.setattr(ar, 'writing_context', lambda: {'workflow_sha256': 'a'*64})
    values = {}
    for q in ['q1','q2']:
        path = tmp_path/(q+'.md'); path.write_text('SYNTHETIC '+q,encoding='utf-8')
        values[q] = {'question_id':q, 'task_id':'task-'+q, 'run_id':str(uuid.uuid4()),
                     'source_project_id':'p', 'files':{q+'.md':sha_file(path)}, 'binding':{'version':1}}
    def approved(w, chapter, project, **kwargs):
        if values[chapter.question_id].get('blocked'):
            raise WorkflowError('Source approval is stale')
        return deepcopy(values[chapter.question_id])
    monkeypatch.setattr(ar, 'approved_chapter', approved)
    req = {'request_id':'test-1','actor':'TEST_ONLY','required_questions':['q1','q2'],
           'chapters':[{k:v[k] for k in ['question_id','task_id','run_id']} for v in values.values()]}
    return MemoryWorkflow(),req,values


def test_freeze_restart_and_idempotency(setup_run):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    assert a['phase']=='ASSEMBLY_INPUTS_FROZEN'
    assert not a['new_export_created'] and not a['new_W2_performed']
    assert ar.start(w,'p',**req)==a
    assert ar.status(w,'p',a['run_id'])==a
    assert len(w.rows)==1
    with pytest.raises(WorkflowError,match='different inputs'):
        ar.start(w,'p',**{**req,'actor':'DIFFERENT'})


def test_changed_source_only_invalidates_affected_question(setup_run):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    values['q2']['blocked']=True
    status=ar.status(w,'p',a['run_id'])
    assert status['phase']=='STALE_INPUTS'
    assert status['affected_questions']==['q2']
    assert status['preserved_questions']==['q1']
    assert 'W2' in status['invalidated_products']


def test_frozen_bytes_detected_without_altering_live_sources(setup_run):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    p=w.rows[a['run_id']]['payload']['files'][0]['snapshot']
    (ar.ROOT/p).write_text('TAMPERED',encoding='utf-8')
    status=ar.status(w,'p',a['run_id'])
    assert status['phase']=='STALE_INPUTS' and status['affected_questions']==['q1']
    assert (ar.ROOT/'q1.md').read_text(encoding='utf-8')=='SYNTHETIC q1'


@pytest.mark.parametrize('name',['input-manifest.json','writer-context.json'])
def test_missing_global_evidence_invalidates_all(setup_run,name):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    (ar.folder(a['run_id'])/name).unlink()
    status=ar.status(w,'p',a['run_id'])
    assert status['phase']=='STALE_INPUTS'
    assert status['affected_questions']==['q1','q2']


def test_policy_change_detected(setup_run,monkeypatch):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    monkeypatch.setattr(ar,'writing_context',lambda:{'workflow_sha256':'b'*64})
    assert ar.status(w,'p',a['run_id'])['affected_questions']==['q1','q2']


def test_new_revision_preserves_history_and_unaffected_question(setup_run):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    values['q2']['binding']['version']=2
    b=ar.start(w,'p',**{**req,'request_id':'test-2','previous_run_id':a['run_id']})
    assert b['update_impact']['changed_questions']==['q2']
    assert b['update_impact']['preserved_questions']==['q1']
    assert not b['update_impact']['solver_rerun_started']
    assert ar.status(w,'p',a['run_id'])['phase']=='STALE_INPUTS'
    assert ar.folder(a['run_id']).exists() and len(w.rows)==2


def test_partial_run_is_explicit(setup_run):
    w,req,values=setup_run
    req['chapters']=req['chapters'][:1]
    with pytest.raises(ValidationError): ar.start(w,'p',**req)
    a=ar.start(w,'p',**{**req,'allow_partial':True})
    assert a['phase']=='PARTIAL_INPUTS_FROZEN' and a['missing_questions']==['q2']


@pytest.mark.parametrize('change',[
    {'request_id':'../escape'},
    {'required_questions':['q1','q1']},
    {'required_questions':['q1']},
    {'required_questions':['q1','../q2']},
    {'chapters':[]},
])
def test_invalid_input_rejected(setup_run,change):
    w,req,values=setup_run
    with pytest.raises(ValidationError): ar.start(w,'p',**{**req,**change})
    assert not w.rows


def test_duplicate_tasks_rejected(setup_run):
    w,req,values=setup_run
    req['chapters'][1]['task_id']=req['chapters'][0]['task_id']
    with pytest.raises(ValidationError): ar.start(w,'p',**req)


def test_source_change_during_freeze_is_rejected(setup_run):
    w,req,values=setup_run
    (ar.ROOT/'q2.md').write_text('MUTATION',encoding='utf-8')
    with pytest.raises(WorkflowError,match='during freeze'): ar.start(w,'p',**req)
    assert not w.rows


def test_project_isolation(setup_run):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    with pytest.raises(WorkflowError,match='Unknown assembly'):
        ar.status(w,'other',a['run_id'])


def test_no_input_change_does_not_invalidate():
    a=[{'question_id':'q1','binding':{'v':1}}]
    assert ar.impact(a,deepcopy(a))['invalidated_products']==[]

def test_shared_source_copied_once(setup_run):
    w,req,values=setup_run
    values['q2']['files']['q1.md']=values['q1']['files']['q1.md']
    a=ar.start(w,'p',**req)
    assert a['phase']=='ASSEMBLY_INPUTS_FROZEN'
    paths=w.rows[a['run_id']]['payload']['files']
    assert len(paths)==3
    assert len({p['snapshot'] for p in paths})==2


def test_document_policy_change_with_unchanged_workflow_hash(setup_run,monkeypatch):
    w,req,values=setup_run
    a=ar.start(w,'p',**req)
    monkeypatch.setattr(ar,'writing_context',lambda:{'workflow_sha256':'a'*64,'documents':['CHANGED']})
    assert ar.status(w,'p',a['run_id'])['phase']=='STALE_INPUTS'


def test_cross_project_source_requires_explicit_declaration():
    class W:
        def task(self,task): return {'project_id':'other'}
    chapter=ar.ChapterInput(question_id='q1',task_id='t',run_id='r')
    with pytest.raises(WorkflowError,match='explicitly declared'):
        ar.approved_chapter(W(),chapter,'p')

def test_http_assembly_routes_forward_requests(setup_run):
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    w,req,values=setup_run
    class Adapter:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def start_assembly(self,project,**kwargs): return ar.start(w,project,**kwargs)
        def assembly_status(self,project,run_id): return ar.status(w,project,run_id)
    with TestClient(create_app(Adapter)) as client:
        answer=client.post('/projects/p/assembly-runs',json=req)
        assert answer.status_code==200
        run_id=answer.json()['run_id']
        assert client.get('/projects/p/assembly-runs/'+run_id).json()==answer.json()
        assert client.post('/projects/p/assembly-runs',json={**req,'chapters':[]}).status_code==422

@pytest.fixture
def editorial_run(setup_run,monkeypatch):
    from modelcrew import assembly_binding as binding
    from modelcrew.contracts import digest
    w,req,values=setup_run
    policy=ar.ROOT/'resources/paper/chinese-modeling-policy.json';policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({'policy_version':'1','figures':{'minimum_formal':8}}),encoding='utf-8')
    old={'workflow_sha256':'a'*64,'workflow':{'workflow_version':'1','must_load':[policy.relative_to(ar.ROOT).as_posix()]},
         'documents':[{'path':policy.relative_to(ar.ROOT).as_posix(),'sha256':sha_file(policy),'text':policy.read_text(encoding='utf-8')}]}
    for v in values.values():
        path=ar.ROOT/f"stage-d/runs/runtime/{v['run_id']}/writer-context.json";path.parent.mkdir(parents=True)
        path.write_text(json.dumps(old),encoding='utf-8')
        v['files'].update({path.relative_to(ar.ROOT).as_posix():sha_file(path),policy.relative_to(ar.ROOT).as_posix():sha_file(policy)})
    monkeypatch.setattr(ar,'writing_context',lambda:deepcopy(old))
    first=ar.start(w,'p',**req)
    current=deepcopy(old);current['workflow_sha256']='b'*64;current['workflow']['layout_requirements']={'single_page':True}
    monkeypatch.setattr(ar,'writing_context',lambda:deepcopy(current));monkeypatch.setattr(binding,'writing_context',lambda:deepcopy(current))
    request={'request_id':'rebind-1','actor':'TEST_ONLY','reason':'SYNTHETIC editorial migration',
             'expected_previous_context':digest(old),'expected_current_context':digest(current)}
    return w,first,request,values,current


def test_editorial_rebind_creates_new_version_and_preserves_old_manifest(editorial_run):
    from modelcrew import assembly_binding as binding
    w,first,request,values,current=editorial_run
    original=(ar.folder(first['run_id'])/'input-manifest.json').read_bytes()
    result=binding.rebind(w,'p',first['run_id'],**request)
    assert result['run_id']!=first['run_id'] and result['phase']=='ASSEMBLY_INPUTS_FROZEN'
    assert result['preserved_questions']==['q1','q2'] and not result['combined_manuscript_approved']
    assert binding.rebind(w,'p',first['run_id'],**request)==result and len(w.rows)==2
    assert ar.status(w,'p',first['run_id'])['phase']=='STALE_INPUTS'
    assert (ar.folder(first['run_id'])/'input-manifest.json').read_bytes()==original
    with pytest.raises(WorkflowError,match='reused'):
        binding.rebind(w,'p',first['run_id'],**{**request,'reason':'different'})
    frozen=w.rows[result['run_id']]['payload']['files'][0]['snapshot'];(ar.ROOT/frozen).write_text('TAMPERED',encoding='utf-8')
    assert ar.status(w,'p',result['run_id'])['phase']=='STALE_INPUTS'


def test_editorial_rebind_cannot_ignore_upstream_or_hash_failures(editorial_run):
    from modelcrew import assembly_binding as binding
    w,first,request,values,current=editorial_run
    with pytest.raises(WorkflowError,match='hashes'):
        binding.rebind(w,'p',first['run_id'],**{**request,'expected_current_context':'0'*64})
    values['q2']['blocked']=True
    with pytest.raises(WorkflowError,match='stale'):
        binding.rebind(w,'p',first['run_id'],**request)
    assert len(w.rows)==1

def test_http_editorial_rebinding_is_explicit_and_idempotent(editorial_run):
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    from modelcrew.assembly_binding import rebind
    w,first,request,_,_=editorial_run
    class Adapter:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def rebind_assembly(self,project,run_id,**kwargs):return rebind(w,project,run_id,**kwargs)
    url='/projects/p/assembly-runs/'+first['run_id']+'/rebindings'
    with TestClient(create_app(Adapter)) as client:
        initial=client.post(url,json=request);assert initial.status_code==200
        assert client.post(url,json=request).json()==initial.json()
        assert client.post(url,json={**request,'expected_current_context':'missing'}).status_code==422
        assert client.post(url,json={**request,'reason':'different'}).status_code==409

def test_mixed_policy_revision_freezes_each_question_without_path_collision(setup_run, monkeypatch):
    w,req,values=setup_run
    policy=ar.ROOT/'resources/paper/policy.json';policy.parent.mkdir(parents=True)
    policy.write_text('old approved policy',encoding='utf-8')
    name=policy.relative_to(ar.ROOT).as_posix()
    for v in values.values():v['files'][name]=sha_file(policy)
    old=ar.start(w,'p',**req);prior=w.rows[old['run_id']]
    prior['payload']['context_rebinding']=True
    from modelcrew import assembly_binding
    def historical(payload,chapter):
        return {'context':{},'files':{x['source']:x for x in payload['files'] if x['question_id']==chapter['question_id']}}
    monkeypatch.setattr(assembly_binding,'chapter_context',historical)
    policy.write_text('new approved policy',encoding='utf-8')
    values['q1']['files'][name]=sha_file(policy);values['q1']['run_id']=str(uuid.uuid4())
    newreq={**req,'request_id':'mixed-policy','previous_run_id':old['run_id'],
            'chapters':[{k:v[k] for k in ['question_id','task_id','run_id']} for v in values.values()]}
    new=ar.start(w,'p',**newreq);row=w.rows[new['run_id']]
    assert row['payload']['historical_chapters']==['q2']
    assert new['update_impact']['changed_questions']==['q1']
    assert new['update_impact']['preserved_questions']==['q2']
    assert (ar.snapshot_root(row,'q1')/name).read_text(encoding='utf-8')=='new approved policy'
    assert (ar.snapshot_root(row,'q2')/name).read_text(encoding='utf-8')=='old approved policy'
    assert ar.status(w,'p',new['run_id'])['phase']=='ASSEMBLY_INPUTS_FROZEN'
