"""Exact initial Coder source transport; never a model approval or execution."""
import copy
import hashlib
import uuid
from types import SimpleNamespace

import pytest
from modelcrew import code_revision as cr
from modelcrew.workflow import WorkflowError


@pytest.fixture
def initial(tmp_path,monkeypatch):
    code='raise RuntimeError("Prepared source must not execute on host")\n'
    source=tmp_path/'source.py';source.write_text(code,encoding='utf-8')
    run=tmp_path/'run';run.mkdir()
    row={'id':str(uuid.uuid4()),'task_id':'synthetic-task','version':6,'hand':'coding','phase':'GENERATE_MINIMAL',
      'payload':{'attempt':0,'retries':0,'ops':{},'jobs':{},'reviews':{},'binding':{'synthetic':True},'sealed':{}}}
    w=SimpleNamespace(approved=True,task=lambda task:{'result_revision':0})
    def guard(w,row):
        if not w.approved:raise WorkflowError('Current approved model required')
    monkeypatch.setattr(cr,'ROOT',tmp_path)
    monkeypatch.setattr(cr.hr,'load',lambda *args:row)
    monkeypatch.setattr(cr.hr,'guard',guard)
    monkeypatch.setattr(cr.hr,'run_folder',lambda row:run)
    monkeypatch.setattr(cr.hr,'rel',lambda p:p.relative_to(tmp_path).as_posix())
    monkeypatch.setattr(cr.hr,'seal',lambda row,p:row['payload']['sealed'].update({p.name:hashlib.sha256(p.read_bytes()).hexdigest()}))
    authors=[];monkeypatch.setattr(cr.hr,'author',lambda row,record:authors.append(copy.deepcopy(record)))
    monkeypatch.setattr(cr.hr,'save',lambda w,row,phase:row.update(phase=phase))
    monkeypatch.setattr(cr.hr,'status',lambda w,t,r:{'phase':row['phase']})
    monkeypatch.setattr(cr,'grant',lambda row:None)
    req={'stage':'minimal','code_path':'source.py','code_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'previous_code_sha256':'0'*64,'rationale':'Synthetic exact prepared source, no approval or execution.'}
    return w,row,req,source,authors


def test_approved_unclaimed_initial_source_is_static_only_and_enters_execution(initial):
    w,row,req,source,authors=initial
    prepared=cr.prepare(w,'synthetic-task',row['id'],req)
    assert prepared['initial_prepared_source'] is True
    assert row['phase']=='GENERATE_MINIMAL' and authors==[]
    answer=cr.submit(w,'synthetic-task',row['id'],prepared,'initial-source')
    assert answer['phase']=='EXECUTE_MINIMAL'
    assert row['payload']['attempt']==row['payload']['retries']==0
    assert row['payload']['reviews']=={} and row['payload']['accepted_reviews']=={}
    assert authors[0]['origin']=='prepared_coder_source' and authors[0]['provider_call'] is False
    assert authors[0]['delegated_repair'] is None
    assert len(row['payload']['ops'])==1
    assert cr.submit(w,'synthetic-task',row['id'],prepared,'initial-source')==answer
    assert len(authors)==1


def test_initial_transport_still_requires_current_model_approval(initial):
    w,row,req,*_=initial;w.approved=False
    with pytest.raises(WorkflowError,match='approved model'):cr.prepare(w,'synthetic-task',row['id'],req)


@pytest.mark.parametrize('key,value',[('attempt',1),('retries',1),('ops',{'code-minimal-0':{'state':'claimed'}}),('jobs',{'minimal-0':{}}),('reviews',{'P1-0':{}}),('minimal_code_path','prior.py')])
def test_zero_hash_cannot_replace_claimed_or_existing_work(initial,key,value):
    w,row,req,*_=initial;row['payload'][key]=value
    with pytest.raises(WorkflowError):cr.prepare(w,'synthetic-task',row['id'],req)


def test_nonzero_previous_hash_is_not_an_initial_source(initial):
    w,row,req,*_=initial;req['previous_code_sha256']='1'*64
    with pytest.raises(WorkflowError,match='delegated repair'):cr.prepare(w,'synthetic-task',row['id'],req)


def test_corrupt_or_invalid_source_fails_before_any_write(initial):
    w,row,req,source,authors=initial
    source.write_text('bad Python !!!',encoding='utf-8')
    with pytest.raises(Exception):cr.prepare(w,'synthetic-task',row['id'],req)
    req['code_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(WorkflowError,match='compilable'):cr.prepare(w,'synthetic-task',row['id'],req)
    assert not authors and row['payload']['ops']=={}


def test_claim_between_preflight_and_submit_is_not_overwritten(initial):
    w,row,req,*_=initial;prepared=cr.prepare(w,'synthetic-task',row['id'],req)
    row['payload']['ops']['code-minimal-0']={'state':'claimed'}
    with pytest.raises(WorkflowError,match='no longer unclaimed'):cr.submit(w,'synthetic-task',row['id'],prepared,'late')


def test_no_new_initial_source_after_noninitial_stage(initial):
    w,row,req,*_=initial;req['stage']='full';row['phase']='GENERATE_FULL'
    with pytest.raises(WorkflowError):cr.prepare(w,'synthetic-task',row['id'],req)
