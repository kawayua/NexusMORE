"""Connection-failure recovery cannot replay ambiguous reviewer requests."""
import copy
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from modelcrew import hand_delivery as hd,hand_runtime as hr
from modelcrew.contracts import digest
from modelcrew.workflow import WorkflowError


@pytest.fixture
def evidence(tmp_path):
    data={'frozen':'synthetic-review-input'}
    meta={'status':'unknown','error_type':'ConnectError','http_status':None,'stage':'P1','call_id':'fixture'}
    request={'messages':[{'content':'system'},{'content':json.dumps(data)}]}
    def save():
        (tmp_path/'P1-fixture-metadata.json').write_text(json.dumps(meta),encoding='utf-8')
        (tmp_path/'P1-fixture-request.json').write_text(json.dumps(request),encoding='utf-8')
    save()
    return tmp_path,data,meta,request,save


def test_proof_requires_exact_original_input_and_preserves_files(evidence):
    f,data,*_=evidence
    before={p.name:p.read_bytes() for p in f.iterdir()}
    proof=hd.delivery_proof(f,'P1',digest(data))
    assert set(proof)==set(before)
    assert before=={p.name:p.read_bytes() for p in f.iterdir()}
    with pytest.raises(WorkflowError,match='differs'):hd.delivery_proof(f,'P1','0'*64)


@pytest.mark.parametrize('change',[{'error_type':'ReadTimeout'},{'error_type':'WriteError'},
    {'http_status':503},{'status':'completed'},{'stage':'P2'},{'call_id':'different'}])
def test_no_retry_for_ambiguous_or_changed_call(evidence,change):
    f,data,meta,request,save=evidence;meta.update(change);save()
    with pytest.raises(WorkflowError):hd.delivery_proof(f,'P1',digest(data))


@pytest.mark.parametrize('name',['answer.json','P1-fixture-response.json','P1-extra-metadata.json'])
def test_any_response_or_second_call_prevents_authorization(evidence,name):
    f,data,*_=evidence;(f/name).write_text('{}',encoding='utf-8')
    with pytest.raises(WorkflowError):hd.delivery_proof(f,'P1',digest(data))


def test_authorization_is_consumed_durably_once_before_network(evidence,monkeypatch):
    f,data,*_=evidence;proof=hd.delivery_proof(f,'P1',digest(data))
    auth={'evidence':proof,'consumed':False}
    row={'payload':{'ops':{'P1-0':{'request_sha256':digest(data),'delivery_retry_authorization':auth}}}}
    saves=[];monkeypatch.setattr(hr,'save',lambda w,r:saves.append(copy.deepcopy(r)))
    assert hd.consume_authorization(None,row,'P1-0',f,'P1')
    assert saves[0]['payload']['ops']['P1-0']['delivery_retry_authorization']['consumed'] is True
    assert not hd.consume_authorization(None,row,'P1-0',f,'P1')
    assert len(saves)==1


def test_changed_proof_is_rejected_before_consumption(evidence,monkeypatch):
    f,data,meta,req,save=evidence
    auth={'evidence':hd.delivery_proof(f,'P1',digest(data)),'consumed':False}
    row={'payload':{'ops':{'P1-0':{'request_sha256':digest(data),'delivery_retry_authorization':auth}}}}
    req['model']='changed';save()
    with pytest.raises(WorkflowError,match='changed'):hd.consume_authorization(None,row,'P1-0',f,'P1')
    assert auth['consumed'] is False

def test_undelivered_multimodal_request_proof_checks_exact_image_bytes(evidence):
    import base64,hashlib
    f,data,meta,request,save=evidence
    raw=b'\x89PNG\r\n\x1a\nSYNTHETIC_BYTE_PROOF'
    data['actual_image_dispatch']=[{'image_id':'page-1','sha256':hashlib.sha256(raw).hexdigest()}]
    meta['image_count']=1
    request['messages'][1]['content']=[{'type':'text','text':json.dumps(data)},{'type':'text','text':'page1'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(raw).decode()}}]
    save()
    assert hd.delivery_proof(f,'P1',digest(data))
    request['messages'][1]['content'][-1]['image_url']['url']='data:image/png;base64,'+base64.b64encode(b'changed').decode()
    save()
    with pytest.raises(WorkflowError,match='image bytes differ'):hd.delivery_proof(f,'P1',digest(data))
