import copy,json,uuid
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from modelcrew import deviation_acceptance as da,hand_runtime as hr
from modelcrew.contracts import digest
from modelcrew.workflow import WorkflowError


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    bind={'task_id':'synthetic-task','contract_version':6,'contract_sha256':'d'*64,'execution_id':'synthetic-execution','result_revision':1}
    checks=[{'id':'chk_dt','status':'FAIL','value':.0084,'tolerance':.002},{'id':'chk_analytic2d','status':'FAIL','value':.0010597,'tolerance':.001}]
    packet={'json_outputs':{'result.json':{'binding':bind,'config':{'dt':1},'checks':checks},'outputs/diagnostics.json':{'verification':{'base_reference':{'sha256_unrounded_T':'1'*64,'sha256_unrounded_C':'2'*64}}}},'receipt':{'status':'succeeded'},'artifacts':[{'path':'runs/primary/artifacts/result.json','sha256':'3'*64}]}
    contract={'checks':[{'id':c['id'],'tolerance':c['tolerance']} for c in checks]}
    row={'id':str(uuid.uuid4()),'task_id':'synthetic-task','version':6,'hand':'coding','phase':'GENERATE_MINIMAL','payload':{'binding':bind,'attempt':3,'retries':3,'ops':{'P2-2':{'state':'completed'}},'jobs':{'full-2':{}},'full_packet':'full.json','replica_packet':'replica.json','sealed':{},'accepted_reviews':{},'last_review':{'gate':'P2','attempt':2,'stage_key':'P2-2'},'reviews':{'P1-0':{'status':'PASS','receipt_sha256':'b'*64,'snapshot_sha256':'c'*64},'P2-2':{'status':'FAIL','receipt_sha256':'e'*64,'snapshot_sha256':'f'*64}}}}
    decision=dict(protocol='disclosed-error-acceptance/1.0.0',run_id=row['id'],binding=bind,actor='user',request_id='user-exact-errors',user_statement='我接受这两个已披露误差，再进行一次P2。',reason='Self-imposed numerical checks; observed errors accepted.',check_ids=[c['id'] for c in checks],expected_p2_receipt_sha256='e'*64,expected_p2_snapshot_sha256='f'*64,expected_check_sha256={c['id']:digest(c) for c in checks},requirement_provenance='Original statement does not specify these tolerances.',capture_channel='trusted_local_user_message')
    for name,value in [('full.json',packet),('replica.json',packet),('decision.json',decision)]:
        (tmp_path/name).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    w=SimpleNamespace(db=object(),lock=lambda key:nullcontext(),task=lambda t:{'result_revision':0})
    monkeypatch.setattr(hr,'ROOT',tmp_path);monkeypatch.setattr(hr,'load',lambda *a:row);monkeypatch.setattr(hr,'guard',lambda *a:contract);monkeypatch.setattr(hr,'run_folder',lambda r:tmp_path);monkeypatch.setattr(hr,'save',lambda w,r,phase=None:r.update(phase=phase or r['phase']));monkeypatch.setattr(hr,'status',lambda *a:{'phase':row['phase']})
    import modelcrew.business_store as bs,modelcrew.collaboration as collab
    monkeypatch.setattr(bs,'BusinessStore',lambda db:SimpleNamespace(unresolved=lambda scope:None))
    class Store:
        def __init__(self,*a):pass
        def load(self,cls,key):return SimpleNamespace(key=key,status='PASS' if key=='b'*64 else 'FAIL')
        def accept_review(self,receipt,snapshot):return receipt.key
    monkeypatch.setattr(collab,'CollaborationStore',Store)
    return tmp_path,row,packet,contract,decision,w


def test_exact_user_acceptance_reopens_p2_preserving_original_fail_and_budget(fixture):
    root,row,packet,contract,decision,w=fixture;before=copy.deepcopy(row);original=(root/'full.json').read_bytes()
    da.adopt(w,'synthetic-task',row['id'],'decision.json')
    assert row['phase']=='REVIEW_P2' and row['payload']['attempt']==3 and row['payload']['retries']==3
    assert row['payload']['reviews']==before['payload']['reviews']
    assert row['payload']['accepted_reviews']=={'P1':'P1-0'}
    assert (root/'full.json').read_bytes()==original
    record=da.validate(row);assert record['accepted_checks']['chk_dt']['status']=='FAIL'
    assert 'no user approval' not in record['acceptance_disposition']
    assert da.adopt(w,'synthetic-task',row['id'],'decision.json')=={'phase':'REVIEW_P2'}


@pytest.mark.parametrize('field,value',[('actor','model'),('check_ids',['execution']),('check_ids',['chk_dt','chk_dt']),('run_id','different')])
def test_no_agent_authorization_or_mandatory_gate_exemption(fixture,field,value):
    root,row,packet,contract,d,w=fixture;d[field]=value
    with pytest.raises((WorkflowError,ValueError)):
        da.verify_request(da.Decision(**d),row,packet,contract)


@pytest.mark.parametrize('change',['value','threshold','binding','receipt'])
def test_changed_measured_or_frozen_evidence_refused(fixture,change):
    root,row,packet,contract,d,w=fixture
    if change=='value':packet['json_outputs']['result.json']['checks'][0]['value']=.02
    elif change=='threshold':contract['checks'][0]['tolerance']=.01
    elif change=='binding':d['binding']={**d['binding'],'contract_version':7}
    else:d['expected_p2_receipt_sha256']='0'*64
    with pytest.raises(WorkflowError):da.verify_request(da.Decision(**d),row,packet,contract)


@pytest.mark.parametrize('claim',['op','job'])
def test_no_reopening_after_new_generation_or_execution_claim(fixture,claim):
    root,row,packet,contract,d,w=fixture
    if claim=='op':row['payload']['ops']['code-minimal-3']={'state':'claimed'}
    else:row['payload']['jobs']['minimal-3']={}
    with pytest.raises(WorkflowError,match='newer author'):da.adopt(w,'synthetic-task',row['id'],'decision.json')


def test_export_only_reuse_is_allowed_but_new_numbers_require_new_discussion(fixture):
    root,row,packet,contract,d,w=fixture;da.adopt(w,'synthetic-task',row['id'],'decision.json')
    packet['json_outputs']['result.json']['font']={'selected':'different-export-font'}
    (root/'new-export.json').write_text(json.dumps(packet),encoding='utf-8');row['payload']['full_packet']='new-export.json';assert da.validate(row)
    packet['json_outputs']['result.json']['checks'][0]['value']=.009
    (root/'new-export.json').write_text(json.dumps(packet),encoding='utf-8')
    with pytest.raises(WorkflowError,match='communicate again'):da.validate(row)


def test_acceptance_record_tampering_is_rejected(fixture):
    root,row,packet,contract,d,w=fixture;da.adopt(w,'synthetic-task',row['id'],'decision.json')
    path=root/row['payload']['error_acceptance_addendum']['path'];path.write_text('{}',encoding='utf-8')
    with pytest.raises(WorkflowError,match='addendum changed'):da.validate(row)

def test_new_export_archives_old_author_visual_record_without_rewriting_it():
    from modelcrew.deviation_acceptance import archive_author_visual_evidence
    old={'path':'old-author-views.json','sha256':'a'*64};row={'payload':{'author_visual_evidence':old,'sealed':{'old-author-views.json':'a'*64}}}
    assert archive_author_visual_evidence(row,'export revised')==old
    assert 'author_visual_evidence' not in row['payload']
    assert row['payload']['author_visual_evidence_history'][0]['record']==old
    assert row['payload']['sealed']=={'old-author-views.json':'a'*64}
