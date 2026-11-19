"""Pure parsing and model-transport boundaries; no paid calls."""
from modelcrew.project_assets import asset_path,local_history
import copy
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from modelcrew.config import ROOT
from modelcrew.model_client import JsonModel, ModelCallError
from modelcrew.modeling_hand import (Edit, Plan, Proposal, SourceDecision, TaskNode,
    apply_edits, graph_check, pointer, validate_decisions)
from modelcrew.resource_routing import installed_algorithm_context as algorithm_context


def baseline():
    return (json.loads((asset_path(ROOT,'stage-b-plus/examples/contract-v2-snapshot.json')).read_text(encoding='utf-8')),
            json.loads((asset_path(ROOT,'stage-b-plus/examples/valid-bench-dragon.json')).read_text(encoding='utf-8')))


@pytest.mark.parametrize('path', ['contract-v2-snapshot.json'])
def test_patch_changes_method_but_preserves_all_baseline_checks(path):
    contract, package = baseline()
    step = list(contract['method']['steps'])+['Explicitly stop and report any branch ambiguity.']
    revised, math = apply_edits(contract, package, [Edit(op='replace',path='/contract/method/steps',value=step)])
    assert revised['method']['steps'] == step and revised['checks'] == contract['checks'] and math == package
    assert contract['method']['steps'] != step


@pytest.mark.parametrize('field', ['schema_version', 'problem', 'sources', 'inputs', 'parameters', 'conventions'])
def test_frozen_facts_cannot_be_rewritten(field):
    contract, package = baseline()
    with pytest.raises((ValueError, KeyError)):
        apply_edits(contract, package, [Edit(op='replace',path='/contract/'+field,value=None)])


def test_old_checks_cannot_be_weakened_or_deleted():
    contract, package = baseline()
    with pytest.raises(ValueError,match='weakened'):
        apply_edits(contract,package,[Edit(op='remove',path='/contract/checks/0')])


@pytest.mark.parametrize('path', ['/outside/x','/contract/unknown/child','/contract/checks/999','/contract/checks/-1','/contract/checks/01'])
def test_invalid_patch_path_rejected(path):
    contract,package=baseline()
    with pytest.raises(ValueError): apply_edits(contract,package,[Edit(op='replace',path=path,value='bad')])


def test_pointer_has_real_selectors_and_rfc6901_escaping():
    value={'a/b':{'~key':[1,2]}}
    assert pointer(value,'/a~1b/~0key/1')==2
    for path in ['no-pointer','/missing','/a~2b','/a~1b/~0key/99','/a~1b/~0key/-1']:
        with pytest.raises(ValueError): pointer(value,path)


def test_graph_cycles_unknown_and_duplicate_dependencies_rejected():
    def node(key,deps):return TaskNode(id=key,scope='scope',conclusion_type='simulation',depends_on=deps)
    graph_check([node('a',[]),node('b',['a'])])
    for nodes in [[node('a',['a'])],[node('a',['b']),node('b',['a'])],[node('a',['missing'])],[node('a',[]),node('a',[])]]:
        with pytest.raises(ValueError):graph_check(nodes)


def test_every_source_needs_explicit_adoption_or_rejection():
    references=algorithm_context('geometry',card_ids=['bracketed-root'])
    base={'task_graph':[{'id':'q1','scope':'scope','conclusion_type':'simulation'}], 'proposal':'中文方案','source_decisions':[]}
    proposal=Proposal.model_validate(base)
    with pytest.raises(ValueError,match='Every retrieved'):validate_decisions(proposal,references)
    base['source_decisions']=[{'citation_id':references['cards'][0]['citation_id'],'decision':'adopted','reason':'reason','adaptation':'adaptation','limitations':'limitations'}]
    validate_decisions(Proposal.model_validate(base),references)


@pytest.mark.parametrize('change', [{'facts':{'x':1}},{'category':'unknown'},{'task_graph':[]}])
def test_planning_response_is_strict(change):
    value={'task_graph':[{'id':'q1','scope':'scope','conclusion_type':'simulation'}],'category':'geometry','research_question':'root'}
    with pytest.raises(ValidationError):Plan.model_validate({**value,**change})


def config():return {'MODELCREW_LLM_API_KEY':'TEST-ONLY-SECRET','MODELCREW_LLM_MODEL':'test-model','MODELCREW_LLM_BASE_URL':'https://fixture.invalid/v1'}


def test_transport_has_no_retries_or_secret_logs(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ConnectError('transport with sensitive context',request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        service=JsonModel(client=client,config=config())
        with pytest.raises(ModelCallError,match='no automatic resend'):
            service.call(tmp_path,'planning','system',{'input':'value'})
    assert len(calls)==1
    for path in tmp_path.iterdir():assert 'TEST-ONLY-SECRET' not in path.read_text(encoding='utf-8')
    meta=json.loads(next(tmp_path.glob('*metadata.json')).read_text(encoding='utf-8'))
    assert meta['status']=='unknown'


@pytest.mark.parametrize('reason,content',[('length','{}'),('stop','not json')])
def test_invalid_or_truncated_model_output_is_preserved_without_retry(tmp_path,reason,content):
    count=[]
    def handler(request):
        count.append(1)
        return httpx.Response(200,json={'choices':[{'finish_reason':reason,'message':{'content':content}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError if reason=='stop' else ModelCallError):
            JsonModel(client=client,config=config()).call(tmp_path,'modeling','system',{})
    assert len(count)==1 and list(tmp_path.glob('*response.json'))

@pytest.mark.parametrize('extra', [{'version':True},{'auto_correct':1},{'guidance':' '},{'model':'override'},{'approve':True}])
def test_invalid_modeling_API_requests_never_reach_model(extra):
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    class Guard:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def run_modeling(self,*args,**kwargs):raise AssertionError('Invalid API input reached model')
    with TestClient(create_app(Guard)) as client:
        reply=client.post('/tasks/q/modeling/runs',json={**{'version':1,'actor':'test','request_id':'id','guidance':'guidance'},**extra})
        assert reply.status_code==422


@pytest.mark.parametrize("ids", [[], ["algorithm:lp:research-hash"]])
def test_proposal_schema_separates_frozen_background_from_research_decisions(ids):
    from modelcrew.modeling_hand import proposal_schema
    references={"cards":[{"citation_id":key} for key in ids]}
    schema=proposal_schema(references)
    assert schema["properties"]["source_decisions"]["minItems"]==len(ids)
    assert schema["properties"]["source_decisions"]["maxItems"]==len(ids)
    if ids:
        from jsonschema import Draft202012Validator
        value={"task_graph":[{"id":"q","scope":"model","conclusion_type":"proposal"}],"proposal":"未批准模型", "edits":[], "questions":[], "source_decisions":[{"citation_id":"algorithm:lp:background-hash","decision":"adopted","reason":"reason","adaptation":"adaptation","limitations":"limits"}]}
        assert list(Draft202012Validator(schema).iter_errors(value))
        value["source_decisions"][0]["citation_id"]=ids[0]
        assert not list(Draft202012Validator(schema).iter_errors(value))


def test_proposal_schema_rejects_bare_edit_paths_and_omitted_decisions():
    from modelcrew.modeling_hand import proposal_schema
    from jsonschema import Draft202012Validator
    schema=proposal_schema({"cards":[]}); validator=Draft202012Validator(schema)
    value={"task_graph":[{"id":"q","scope":"scope","conclusion_type":"proposal"}],"proposal":"proposal","questions":[],"source_decisions":[],"edits":[{"op":"replace","path":"/method/steps","value":[]}]}
    assert list(validator.iter_errors(value))
    value["edits"][0]["path"]="/contract/method/steps"
    assert not list(validator.iter_errors(value))
    del value["source_decisions"]
    assert list(validator.iter_errors(value))


def test_m1_pointer_navigation_preserves_root_paths_before_large_subtrees():
    from modelcrew.modeling_hand import review_pointer_navigation
    value={"dossier":{"symbols":[{"id":str(i),"meaning":"symbol","unit":"u"} for i in range(100)],"equations":[{"latex":"x"} for _ in range(100)]},"figures":[],"provenance":[],"presentation":{},"contract_links":[],"schema_version":"1.0.0","validation_plan":[{"id":"check"}],"method_selection":{"model":"LP"}}
    paths=review_pointer_navigation(value)
    assert len(paths)<=60 and "/validation_plan" in paths and "/method_selection" in paths
    assert paths[:len(value)]==["/"+key for key in value]
    assert "/dossier/validation_plan" not in paths
    for path in paths: pointer(value,path)


@pytest.mark.parametrize('auto_correct,valid_second,expected_calls', [(True,True,2),(True,False,2),(False,True,1)])
def test_planning_structural_feedback_is_bounded_and_never_coerces_unknown(tmp_path,auto_correct,valid_second,expected_calls):
    from modelcrew.modeling_hand import planning_result
    valid={'task_graph':[{'id':'q1','scope':'scope','conclusion_type':'simulation'}],
        'category':'simulation','research_question':'root','facts':{}}
    invalid={**valid,'facts':{'symmetry':'unknown_requires_model_review'}}
    class Provider:
        def __init__(self):self.inputs=[]
        def call(self,folder,stage,system,data,**kwargs):
            self.inputs.append(copy.deepcopy(data))
            return (valid if valid_second and len(self.inputs)>1 else invalid),{'call_id':str(len(self.inputs))}
    provider=Provider();payload={'calls':[]}
    if auto_correct and valid_second:
        plan,meta=planning_result(provider,tmp_path,{},payload,auto_correct=auto_correct)
        assert plan.facts=={} and meta['call_id']=='2'
    else:
        with pytest.raises(ValidationError):planning_result(provider,tmp_path,{},payload,auto_correct=auto_correct)
    assert len(provider.inputs)==expected_calls
    assert payload['planning_attempts'][0]['status']=='STRUCTURE_FAIL'
    assert (tmp_path/'planning-validation-0.json').exists()
    if expected_calls==2:
        assert provider.inputs[1]['planning_feedback']['issues'][0]['loc']==('facts','symmetry')


def test_planning_transport_ambiguity_is_never_retried(tmp_path):
    from modelcrew.modeling_hand import planning_result
    class Provider:
        calls=0
        def call(self,*args,**kwargs):
            self.calls+=1
            raise ModelCallError('Model transport outcome unknown; no automatic resend')
    provider=Provider()
    with pytest.raises(ModelCallError):planning_result(provider,tmp_path,{}, {'calls':[]}, auto_correct=True)
    assert provider.calls==1
