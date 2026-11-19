"""Durable terminal assembly evidence in an isolated synthetic database."""
import uuid
import pytest
from psycopg.types.json import Jsonb
from test_business_mcp import url,adapter,project,request
from modelcrew.workflow import Workflow
from modelcrew.assembly_builds import ComposeRequest
from modelcrew.business_contract import request_digest
from modelcrew.business_store import BusinessStore
from modelcrew.contracts import digest


@pytest.mark.parametrize('mode',['failed','payload_mismatch','request_mismatch','unfinished'])
def test_composition_reconciliation_requires_matching_terminal_evidence(adapter,url,monkeypatch,mode):
    monkeypatch.setattr(adapter,'_current_status',lambda *a:{'phase':'TEST_SYNTHETIC'})
    p,_=project(adapter);rid=str(uuid.uuid4());bid=str(uuid.uuid4());key='synthetic-compose'
    scope={'project_id':p,'run_id':rid};body={'request_id':key,'actor':'TEST_ONLY','title':'Synthetic question 1'}
    cmd=request('assembly_compose',{'project_id':p,'run_id':rid,'body':body},key=key,bound=scope)
    normalized=ComposeRequest.model_validate(body).model_dump(mode='json')
    payload={'request':normalized,'source_ready':False,'sealed':{},'failure':{'kind':'ValueError','message':'TEST_ONLY numbered reference error'}}
    phase='COMPOSING' if mode=='unfinished' else 'COMPOSITION_FAILED'
    with Workflow(url) as w:
        w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',(rid,p,'synthetic-input','a'*64,Jsonb({})))
        st=BusinessStore(w.db);row=st.claim(scope,'assembly_compose',key,request_digest(cmd),cmd,'project:'+p,'assembly-builds:'+p);st.save(row,'outcome_unknown')
        fingerprint=digest({'assembly_run_id':rid,'request':normalized}) if mode!='request_mismatch' else 'b'*64
        w.db.execute('INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)',(bid,rid,p,key,fingerprint,phase,Jsonb(payload)))
        event_payload={**payload,'changed':True} if mode=='payload_mismatch' else payload
        w.db.execute('INSERT INTO mc_assembly_build_events(build_id,phase,payload) VALUES(%s,%s,%s)',(bid,phase,Jsonb(event_payload)))
    query=request('operation_status',{**scope,'operation_name':'assembly_compose','request_id':key})
    result=adapter.invoke('operation_status',query)
    assert result['receipt']['state']==('failed' if mode=='failed' else 'outcome_unknown'),result
    if mode=='failed':
        response=result['data']['response'];assert response['phase']=='COMPOSITION_FAILED'
        assert response['data']['failure']==payload['failure'] and response['data']['no_redispatch'] is True
        repeat=adapter.invoke('operation_status',query);assert repeat['data']['response']==response
    with Workflow(url) as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_assembly_builds WHERE project_id=%s',(p,)).fetchone()['n']==1
        assert w.db.execute('SELECT count(*) AS n FROM mc_assembly_build_events WHERE build_id=%s',(bid,)).fetchone()['n']==1

def test_core_composition_failure_is_reported_without_unknown_fence(adapter,url,monkeypatch):
    p,_=project(adapter);rid=str(uuid.uuid4());bid=str(uuid.uuid4());key='synthetic-compose-dispatch'
    scope={'project_id':p,'run_id':rid};body={'request_id':key,'actor':'TEST_ONLY','title':'Synthetic question 1'}
    normalized=ComposeRequest.model_validate(body).model_dump(mode='json')
    with Workflow(url) as w:w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',(rid,p,'synthetic-input','a'*64,Jsonb({})))
    def dispatch(w,name,args):
        payload={'request':normalized,'source_ready':False,'sealed':{},'failure':{'kind':'ValueError','message':'TEST_ONLY known rejection'}}
        w.db.execute('INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)',(bid,rid,p,key,digest({'assembly_run_id':rid,'request':normalized}),'COMPOSITION_FAILED',Jsonb(payload)))
        w.db.execute('INSERT INTO mc_assembly_build_events(build_id,phase,payload) VALUES(%s,%s,%s)',(bid,'COMPOSITION_FAILED',Jsonb(payload)))
        raise ValueError('TEST_ONLY known rejection')
    monkeypatch.setattr(adapter,'_dispatch',dispatch)
    result=adapter.invoke('assembly_compose',request('assembly_compose',{'project_id':p,'run_id':rid,'body':body},key=key,bound=scope))
    assert result['receipt']['state']=='failed' and result['phase']=='COMPOSITION_FAILED',result
    with Workflow(url) as w:assert BusinessStore(w.db).unresolved('project:'+p) is None


@pytest.mark.parametrize('mode',['failed','payload_mismatch','request_mismatch','unfinished'])
def test_export_reconciliation_requires_matching_terminal_evidence(adapter,url,monkeypatch,mode):
    from modelcrew.assembly_builds import ExportRequest
    monkeypatch.setattr(adapter,'_current_status',lambda *a:{'phase':'TEST_SYNTHETIC'})
    p,_=project(adapter);rid=str(uuid.uuid4());bid=str(uuid.uuid4());key='synthetic-export'
    scope={'project_id':p,'build_id':bid};body={'request_id':key,'actor':'TEST_ONLY'}
    cmd=request('assembly_export',{**scope,'body':body},key=key,bound=scope)
    normalized=ExportRequest.model_validate(body).model_dump(mode='json')
    phase='EXPORTING' if mode=='unfinished' else 'EXPORT_FAILED'
    entry={'request_sha256':digest(normalized) if mode!='request_mismatch' else 'b'*64,
           'phase':phase,'error':'TEST_ONLY keywords spill to page 2','output':'synthetic/not-published'}
    payload={'exports':{key:entry},'sealed':{}}
    with Workflow(url) as w:
        w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',(rid,p,'synthetic-input','a'*64,Jsonb({})))
        st=BusinessStore(w.db);row=st.claim(scope,'assembly_export',key,request_digest(cmd),cmd,'project:'+p,'assembly-builds:'+p);st.save(row,'outcome_unknown')
        w.db.execute('INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)',(bid,rid,p,'synthetic-compose','a'*64,phase,Jsonb(payload)))
        event_payload={**payload,'changed':True} if mode=='payload_mismatch' else payload
        w.db.execute('INSERT INTO mc_assembly_build_events(build_id,phase,payload) VALUES(%s,%s,%s)',(bid,phase,Jsonb(event_payload)))
    query=request('operation_status',{**scope,'operation_name':'assembly_export','request_id':key})
    result=adapter.invoke('operation_status',query)
    assert result['receipt']['state']==('failed' if mode=='failed' else 'outcome_unknown'),result
    if mode=='failed':
        response=result['data']['response'];assert response['phase']=='EXPORT_FAILED'
        assert response['data']['no_redispatch'] is True
        assert adapter.invoke('operation_status',query)['data']['response']==response
    with Workflow(url) as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_assembly_build_events WHERE build_id=%s',(bid,)).fetchone()['n']==1


@pytest.mark.parametrize('mode',['failed','changed_answer','changed_packet','different_raw','request_mismatch','payload_mismatch','unfinished','transport_unknown'])
def test_w2_invalid_answer_reconciliation_preserves_evidence(adapter,url,monkeypatch,tmp_path,mode):
    import json
    from modelcrew.assembly_w2 import W2Request
    from modelcrew.collaboration import sha_file
    monkeypatch.setattr(adapter,'_current_status',lambda *a:{'phase':'TEST_SYNTHETIC'})
    p,_=project(adapter);monkeypatch.setattr(adapter,'root',tmp_path)
    rid=str(uuid.uuid4());bid=str(uuid.uuid4());key='synthetic-w2'
    scope={'project_id':p,'build_id':bid}
    body={'request_id':key,'actor':'TEST_ONLY','export_request_id':'synthetic-export','render_request_id':'synthetic-render'}
    cmd=request('assembly_review_w2',{**scope,'body':body},key=key,bound=scope)
    normalized=W2Request.model_validate(body).model_dump(exclude_none=True)
    base=tmp_path/'synthetic-w2';base.mkdir()
    answer={'status':'FAIL','checks':[{'explanation':'x'*338}]}
    raw={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer if mode!='different_raw' else {'status':'PASS'})}}]}
    def save(name,value):
        f=base/name;f.write_text(json.dumps(value),encoding='utf-8');return f
    ap=save('answer.json',answer);pp=save('packet.json',{'test_only':True})
    rp=save('W2-synthetic-call-response.json',raw)
    meta={'call_id':'synthetic-call','status':'completed','http_status':200,'finish_reason':'stop','response_sha256':sha_file(rp)}
    if mode=='transport_unknown':meta['status']='unknown'
    mp=save('W2-synthetic-call-metadata.json',meta)
    op={'phase':'INVALID_RESPONSE','request':normalized,'request_sha256':digest(normalized),
        'folder':'synthetic-w2','validation_error':'TEST_ONLY explanation too long',
        'answer_sha256':sha_file(ap),'packet_sha256':sha_file(pp),'provider_metadata':meta,'reviewer_reported_status':'FAIL'}
    if mode=='request_mismatch':op['request_sha256']='b'*64
    phase='W2_INVALID_RESPONSE'
    if mode=='unfinished':op['phase']='UNKNOWN';phase='W2_RECOVERY_REQUIRED'
    payload={'w2_reviews':{key:op},'sealed':{f.relative_to(tmp_path).as_posix():sha_file(f) for f in [ap,pp,rp,mp]}}
    if mode=='changed_answer':save('answer.json',{'status':'PASS'})
    if mode=='changed_packet':save('packet.json',{'changed':True})
    with Workflow(url) as w:
        w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',(rid,p,'synthetic-input','a'*64,Jsonb({})))
        st=BusinessStore(w.db);row=st.claim(scope,'assembly_review_w2',key,request_digest(cmd),cmd,'project:'+p,None);st.save(row,'outcome_unknown')
        w.db.execute('INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)',(bid,rid,p,'synthetic-compose','a'*64,phase,Jsonb(payload)))
        ep={**payload,'changed':True} if mode=='payload_mismatch' else payload
        w.db.execute('INSERT INTO mc_assembly_build_events(build_id,phase,payload) VALUES(%s,%s,%s)',(bid,phase,Jsonb(ep)))
    query=request('operation_status',{**scope,'operation_name':'assembly_review_w2','request_id':key})
    result=adapter.invoke('operation_status',query)
    assert result['receipt']['state']==('failed' if mode=='failed' else 'outcome_unknown'),result
    if mode=='failed':
        saved=result['data']['response'];assert saved['data']['reviewer_reported_status']=='FAIL'
        assert saved['data']['recheck_consumed'] is False and saved['data']['no_redispatch'] is True
        assert adapter.invoke('operation_status',query)['data']['response']==saved
    with Workflow(url) as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_assembly_build_events WHERE build_id=%s',(bid,)).fetchone()['n']==1
