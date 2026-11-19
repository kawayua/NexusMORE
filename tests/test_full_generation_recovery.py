"""A stage correction requires unchanged P1 bytes and terminal truncation proof."""
import copy
import json

import pytest
from modelcrew import full_generation_recovery as fg,hand_runtime as hr
from modelcrew.contracts import digest
from modelcrew.collaboration import sha_file
from modelcrew.workflow import WorkflowError


@pytest.fixture
def misroute(tmp_path,monkeypatch):
    folder=tmp_path/'run';folder.mkdir();(tmp_path/'minimal.py').write_text('raise RuntimeError("not executed")',encoding='utf-8')
    minimal=(tmp_path/'minimal.py').read_text(encoding='utf-8')
    p={'binding':{'version':6},'minimal_code':minimal,'minimal_code_path':'minimal.py','minimal_packet':'slice.json',
       'current_author':'original','lineage':['original'],'jobs':{'minimal-0':{}},'sealed':{'minimal.py':'hash'},
       'reviews':{'P1-0':{'status':'PASS','receipt_sha256':'a'*64,'snapshot_sha256':'b'*64}},
       'accepted_reviews':{'P1':'P1-0'},'attempt':0,'retries':0,'ops':{}}
    baseline={'id':1,'phase':'GENERATE_FULL','payload':copy.deepcopy(p)}
    p.update(accepted_reviews={},attempt=2,retries=2,failure_domain='implementation',rework_target='coding')
    for key in ['code-full-0','code-minimal-1']:
        f=folder/'operations'/key;f.mkdir(parents=True)
        data={'binding':p['binding'],'previous_minimal_code':minimal}
        request={'messages':[{}, {'content':json.dumps(data)}]};response={'choices':[{'finish_reason':'length'}]}
        (f/'Coder-fixture-request.json').write_text(json.dumps(request),encoding='utf-8')
        (f/'Coder-fixture-response.json').write_text(json.dumps(response),encoding='utf-8')
        meta={'status':'invalid_response','http_status':200,'finish_reason':'length','call_id':'fixture','response_sha256':sha_file(f/'Coder-fixture-response.json')}
        (f/'Coder-fixture-metadata.json').write_text(json.dumps(meta),encoding='utf-8')
        p['ops'][key]={'state':'claimed','request_sha256':digest(data)}
    row={'hand':'coding','phase':'GENERATE_MINIMAL','payload':p}
    monkeypatch.setattr(fg,'ROOT',tmp_path);monkeypatch.setattr(hr,'run_folder',lambda r:folder)
    monkeypatch.setattr(hr,'rel',lambda p:p.relative_to(tmp_path).as_posix())
    return row,baseline,folder


def test_recovery_proof_keeps_budget_and_reads_only(misroute):
    row,base,f=misroute;before=copy.deepcopy(row)
    value=fg.proof(row,base,[])
    assert value['attempt']==value['retries']==2 and value['P1_key']=='P1-0'
    assert row==before


@pytest.mark.parametrize('key',['minimal_code','minimal_code_path','minimal_packet','current_author','lineage','jobs','sealed','binding'])
def test_changed_accepted_slice_cannot_recover(misroute,key):
    row,base,f=misroute;row['payload'][key]='changed'
    with pytest.raises(WorkflowError):fg.proof(row,base,[])


@pytest.mark.parametrize('change',['full_code','new_claim','missing_pass','retry_reset','reply_hash','http_failure'])
def test_incomplete_or_advanced_history_cannot_recover(misroute,change):
    row,base,f=misroute;p=row['payload']
    if change=='full_code':p['full_code_path']='new.py'
    if change=='new_claim':p['ops']['code-full-2']={'state':'claimed'}
    if change=='missing_pass':base['payload']['accepted_reviews']={}
    if change=='retry_reset':p['retries']=0
    if change=='reply_hash':(f/'operations/code-full-0/Coder-fixture-response.json').write_text('{}',encoding='utf-8')
    if change=='http_failure':
        target=f/'operations/code-full-0/Coder-fixture-metadata.json';v=json.loads(target.read_text());v['http_status']=503;target.write_text(json.dumps(v))
    with pytest.raises(WorkflowError):fg.proof(row,base,[])
