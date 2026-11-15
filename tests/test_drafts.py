from modelcrew.project_assets import asset_path,local_history
import json,uuid
import pytest
from modelcrew.contracts import ROOT,validate
from modelcrew.drafts import generate_draft

@pytest.fixture
def scratch():
    p=asset_path(ROOT,'stage-b/runs')/('draft-tests-'+uuid.uuid4().hex);p.mkdir(parents=True);return p

class FakeClient:
    def __init__(self,truncate=False,change=False):self.truncate=truncate;self.change=change
    def post(self,url,**kwargs):
        request=json.loads(kwargs['json']['messages'][1]['content'])
        c=json.loads((asset_path(ROOT,'contracts/examples/valid-2024-a-q1.json')).read_text(encoding='utf-8'))
        c['sources']=request['authoritative_sources'];c['inputs']=[{k:v for k,v in x.items() if k!='structure'} for x in request['inputs_with_observed_structures']]
        for group in ['parameters','assumptions']:
            for item in c[group]:item['source_id']='source0'
        if self.change:c['inputs'][0]['sha256']='0'*64
        content=json.dumps({'contract':c,'proposal':'TEST_ONLY Agent方案','next_steps':['等待用户审阅'],'open_questions':['请确认方向']},ensure_ascii=False)
        class Response:
            status_code=200
            def json(inner):return {'choices':[{'finish_reason':'length' if self.truncate else 'stop','message':{'content':content}}],'model':'TEST_ONLY','usage':{'total_tokens':42}}
        return Response()

def setup(monkeypatch,scratch):
    from modelcrew import drafts
    monkeypatch.setattr(drafts,'model_config',lambda:{'MODELCREW_LLM_API_KEY':'TEST_FAKE_KEY','MODELCREW_LLM_MODEL':'TEST_ONLY','MODELCREW_LLM_BASE_URL':'https://unused.invalid'})
    statement=scratch/'statement.txt';statement.write_text('TEST_ONLY题面',encoding='utf-8');return statement

def test_model_draft_saved_but_not_approved(monkeypatch,scratch):
    statement=setup(monkeypatch,scratch);folder=scratch/'bundle'
    value=generate_draft(statement,[],folder,'第一小题',client=FakeClient())
    c=json.loads((folder/'contract.json').read_text(encoding='utf-8'));validate(c)
    assert value['status']=='draft_awaiting_review' and value['approval']=='not_granted'
    assert len(value['pending_questions'])==2 and value['usage']['total_tokens']==42
    assert 'TEST_FAKE_KEY' not in (folder/'request.json').read_text(encoding='utf-8')
    with pytest.raises(FileExistsError):generate_draft(statement,[],folder,'第一小题',client=FakeClient())

@pytest.mark.parametrize('truncate,change',[(True,False),(False,True)])
def test_failed_draft_attempt_is_preserved(monkeypatch,scratch,truncate,change):
    statement=setup(monkeypatch,scratch);folder=scratch/'failed'
    with pytest.raises(ValueError):generate_draft(statement,[],folder,'第一小题',client=FakeClient(truncate,change))
    meta=json.loads((folder/'metadata.json').read_text(encoding='utf-8'));assert meta['status']=='failed'
    assert not (folder/'contract.json').exists() and (folder/'model-output.txt').exists()
