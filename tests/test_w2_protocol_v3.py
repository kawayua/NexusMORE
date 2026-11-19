"""New-protocol invariants; old invalid responses cannot be laundered as v3."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from test_w2_protocol import packet
from modelcrew import w2_protocol_v3 as p
from modelcrew import w2_protocol as old
from modelcrew.workflow import WorkflowError
from modelcrew.contracts import digest


def answer(packet,status='PASS'):
    refs,_,_=p.prepare(packet)
    raw={'protocol_version':'3.0.0',
      'checks':[{'check_id':k,'status':status if k=='claims' else 'PASS','evidence_refs':[refs['entries'][0]['ref_id']],'explanation':'actual finding'} for k in old.CHECKS],
      'issues':[],'pages_reviewed':[{'page_ref':r['page_ref'],'status':'PASS','finding':'observed'} for r in refs['pages']]}
    if status!='PASS':raw['issues']=[{'check_id':'claims','severity':'blocking','issue_kind':'writing','reason':'actual problem','recheck':'verify correction'}]
    return raw,refs


@pytest.mark.parametrize('status',['PASS','FAIL','BLOCKED'])
def test_aggregate_derived_without_model_authored_duplicate_status(packet,status):
    raw,refs=answer(packet,status);before=deepcopy(raw)
    result,proof=p.compile_answer(raw,packet,refs)
    assert result['status']==status and raw==before
    assert proof['aggregate_status_source']=='per_check_verdicts'
    raw['status']='PASS'
    with pytest.raises(ValidationError):p.compile_answer(raw,packet,refs)


def test_long_findings_are_preserved_and_linked_without_truncation(packet):
    raw,refs=answer(packet,'FAIL');raw['checks'][0]['explanation']='详实的原始论据'*200
    raw['issues'][0].update(reason='问题'*500,recheck='复核要求'*300)
    raw['pages_reviewed'][0]['finding']='页面观测'*300;before=deepcopy(raw)
    result,proof=p.compile_answer(raw,packet,refs)
    assert raw==before and result['status']=='FAIL'
    assert len(result['checks'][0]['explanation'])<=300
    assert '/checks/0/explanation' in result['checks'][0]['explanation']
    assert digest(raw) in result['checks'][0]['explanation']
    assert proof['detail_report']['full_text_preserved']
    assert result['issues'][0]['severity']=='blocking'


@pytest.mark.parametrize('defect',['unknown','duplicate','missing_page','page_fail','hidden_issue','old_response','registry'])
def test_no_false_pass_or_reinterpretation(packet,defect):
    raw,refs=answer(packet)
    if defect=='unknown':raw['checks'][0]['evidence_refs']=['E9999']
    if defect=='duplicate':raw['checks'][1]['check_id']='claims'
    if defect=='missing_page':raw['pages_reviewed'].pop()
    if defect=='page_fail':raw['pages_reviewed'][0]['status']='FAIL'
    if defect=='hidden_issue':raw['issues']=[{'check_id':'claims','severity':'error','issue_kind':'writing','reason':'real issue','recheck':'required'}]
    if defect=='old_response':raw['protocol_version']='2.2.0';raw['status']='PASS'
    if defect=='registry':refs['entries'][0]['value_sha256']='f'*64
    with pytest.raises((ValidationError,WorkflowError)):p.compile_answer(raw,packet,refs)


def test_runtime_proof_is_registered_as_hash_bound_exact_evidence(packet):
    packet['evidence']['claim-runtime-reproduction-q1']={'value':{'status':'PASS','actual_files_verified':True}}
    raw,refs=answer(packet);item=next(r for r in refs['entries'] if r['artifact_id']=='claim-runtime-reproduction-q1')
    raw['checks'][4]['evidence_refs']=[item['ref_id']]
    native,_=p.compile_answer(raw,packet,refs)
    assert native['checks'][4]['evidence']==[{'artifact_id':'claim-runtime-reproduction-q1','selector':'/value'}]
    packet['evidence']['claim-runtime-reproduction-q1']['value']['status']='CHANGED'
    with pytest.raises(WorkflowError):p.compile_answer(raw,packet,refs)


def test_v2_still_rejects_its_old_contradictory_and_overlong_answers(packet):
    from test_w2_protocol import answer as v2_answer
    raw,refs=v2_answer(packet);raw['status']='FAIL'
    with pytest.raises(WorkflowError,match='Contradictory'):old.compile_answer(raw,packet,refs)
    raw['status']='PASS';raw['checks'][0]['explanation']='x'*301
    with pytest.raises(ValidationError):old.compile_answer(raw,packet,refs)


def test_model_client_requests_declared_v3_schema_without_duplicate_status(packet,tmp_path):
    import json
    from modelcrew.model_client import JsonModel
    raw,_=answer(packet);_,data,_=p.prepare(packet)
    class Response:
        status_code=200
        def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]}
    class Client:
        def post(self,url,**kwargs):
            req=kwargs['json'];assert req['model']=='synthetic-w2'
            assert req['response_format']['type']=='json_schema'
            assert req['response_format']['json_schema']['name']=='w2_evidence_refs_v3'
            assert 'status' not in req['response_format']['json_schema']['schema']['properties']
            return Response()
    model=JsonModel(client=Client(),config={'MODELCREW_LLM_API_KEY':'SYNTHETIC_SECRET_KEY_NOT_REAL',
        'MODELCREW_LLM_MODEL':'synthetic-default','MODELCREW_W2_MODEL':'synthetic-w2',
        'MODELCREW_LLM_BASE_URL':'https://invalid.example','MODELCREW_W2_RESPONSE_FORMAT':'json_schema'})
    got,meta=model.call(tmp_path,'W2','SYNTHETIC transport',data)
    assert got==raw and meta['server_schema_requested'] and meta['output_protocol']=='w2_evidence_refs_v3'
