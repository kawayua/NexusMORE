"""Exact-reference protocol checks; no paper approval or semantic PASS is inferred."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from modelcrew import w2_protocol as p
from modelcrew.contracts import digest
from modelcrew.workflow import WorkflowError

@pytest.fixture
def packet():
    return {'evidence':{'manuscript':{'text':'SYNTHETIC PAPER'},'figures':{'figures':[]},
      'render':{'status':'passed','formats':{'latex':{},'word':{}}},
      'claim-evidence-map':{'claims':[{'global_claim_id':'q1-test','statement':'Synthetic claim','evidence':[]}]},
      'claim-q1-test-0':{'source':{'selector':'/values/1/value'},'value':{'number':1}},
      'latex-page-001':{'format':'latex','page':1},'word-page-001':{'format':'word','page':1}},
      'images':[{'artifact_id':k+'-page-001','path':k+'.png','sha256':'a'*64,'label':k+' page 1'} for k in ['latex','word']]}


def answer(packet,status='PASS'):
    refs,view,images=p.prepare(packet)
    evidence=refs['entries'][0]['ref_id']
    result={'protocol_version':'2.2.0','status':status,
     'checks':[{'check_id':c,'status':status if c=='claims' else 'PASS','evidence_refs':[evidence],'explanation':'SYNTHETIC '+c} for c in p.CHECKS],
     'pages_reviewed':[{'page_ref':i['page_ref'],'status':'PASS','finding':'SYNTHETIC'} for i in refs['pages']],
     'issues':[]}
    if status!='PASS':result['issues']=[{'check_id':'claims','severity':'blocking','issue_kind':'infrastructure','reason':'SYNTHETIC missing facts','recheck':'SYNTHETIC verify original'}]
    return result,refs


def test_registry_exposes_only_real_value_anchors_and_labeled_pages(packet):
    refs,view,images=p.prepare(packet)
    claim=next(r for r in refs['entries'] if r['kind']=='claim')
    assert claim['selector']=='/value' and claim['value_sha256']==digest({'number':1})
    assert view['reference_registry_sha256']==digest(refs)
    assert all('artifact_id' not in r and 'selector' not in r for r in view['evidence'])
    assert view['claims'][0]['evidence_refs']==[claim['ref_id']]
    assert [i['label'].split()[0] for i in images]==['P0001','P0002']
    assert view['schema']['$defs']['Check']['properties']['evidence_refs']['items']['enum']==[r['ref_id'] for r in refs['entries']]

@pytest.mark.parametrize('status',['PASS','FAIL','BLOCKED'])
def test_translation_preserves_all_reviewer_verdicts_findings_and_issues(packet,status):
    raw,refs=answer(packet,status);before=deepcopy(raw)
    native,proof=p.compile_answer(raw,packet,refs)
    assert native['status']==status and raw==before
    assert proof['verdict_preserved'] and not proof['unknown_reference_repair']
    for a,b in zip(raw['issues'],native['issues']):
        assert all(a[k]==b[k] for k in ['check_id','severity','reason','recheck'])
        assert b['domain']=='infrastructure' and b['target']=='recovery'
    for a,b in zip(raw['checks'],native['checks']):
        assert (a['status'],a['explanation'])==(b['status'],b['explanation'])
        r=next(r for r in refs['entries'] if r['ref_id']==a['evidence_refs'][0])
        assert b['evidence']==[{'artifact_id':r['artifact_id'],'selector':r['selector']}]
    assert [r['finding'] for r in native['pages_reviewed']]==[r['finding'] for r in raw['pages_reviewed']]

@pytest.mark.parametrize('defect',['unknown_ref','foreign_artifact','invented_pointer','duplicate_ref','missing_page','duplicate_page','unpadded_page','contradiction','hidden_failure','empty_pass','bad_route','unresolved_error','changed_registry','changed_value','too_many_refs'])
def test_unknown_or_contradictory_data_is_rejected_without_repair(packet,defect):
    raw,refs=answer(packet)
    if defect=='too_many_refs':raw['checks'][0]['evidence_refs']=[r['ref_id'] for r in refs['entries'][:4]]
    if defect=='unknown_ref':raw['checks'][0]['evidence_refs']=['E9999']
    if defect=='foreign_artifact':raw['checks'][0]['evidence_refs']=['result']
    if defect=='invented_pointer':raw['checks'][0]['evidence']=[{'artifact_id':'result','selector':'/values/1'}]
    if defect=='duplicate_ref':raw['checks'][0]['evidence_refs']*=2
    if defect=='missing_page':raw['pages_reviewed'].pop()
    if defect=='duplicate_page':raw['pages_reviewed'][1]=raw['pages_reviewed'][0]
    if defect=='unpadded_page':raw['pages_reviewed'][0]['page_ref']='P1'
    if defect=='contradiction':raw['status']='FAIL'
    if defect=='hidden_failure':raw['pages_reviewed'][0]['status']='FAIL'
    if defect=='empty_pass':raw['checks'][0]['evidence_refs']=[]
    if defect in ['bad_route','unresolved_error']:
        raw['issues']=[{'check_id':'claims','severity':'error','issue_kind':'not_a_kind' if defect=='bad_route' else 'writing','reason':'SYNTHETIC','recheck':'SYNTHETIC'}]
    if defect=='changed_registry':refs['entries'][0]['selector']='/missing'
    if defect=='changed_value':packet['evidence']['manuscript']['text']='CHANGED'
    with pytest.raises((WorkflowError,ValidationError)):p.compile_answer(raw,packet,refs)


def test_output_schema_is_strict_and_has_no_optional_unregistered_locations(packet):
    _,view,_=p.prepare(packet)
    def verify(node):
        if isinstance(node,dict):
            if node.get('type')=='object':
                assert node.get('additionalProperties') is False
                assert set(node.get('required',[]))==set(node.get('properties',{}))
            for value in node.values():verify(value)
        elif isinstance(node,list):
            for value in node:verify(value)
    verify(view['schema'])


def test_native_receipt_length_is_the_hard_limit_and_old_versions_are_not_reinterpreted(packet):
    raw,refs=answer(packet)
    assert p.NATIVE_TEXT_LIMIT==300
    raw['checks'][0]['explanation']='x'*242
    native,_=p.compile_answer(raw,packet,refs)
    assert native['checks'][0]['explanation']=='x'*242
    raw['checks'][0]['explanation']='x'*301
    with pytest.raises(ValidationError):p.compile_answer(raw,packet,refs)
    raw['checks'][0]['explanation']='x'*242;raw['protocol_version']='2.1.0'
    with pytest.raises(ValidationError):p.compile_answer(raw,packet,refs)
