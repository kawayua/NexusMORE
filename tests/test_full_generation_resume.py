"""Full-stage source transport and rework retain valid independent P1 only."""
import copy
import hashlib
import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from modelcrew import hand_runtime as hr,code_revision as cr
from modelcrew.model_client import ModelCallError
from modelcrew.workflow import WorkflowError


@pytest.fixture
def full_source(tmp_path,monkeypatch):
    minimal=tmp_path/'minimal.py';minimal.write_text('raise RuntimeError("not host executed")\n',encoding='utf-8')
    source=tmp_path/'full.py';source.write_text('raise RuntimeError("also not host executed")\n',encoding='utf-8')
    folder=tmp_path/'run';folder.mkdir()
    review={'status':'PASS','receipt_sha256':'a'*64,'snapshot_sha256':'b'*64}
    row={'id':str(uuid.uuid4()),'task_id':'fixture','version':6,'hand':'coding','phase':'GENERATE_FULL','payload':{
        'attempt':2,'retries':2,'ops':{},'jobs':{},'binding':{},'sealed':{},
        'minimal_code_path':'minimal.py','reviews':{'P1-0':review},'accepted_reviews':{'P1':'P1-0'}}}
    w=SimpleNamespace(task=lambda task:{'result_revision':0})
    monkeypatch.setattr(cr,'ROOT',tmp_path);monkeypatch.setattr(hr,'load',lambda *a:row)
    monkeypatch.setattr(hr,'guard',lambda *a:None);monkeypatch.setattr(hr,'run_folder',lambda r:folder)
    monkeypatch.setattr(hr,'rel',lambda p:p.relative_to(tmp_path).as_posix())
    monkeypatch.setattr(hr,'seal',lambda *a:None);monkeypatch.setattr(hr,'author',lambda *a:None)
    monkeypatch.setattr(hr,'save',lambda w,r,phase:r.update(phase=phase));monkeypatch.setattr(hr,'status',lambda w,t,r:{'phase':row['phase']})
    store=SimpleNamespace(load=lambda *a:object(),accept_review=lambda *a:'a'*64)
    monkeypatch.setattr(hr,'CollaborationStore',lambda *a:store)
    monkeypatch.setattr(cr,'grant',lambda *a:None)
    req={'stage':'full','code_path':'full.py','code_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'previous_code_sha256':hashlib.sha256(minimal.read_bytes()).hexdigest(),'rationale':'Preserve synthetic P1, full execution and new P2 still required.'}
    return w,row,req,store


def test_first_full_file_submission_needs_no_exhausted_repair_grant(full_source):
    w,row,req,store=full_source;prepared=cr.prepare(w,'fixture',row['id'],req)
    assert prepared['prepared_full_source'] and not prepared['initial_prepared_source']
    result=cr.submit(w,'fixture',row['id'],prepared,'first-full')
    assert result['phase']=='EXECUTE_FULL'
    p=row['payload'];assert p['attempt']==p['retries']==2 and p['accepted_reviews']=={'P1':'P1-0'}
    record=p['coder_code_revisions']['first-full'];assert record['origin']=='prepared_coder_source' and record['provider_call'] is False
    assert record['delegated_repair'] is None
    assert cr.submit(w,'fixture',row['id'],prepared,'first-full')==result


@pytest.mark.parametrize('change',['no_pass','corrupt_receipt','wrong_base','claimed','already_full','already_job'])
def test_full_submission_rejects_invalid_or_claimed_baseline(full_source,change):
    w,row,req,store=full_source;p=row['payload']
    if change=='no_pass':p['accepted_reviews']={}
    if change=='corrupt_receipt':store.accept_review=lambda *a:'c'*64
    if change=='wrong_base':req['previous_code_sha256']='0'*64
    if change=='claimed':p['ops']['code-full-2']={'state':'claimed'}
    if change=='already_full':p['full_code_path']='old.py'
    if change=='already_job':p['jobs']['full-0']={}
    with pytest.raises(WorkflowError):cr.prepare(w,'fixture',row['id'],req)


def test_claim_after_preflight_cannot_be_overwritten(full_source):
    w,row,req,store=full_source;prepared=cr.prepare(w,'fixture',row['id'],req)
    row['payload']['ops']['code-full-2']={'state':'claimed'}
    with pytest.raises(WorkflowError,match='claimed'):cr.submit(w,'fixture',row['id'],prepared,'stale')


@pytest.mark.parametrize('phase',['GENERATE_FULL'])
def test_full_rework_retains_p1_and_budget_history(monkeypatch,phase):
    row={'hand':'coding','phase':phase,'payload':{'attempt':1,'retries':1,
        'accepted_reviews':{'P1':'P1-0','P2':'old'},'reviews':{'P1-0':{'status':'PASS'}}}}
    monkeypatch.setattr(hr,'save',lambda w,r,p:r.update(phase=p))
    hr.rework(None,row,{'failure':'synthetic'},'coding')
    assert row['phase']=='GENERATE_FULL' and row['payload']['accepted_reviews']=={'P1':'P1-0'}
    assert row['payload']['attempt']==row['payload']['retries']==2


@pytest.mark.parametrize('phase',['EXECUTE_FULL','REPRODUCE_FULL','REVIEW_P2'])
def test_actual_full_execution_or_review_failure_still_invalidates_gate(monkeypatch,phase):
    row={'hand':'coding','phase':phase,'payload':{'attempt':1,'retries':1,
        'accepted_reviews':{'P1':'P1-0'},'reviews':{'P1-0':{'status':'PASS'}}}}
    monkeypatch.setattr(hr,'save',lambda w,r,p:r.update(phase=p))
    hr.rework(None,row,{'failure':'synthetic'},'coding')
    assert row['phase']=='GENERATE_MINIMAL' and not row['payload']['accepted_reviews']


def test_minimal_rework_does_not_keep_old_pass(monkeypatch):
    row={'hand':'coding','phase':'GENERATE_MINIMAL','payload':{'attempt':1,'retries':1,
        'accepted_reviews':{'P1':'old'},'reviews':{'old':{'status':'PASS'}}}}
    monkeypatch.setattr(hr,'save',lambda w,r,p:r.update(phase=p))
    hr.rework(None,row,{},'coding')
    assert row['phase']=='GENERATE_MINIMAL' and not row['payload']['accepted_reviews']


def test_known_incomplete_uses_originating_stage_not_temporary_unknown(monkeypatch):
    row={'hand':'coding','phase':'GENERATE_FULL','payload':{'attempt':0,'retries':0,
        'accepted_reviews':{'P1':'P1-0'},'reviews':{'P1-0':{'status':'PASS'}}}}
    w=SimpleNamespace(lock=lambda *a:nullcontext())
    monkeypatch.setattr(hr,'load',lambda *a:row);monkeypatch.setattr(hr,'guard',lambda *a:{})
    monkeypatch.setattr(hr,'save',lambda w,r,p:r.update(phase=p));monkeypatch.setattr(hr,'status',lambda *a:row)
    def incomplete(*a):
        row['phase']='PROVIDER_UNKNOWN'
        raise ModelCallError('truncated',domain='model_output')
    monkeypatch.setattr(hr,'code_generate',incomplete)
    hr.advance(w,'fixture','run')
    assert row['phase']=='GENERATE_FULL' and row['payload']['coding_failure_stage']=='full'
    assert row['payload']['accepted_reviews']=={'P1':'P1-0'}


def test_full_capacity_comes_from_frozen_figure_commitments(tmp_path,monkeypatch):
    limits={'timeout_s':180,'memory_mb':1024,'max_files':32,'max_file_bytes':1048576,'max_total_bytes':4194304,'max_log_bytes':262144}
    row={'payload':{'request':{'limits':limits}}}
    monkeypatch.setattr(hr,'run_folder',lambda r:tmp_path)
    monkeypatch.setattr(hr,'read',lambda p:{'content':{'figures':[{}]*13}} if p.name=='mathematics.json' else {'outputs':[{}]*5})
    assert hr.execution_limits(row,True)['max_files']==46
    assert hr.execution_limits(row,False)['max_files']==32
    assert limits['max_files']==32
