"""Editorial migrations must preserve scientific checks and immutable history."""
from copy import deepcopy
import json
import pytest
from modelcrew import assembly_binding as binding
from modelcrew.contracts import digest
from modelcrew.workflow import WorkflowError
from modelcrew.collaboration import historical_review_context, historical_paper_policy_sha256


def context():
    return {'workflow_sha256':'a'*64,'workflow':{'workflow_version':'1','must_load':[],
             'collaboration':{'author_context_must_not_review_own_artifact':True}},
            'documents':[{'path':'resources/paper/chinese-modeling-policy.json',
                'sha256':'b'*64,'text':json.dumps({'policy_version':'1','figures':{'minimum_formal':8}})},
                {'path':'resources/algorithms/index.md','sha256':'c'*64,'text':'scientific methods'}]}


def test_only_editorial_additions_are_accepted():
    old=context();new=deepcopy(old);new['workflow']['layout_requirements']={'single_page':True}
    new['documents'][0]['text']=json.dumps({'policy_version':'2','figures':{'minimum_formal':8},'symbol_table':{'scope':'whole_paper'}})
    new['documents'].append({'path':'resources/paper/reference/main.tex','sha256':'d'*64,'text':'template'})
    assert len(binding.context_delta(old,new))==2
    assert old==context()


@pytest.mark.parametrize('kind',['algorithm','figure_minimum','review_gate','removed_doc'])
def test_substantive_changes_cannot_use_editorial_rebind(kind):
    old=context();new=deepcopy(old)
    if kind=='algorithm':new['documents'][1]['text']='different method'
    if kind=='figure_minimum':new['documents'][0]['text']=json.dumps({'figures':{'minimum_formal':1}})
    if kind=='review_gate':new['workflow']['collaboration']['author_context_must_not_review_own_artifact']=False
    if kind=='removed_doc':new['documents'].pop()
    with pytest.raises(WorkflowError):binding.context_delta(old,new)


def test_historical_policy_scope_is_nested_and_restored_on_failure():
    assert historical_paper_policy_sha256() is None
    with historical_review_context('a'*64,'b'*64):
        assert historical_paper_policy_sha256()=='b'*64
        with pytest.raises(RuntimeError):
            with historical_review_context('c'*64,'d'*64):
                assert historical_paper_policy_sha256()=='d'*64
                raise RuntimeError('failure')
        assert historical_paper_policy_sha256()=='b'*64
    assert historical_paper_policy_sha256() is None

def test_missing_historical_context_is_rejected_as_binding_error():
    with pytest.raises(WorkflowError,match='Writer context is missing'):
        binding.chapter_context({'files':[]},{'question_id':'q1','run_id':'missing'})
