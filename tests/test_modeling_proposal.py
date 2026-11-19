"""New proposal policy rejects incomplete work; does not prove scientific correctness."""
import copy
import json

import pytest
from pydantic import ValidationError

from modelcrew.collaboration import Check
from modelcrew.modeling_hand import pointer, proposal_schema
from modelcrew.modeling_proposal import (ReviewDocument, AuditFinding, CRITERIA, VERSION,
    validate_document, render, enforce_audit)
from modelcrew.hand_contracts import REQUIRED_CHECKS
from proposal_fixtures import document, audit


def baseline():
    return {'sources':[{'id':'statement','locator':'合成原始资料'}]}, {'cards':[]}


def test_document_renders_actual_sections_and_unified_symbol_table():
    contract,refs=baseline();doc=ReviewDocument.model_validate(document())
    report=validate_document(doc,contract,refs)
    text=render(doc,contract,refs)
    assert text.count('## 符号说明')==1
    assert all(title in text for title in ['问题分析与建模思路','模型假设及依据','模型建立与推导','离散与求解流程','检验方法与判据','局限性与适用范围','资料依据'])
    assert not report['semantic_correctness_verified'] and report['independent_audit_required']


@pytest.mark.parametrize('key',['problem_analysis','assumptions','symbols','model_derivation','solution_plan','verification_plan','limitations','sources','applicability'])
def test_each_required_section_is_structural_not_a_heading_only(key):
    value=document();value.pop(key)
    with pytest.raises(ValidationError):ReviewDocument.model_validate(value)


@pytest.mark.parametrize('mutation',['internal','duplicate_symbol','fake_source','missing_applicability','english','plain_formula'])
def test_reject_internal_metadata_conflicting_symbols_and_unread_sources(mutation):
    value=document();contract,refs=baseline()
    if mutation=='plain_formula':value['model_derivation']=value['model_derivation'].replace('$x=a$','x=a')
    if mutation=='internal':value['model_derivation']+=' edits=[] baseline chk_bc M1'
    if mutation=='duplicate_symbol':value['symbols'].append(copy.deepcopy(value['symbols'][0]))
    if mutation=='fake_source':value['sources'][0]['source_id']='invented-reference'
    if mutation=='missing_applicability':value['applicability'].pop('stability')
    if mutation=='english':
        for key in ['problem_analysis','model_derivation','solution_plan','verification_plan','limitations']:value[key]='English only explanation without actual Chinese modeling discussion. '*20
    with pytest.raises(ValueError):validate_document(ReviewDocument.model_validate(value),contract,refs)


def test_new_schema_requires_review_document_but_legacy_schema_does_not():
    from jsonschema import Draft202012Validator
    legacy=proposal_schema({'cards':[]})
    new=proposal_schema({'cards':[]},proposal_policy={'version':VERSION},source_ids=['statement'])
    Draft202012Validator.check_schema(new)
    value={'task_graph':[{'id':'q1','scope':'scope','conclusion_type':'simulation'}], 'proposal':'summary','questions':[], 'edits':[], 'source_decisions':[]}
    assert not list(Draft202012Validator(legacy).iter_errors(value))
    assert list(Draft202012Validator(new).iter_errors(value))
    value['review_document']=document()
    assert not list(Draft202012Validator(new).iter_errors(value))


def checked(findings=None):
    checks=[Check(check_id=key,status='PASS',evidence=[],explanation='Synthetic declared pass') for key in REQUIRED_CHECKS['M1']]
    proofs={'proposal':{'review_document':document()},'contract':{'method':'Synthetic method'}}
    parsed=[AuditFinding.model_validate(x) for x in findings] if findings is not None else None
    return enforce_audit(checks,[],parsed,proofs,pointer)


def test_legacy_blanket_pass_cannot_pass_new_policy_without_audit():
    checks,issues,result=checked()
    assert all(c.status=='BLOCKED' for c in checks)
    assert len(issues)==len(CRITERIA) and all(x['status']=='BLOCKED' for x in result)


@pytest.mark.parametrize('mutation',['missing','duplicate','root_only','fake_pointer','no_baseline','math_fail'])
def test_each_audit_is_unique_precise_and_cannot_be_hidden_by_overall_pass(mutation):
    findings=audit();index=next(i for i,x in enumerate(findings) if x['criterion']=='convergence_reasoning')
    if mutation=='missing':findings.pop(index)
    if mutation=='duplicate':findings.append(copy.deepcopy(findings[index]))
    if mutation=='root_only':findings[index]['evidence'][0]['selector']='/review_document'
    if mutation=='fake_pointer':findings[index]['evidence'][0]['selector']='/review_document/verification_plan/missing'
    if mutation=='no_baseline':findings[index]['evidence']=findings[index]['evidence'][:1]
    if mutation=='math_fail':findings[index]['status']='FAIL';findings[index]['explanation']='误把加密比值1.5解释为二阶证明。'
    checks,issues,result=checked(findings)
    expected='FAIL' if mutation=='math_fail' else 'BLOCKED'
    assert next(c for c in checks if c.check_id=='validation_plan').status==expected
    assert any(x['criterion']=='convergence_reasoning' and x['status']==expected for x in result)
    assert issues


def test_complete_audit_preserves_reviewer_findings_and_new_policy_is_frozen(tmp_path):
    checks,issues,result=checked(audit())
    assert not issues and all(c.status=='PASS' for c in checks)
    from modelcrew.hand_guidance import freeze_guidance,frozen_context
    sha=freeze_guidance(tmp_path)
    assert frozen_context(tmp_path,sha,'modeling')['modeling_proposal_policy']=={'version':VERSION}
    assert frozen_context(tmp_path,sha,'M1')['modeling_proposal_policy']=={'version':VERSION}
    assert 'modeling_proposal_policy' not in frozen_context(tmp_path,sha,'coding')



def test_old_frozen_guidance_does_not_acquire_new_policy():
    import hashlib
    from modelcrew.hand_guidance import load_bundle,guidance_context
    bundle=copy.deepcopy(load_bundle())
    bundle['manifest']['boundaries'].pop('modeling_proposal_protocol')
    bundle['manifest_sha256']=hashlib.sha256(json.dumps(bundle['manifest'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    assert 'modeling_proposal_policy' not in guidance_context(bundle,'modeling')
    assert 'modeling_proposal_policy' not in guidance_context(bundle,'M1')



@pytest.mark.parametrize('criterion,selector',[('nonlinear_solver','/review_document/applicability/nonlinear_solver'),('nonlinear_solver','/review_document/model_derivation'),('stability_reasoning','/review_document/model_derivation'),('convergence_reasoning','/review_document/applicability/convergence'),('reader_presentation','/text')])
def test_relevant_alternate_section_is_not_rejected_for_cosmetic_location(criterion,selector):
    from modelcrew.collaboration import Check
    findings=audit();finding=next(x for x in findings if x['criterion']==criterion)
    finding['evidence'][0]['selector']=selector
    checks=[Check(check_id=key,status='PASS',evidence=[],explanation='Synthetic declared pass') for key in REQUIRED_CHECKS['M1']]
    proofs={'proposal':{'review_document':document(),'text':'Full synthetic readable view'},'contract':{'method':'Synthetic method'}}
    checks,issues,result=enforce_audit(checks,[],[AuditFinding.model_validate(x) for x in findings],proofs,pointer)
    assert not issues and all(c.status=='PASS' for c in checks)


def test_concise_assumption_basis_is_allowed_but_empty_basis_is_not():
    value=document();value['assumptions'][0]['basis']='题面明示初值。'
    doc=ReviewDocument.model_validate(value)
    assert doc.assumptions[0].basis=='题面明示初值。'
    for empty in ['', '   ']:
        value['assumptions'][0]['basis']=empty
        with pytest.raises(ValidationError):ReviewDocument.model_validate(value)


def test_structure_feedback_identifies_field_without_urls_or_rejected_input():
    from modelcrew.modeling_hand import structure_feedback
    from modelcrew.business_adapter import clean
    value=document();value['assumptions'][0]['basis']=''
    try:ReviewDocument.model_validate(value)
    except ValidationError as exc:feedback=structure_feedback(exc,{'cards':[{'citation_id':'algorithm:ode:test'}]})
    safe=clean(feedback, 'D:/synthetic/workspace')
    assert 'assumptions.0.basis' in safe['issues']
    assert safe['validation_errors'][0]['loc']==['assumptions',0,'basis']
    assert 'errors.pydantic.dev' not in json.dumps(safe)
    assert all(key not in safe['validation_errors'][0] for key in ['input','url','ctx'])
    assert safe['required_source_decision_ids']==['algorithm:ode:test']
    assert 'not a report that they are invalid' in safe['instruction']


@pytest.mark.parametrize('formula', ['$x=a$', '$$x=a$$', r'\[x=a\]', r'\(x=a\)'])
def test_latex_delimiters_survive_json_and_validate(formula):
    value=document();value['model_derivation']=value['model_derivation'].replace('$x=a$',formula)
    value=json.loads(json.dumps(value))
    contract,refs=baseline()
    assert validate_document(ReviewDocument.model_validate(value),contract,refs)['status']=='PASS'


def test_prose_error_reports_exact_field_token_offset_and_preserves_input():
    from modelcrew.modeling_proposal import ProposalProseError
    from modelcrew.modeling_hand import structure_feedback
    value=document();value['model_derivation']+='\n温度方程引用 eq:heat2d，边界检验 chk_bc。'
    value['applicability']['nonlinear_solver']['reason']+=' 依据 eq:mass2d。'
    doc=ReviewDocument.model_validate(value);before=doc.model_dump(mode='json')
    contract,refs=baseline()
    with pytest.raises(ProposalProseError) as error:validate_document(doc,contract,refs)
    feedback=structure_feedback(error.value,refs)
    errors=feedback['validation_errors']
    assert [e['matched_tokens'] for e in errors]==[['eq:heat2d','chk_bc'],['eq:mass2d']]
    assert errors[0]['loc']==['review_document','model_derivation'] and errors[0]['line']==2
    assert errors[1]['loc']==['review_document','applicability','nonlinear_solver','reason']
    for item in errors:
        text=before
        for key in item['loc'][1:]:text=text[key]
        for match in item['matches']:
            assert text[match['char_start']:match['char_end']]==match['matched_text']
    assert doc.model_dump(mode='json')==before
    assert 'not by deleting the scientific content' in feedback['instruction']


def test_internal_prose_check_does_not_reject_registered_source_metadata():
    value=document();value['sources'][0]['source_id']='eq:registered-source'
    contract={'sources':[{'id':'eq:registered-source','locator':'baseline source catalog'}]}
    doc=ReviewDocument.model_validate(value)
    assert validate_document(doc,contract,{'cards':[]})['status']=='PASS'
    value['sources'][0]['use']+=' See eq:heat2d.'
    from modelcrew.modeling_proposal import ProposalProseError
    with pytest.raises(ProposalProseError) as error:validate_document(ReviewDocument.model_validate(value),contract,{'cards':[]})
    assert error.value.errors()[0]['loc']==['review_document','sources',0,'use']


def test_prose_diagnostics_are_bounded():
    from modelcrew.modeling_proposal import prose_diagnostics
    value=document();value['model_derivation']+=' eq:heat2d'*100
    errors=prose_diagnostics(ReviewDocument.model_validate(value))
    assert len(errors)==1 and errors[0]['occurrence_count']==100
    assert len(errors[0]['matches'])==30 and errors[0]['matches_truncated']
    assert errors[0]['matched_tokens']==['eq:heat2d']


def test_check_reference_with_digits_is_reported_as_one_full_token():
    from modelcrew.modeling_proposal import prose_diagnostics
    value=document();value['verification_plan']+=' chk_analytic2d'
    errors=prose_diagnostics(ReviewDocument.model_validate(value))
    assert len(errors)==1 and errors[0]['matched_text']=='chk_analytic2d'


@pytest.mark.parametrize('defect',['missing','duplicate','duplicate_fail'])
def test_m1_incomplete_review_is_explicitly_blocked_never_inferred_pass(defect):
    from modelcrew.modeling_hand import M1Answer,complete_m1_coverage
    value={'checks':[{'check_id':key,'status':'PASS','evidence':[], 'explanation':'Synthetic reviewer response'} for key in REQUIRED_CHECKS['M1']]}
    value['checks']=[c for c in value['checks'] if c['check_id']!='validation_plan']
    if defect.startswith('duplicate'):
        value['checks'].append(copy.deepcopy(value['checks'][0]))
        if defect=='duplicate_fail':value['checks'][-1]['status']='FAIL'
    answer,coverage=complete_m1_coverage(M1Answer.model_validate(value),REQUIRED_CHECKS['M1'])
    assert len(answer.checks)==6 and not coverage['complete']
    assert next(c for c in answer.checks if c.check_id=='validation_plan').status=='BLOCKED'
    if defect=='duplicate_fail':assert next(c for c in answer.checks if c.check_id=='model').status=='FAIL'
    assert all(i.target=='recovery' for i in answer.issues)
