"""Pure parsing and model-transport boundaries; no paid calls."""
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
from modelcrew.collaboration_retrieval import algorithm_context


def baseline():
    return (json.loads((ROOT/'stage-b-plus/examples/contract-v2-snapshot.json').read_text(encoding='utf-8')),
            json.loads((ROOT/'stage-b-plus/examples/valid-bench-dragon.json').read_text(encoding='utf-8')))


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
