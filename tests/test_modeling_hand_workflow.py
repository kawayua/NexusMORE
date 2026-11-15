"""Actual PostgreSQL/graph with deterministic model responses, never user approvals."""
from modelcrew.project_assets import asset_path,local_history
import copy
import json
import uuid
from pathlib import Path

import pytest

from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.collaboration import REQUIRED_CHECKS, sha_file
from modelcrew.modeling_hand import assert_m1
from modelcrew.workflow import Workflow, WorkflowError


class FixtureModel:
    def __init__(self, statuses=None, invalid_selector=False):
        self.statuses=list(statuses or ['PASS']);self.calls=[];self.invalid_selector=invalid_selector
    def call(self,folder,stage,system,data,**kwargs):
        self.calls.append({'stage':stage,'data':copy.deepcopy(data)})
        meta={'call_id':str(uuid.uuid4()),'context_id':str(uuid.uuid4()),'stage':stage,'status':'completed','fixture_model':True}
        graph=[{'id':'q1','scope':'single q1 regression','conclusion_type':'simulation','depends_on':[]}]
        if stage=='planning':return {'task_graph':graph,'category':'geometry','card_ids':['bracketed-root'],'facts':{},'research_question':'root premise review'},meta
        if stage=='modeling':
            baseline=data['baseline']['contract'];steps=baseline['method']['steps']+['Fixture user guidance: '+data['user_guidance']+'; rework='+str(bool(data['M1_feedback']))]
            decisions=[{'citation_id':c['citation_id'],'decision':'adopted','reason':'Need a scalar bracket','adaptation':'Prove premises for this case','limitations':'Caller facts are unknown until model review'} for c in data['references']['cards']]
            return {'task_graph':graph,'edits':[{'op':'replace','path':'/contract/method/steps','value':steps}],
                    'source_decisions':decisions,'proposal':'合成模型输出：'+data['user_guidance'],'questions':[]},meta
        state=self.statuses.pop(0) if self.statuses else 'PASS'
        checks=[{'check_id':c,'status':'PASS','explanation':'Fixture only; no mathematical assessment',
                 'evidence':[{'artifact_id':'contract','selector':'/missing' if self.invalid_selector else '/method'}]} for c in REQUIRED_CHECKS['M1']]
        issues=[]
        if state!='PASS':
            checks[0]['status']=state
            issues=[{'check_id':'model','severity':'blocking','domain':'model','target':'modeling','reason':'Injected issue','recheck':'M1 after revision'}]
        return {'status':state,'checks':checks,'issues':issues},meta


@pytest.fixture
def task(tmp_path):
    contract=json.loads((asset_path(ROOT,'stage-b-plus/examples/contract-v2-snapshot.json')).read_text(encoding='utf-8'))
    package=json.loads((asset_path(ROOT,'stage-b-plus/examples/valid-bench-dragon.json')).read_text(encoding='utf-8'))
    statement=tmp_path/'statement.txt'; statement.write_text('SYNTHETIC Q1 DATA, NOT A REAL STATEMENT',encoding='utf-8')
    contract['inputs']=[{'id':'input0','source_id':'statement','path':str(statement),'sha256':sha_file(statement),'role':'problem_statement'}]
    identifier='test-d2-'+uuid.uuid4().hex
    with Workflow() as w:w.create(identifier,contract,project='automated-tests',math_package=package)
    return identifier


def invoke(w,task,model,**kwargs):
    return w.run_modeling(task,version=w.task(task)['current_version'],actor='TEST_MODELING_OPERATOR',
                          request_id=kwargs.pop('request_id',uuid.uuid4().hex),guidance=kwargs.pop('guidance','Record numerical branch failure explicitly'),model=model,**kwargs)


def test_ready_model_retains_user_gate_and_restores_without_model_calls(task):
    model=FixtureModel()
    with Workflow() as w:
        result=invoke(w,task,model,request_id='same')
        assert result['status']=='ready' and result['version']==2
        assert len(model.calls)==3 and [c['stage'] for c in model.calls]==['planning','modeling','M1']
        assert 'M1_feedback' not in model.calls[-1]['data'] and 'messages' not in model.calls[-1]['data']
        assert [c['data']['nexusmore_guidance']['selector'] for c in model.calls] == ['modeling', 'modeling', 'M1']
        assert model.calls[-1]['data']['nexusmore_guidance']['read_only']
        current=w.inspect(task)
        assert not current['task']['model_approved'] and current['execution'] is None
        assert current['checkpoint_next']==['model_gate']
        assert assert_m1(w,current['task'])['receipt_sha256']==result['receipt_sha256']
    with Workflow() as w:
        replay=w.run_modeling(task,version=1,actor='TEST_MODELING_OPERATOR',request_id='same',guidance='Record numerical branch failure explicitly',model=model)
        assert replay['run_id']==result['run_id'] and len(model.calls)==3
        assert w.resume(task)['task']['current_version']==2
        with pytest.raises(WorkflowError,match='Stale'):
            w.action(task,actor='TEST_SIMULATED_USER',request_id='old-approval',version=1,kind='model',decision='approve')


def test_M1_failure_blocks_approval_and_does_not_solve(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel(['FAIL']),auto_correct=False)
        assert result['status']=='needs_human'
        state=w.inspect(task)
        with pytest.raises(WorkflowError,match='independent M1'):
            w.action(task,actor='TEST_SIMULATED_USER',request_id='fail-approval',version=state['task']['current_version'],kind='model',decision='approve',
                     math_semantic_sha256=state['mathematics']['semantic_sha256'],reason='Synthetic attempt')
        assert w.inspect(task)['execution'] is None


def test_M1_failure_gets_one_real_revision_and_independent_recheck(task):
    model=FixtureModel(['FAIL','PASS'])
    with Workflow() as w:
        result=invoke(w,task,model)
        assert result['status']=='ready' and result['version']==3
        assert [a['status'] for a in result['attempts']]==['FAIL','PASS']
        assert len(model.calls)==5
        assert model.calls[3]['data']['M1_feedback']['status']=='FAIL'
        assert result['attempts'][0]['review_call_id']!=result['attempts'][1]['review_call_id']
        assert not w.task(task)['model_approved']


def test_rework_budget_exhaustion_routes_to_human(task):
    model=FixtureModel(['FAIL','FAIL'])
    with Workflow() as w:
        result=invoke(w,task,model)
        assert result['status']=='needs_human' and len(model.calls)==5
        with pytest.raises(WorkflowError): assert_m1(w,w.task(task))


def test_blocked_review_does_not_consume_automatic_model_rework(task):
    model=FixtureModel(['BLOCKED'])
    with Workflow() as w:
        result=invoke(w,task,model)
        assert result['status']=='blocked' and len(model.calls)==3


def test_user_feedback_creates_new_version_and_old_M1_cannot_pass(task):
    with Workflow() as w:
        first=invoke(w,task,FixtureModel(),guidance='first guidance')
        second=invoke(w,task,FixtureModel(),guidance='Require explicit conditioning threshold discussion')
        assert second['version']==first['version']+1
        assert w.db.execute('SELECT guidance FROM mc_contracts WHERE task_id=%s AND version=%s',(task,second['version'])).fetchone()['guidance']=='Require explicit conditioning threshold discussion'
        assert w.modeling_status(task)[0]['payload']['receipt_sha256']==first['receipt_sha256']
        assert assert_m1(w,w.task(task))['receipt_sha256']==second['receipt_sha256']


def test_changed_evidence_and_input_block_M1_admission(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel())
        file=asset_path(ROOT,result['attempts'][0]['proposal_path'])
        # The authoritative JSON proposal is part of the snapshot; Markdown is a view.
        path=file.with_suffix('.json'); original=path.read_bytes();path.write_bytes(b'{}')
        try:
            with pytest.raises(ValueError,match='changed'):assert_m1(w,w.task(task))
        finally:path.write_bytes(original)
        contract=w.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s',(task,w.task(task)['current_version'])).fetchone()['content']
        input_path=Path(contract['inputs'][0]['path']); input_path.write_text('changed',encoding='utf-8')
        with pytest.raises(WorkflowError,match='input changed'):assert_m1(w,w.task(task))


def test_invalid_evidence_selector_fails_closed(task):
    with Workflow() as w:
        with pytest.raises(WorkflowError,match='does not resolve'):invoke(w,task,FixtureModel(invalid_selector=True))
        assert w.modeling_status(task)[-1]['status']=='failed'
        with pytest.raises(WorkflowError):assert_m1(w,w.task(task))


def test_no_model_is_recalled_on_started_request_or_changed_idempotency_input(task):
    model=FixtureModel()
    with Workflow() as w:
        result=invoke(w,task,model,request_id='claimed')
        w.db.execute("UPDATE mc_modeling_runs SET status='started' WHERE id=%s",(result['run_id'],))
        repeated=w.run_modeling(task,version=1,actor='TEST_MODELING_OPERATOR',request_id='claimed',guidance='Record numerical branch failure explicitly',model=model)
        assert repeated['status']=='started' and len(model.calls)==3
        with pytest.raises(WorkflowError,match='reused'):
            w.run_modeling(task,version=1,actor='TEST_MODELING_OPERATOR',request_id='claimed',guidance='different guidance',model=model)


def test_later_math_change_invalidates_M1(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel())
        current=w.inspect(task);package=copy.deepcopy(current['mathematics']['content'])
        package['dossier']['unproved_or_out_of_scope'].append('New semantic limitation')
        revised=w.action(task,version=result['version'],kind='revise_mathematics',math_package=package,
                         actor='TEST_SIMULATED_USER',request_id='manual-math',reason='new math guidance')
        with pytest.raises(WorkflowError,match='independent M1'):assert_m1(w,revised['task'])


def test_successful_user_action_binds_M1_and_remains_unexecuted_at_commit(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel())
        state=w.inspect(task)
        with pytest.raises(RuntimeError,match='Injected crash'):
            w.action(task,version=result['version'],actor='TEST_SIMULATED_USER',request_id='approve-after-m1',kind='model',decision='approve',
                     math_semantic_sha256=state['mathematics']['semantic_sha256'],reason='Synthetic user approval for gate integration test',crash_after_commit=True)
        t=w.task(task)
        assert t['model_approved'] and t['execution_id'] is None
        event=w.db.execute("SELECT payload FROM mc_events WHERE task_id=%s AND kind='model_approve' ORDER BY id DESC LIMIT 1",(task,)).fetchone()['payload']
        assert event['modeling_snapshot']['receipt_sha256']==result['receipt_sha256']
        assert event['math_snapshot']['semantic_sha256']==state['mathematics']['semantic_sha256']


def test_API_modeling_and_user_feedback_route(monkeypatch,task):
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    import modelcrew.modeling_hand as module
    model=FixtureModel();monkeypatch.setattr(module,'JsonModel',lambda:model)
    with TestClient(create_app()) as client:
        answer=client.post('/tasks/'+task+'/modeling/runs',json={'version':1,'actor':'TEST_MODELING_OPERATOR','request_id':'api-model','guidance':'Clarify root conditioning'})
        assert answer.status_code==200 and answer.json()['status']=='ready'
        history=client.get('/tasks/'+task+'/modeling')
        assert history.status_code==200 and history.json()[-1]['version']==2
        stale=client.post('/tasks/'+task+'/modeling/runs',json={'version':1,'actor':'TEST_MODELING_OPERATOR','request_id':'stale-model','guidance':'stale feedback'})
        assert stale.status_code==409 and len(model.calls)==3


def test_missing_input_does_not_make_a_paid_planning_call(task):
    model=FixtureModel()
    with Workflow() as w:
        contract=w.inspect(task)['contract']['content'];Path(contract['inputs'][0]['path']).unlink()
        with pytest.raises((ValueError,OSError)):invoke(w,task,model)
        assert model.calls==[]
        assert w.modeling_status(task)[-1]['status']=='failed'


def test_transport_failure_is_distinct_and_not_retried(task):
    from modelcrew.model_client import ModelCallError
    class Unavailable:
        def __init__(self):self.calls=0
        def call(self,*args,**kwargs):
            self.calls+=1
            raise ModelCallError('Model transport outcome unknown; no automatic resend')
    model=Unavailable()
    with Workflow() as w:
        with pytest.raises(ModelCallError):invoke(w,task,model,request_id='unknown-transport')
        row=w.modeling_status(task)[-1]
        assert row['status']=='unknown' and row['payload']['failure_domain']=='infrastructure' and model.calls==1
        response=w.run_modeling(task,version=1,actor='TEST_MODELING_OPERATOR',request_id='unknown-transport',guidance='Record numerical branch failure explicitly',model=model)
        assert response['status']=='unknown' and model.calls==1


def test_schema_failure_has_one_bounded_repair_without_publishing_invalid_contract(task):
    class InvalidFirst(FixtureModel):
        def __init__(self):super().__init__();self.invalid=True
        def call(self,*args,**kwargs):
            value,meta=super().call(*args,**kwargs)
            if args[1]=='modeling' and self.invalid:
                self.invalid=False
                value['edits']=[{'op':'add','path':'/mathematics/method_selection/unsupported_field','value':'invalid'}]
            return value,meta
    model=InvalidFirst()
    with Workflow() as w:
        result=invoke(w,task,model)
        assert result['status']=='ready' and result['version']==2 and len(model.calls)==4
        assert [a['status'] for a in result['attempts']]==['STRUCTURE_FAIL','PASS']
        assert model.calls[2]['data']['M1_feedback']['stage']=='structure'
        assert 'mathematical_package_schema' in model.calls[2]['data']


def test_explicit_read_only_recheck_preserves_fail_and_cannot_loop(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel(['FAIL']),auto_correct=False)
        old_key=result['receipt_sha256'];old_snapshot=result['snapshot_sha256']
        reviewer=FixtureModel()
        second=w.recheck_modeling(task,version=result['version'],run_id=result['run_id'],actor='TEST_REVIEW_OPERATOR',request_id='recheck-once',rationale='Inspect a contradictory assertion against original evidence',model=reviewer)
        assert second['status']=='ready' and len(reviewer.calls)==1
        assert second['snapshot_sha256']==old_snapshot and second['review_recheck']['previous_receipt_sha256']==old_key
        assert second['receipt_sha256']!=old_key and not w.task(task)['model_approved']
        again=w.recheck_modeling(task,version=result['version'],run_id=result['run_id'],actor='TEST_REVIEW_OPERATOR',request_id='recheck-once',rationale='Inspect a contradictory assertion against original evidence',model=reviewer)
        assert again['status']=='ready' and len(reviewer.calls)==1
        with pytest.raises(WorkflowError,match='budget'):
            w.recheck_modeling(task,version=result['version'],run_id=result['run_id'],actor='TEST_REVIEW_OPERATOR',request_id='another',rationale='try again',model=reviewer)
        assert len(reviewer.calls)==1


def test_recheck_is_not_a_bypass_for_changed_model_or_still_failed_review(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel(['FAIL']),auto_correct=False)
        repeated=w.recheck_modeling(task,version=result['version'],run_id=result['run_id'],actor='TEST_REVIEW_OPERATOR',request_id='still-fail',rationale='Original issue disputed',model=FixtureModel(['FAIL']))
        assert repeated['status']=='needs_human'
        with pytest.raises(WorkflowError):assert_m1(w,w.task(task))


@pytest.mark.parametrize('declared,per_check,expected',[('FAIL','PASS','ready'),('PASS','FAIL','needs_human')])
def test_overall_summary_is_programmatically_derived_without_changing_semantic_findings(task,declared,per_check,expected):
    class WrongSummary(FixtureModel):
        def call(self,*args,**kwargs):
            value,meta=super().call(*args,**kwargs)
            if args[1]=='M1':value['status']=declared
            return value,meta
    with Workflow() as w:
        result=invoke(w,task,WrongSummary([per_check]),auto_correct=False)
        assert result['status']==expected
        admission=next((asset_path(ROOT,result['folder'])).rglob('admission.json'))
        details=json.loads(admission.read_text(encoding='utf-8'))
        assert details['aggregation_mismatch'] and not details['semantic_checks_modified']
        assert details['reported_status']==declared and details['derived_status']==per_check


def test_completed_cached_recheck_recovers_without_resending_model(task):
    from modelcrew.model_client import ModelCallError
    class ResponseThenCrash(FixtureModel):
        def call(self,folder,stage,system,data,**kwargs):
            value,meta=super().call(folder,stage,system,data,**kwargs)
            prefix=Path(folder)/('M1-'+meta['call_id'])
            Path(str(prefix)+'-response.json').write_text(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}),encoding='utf-8')
            Path(str(prefix)+'-metadata.json').write_text(json.dumps(meta),encoding='utf-8')
            raise ModelCallError('Response persisted before injected interruption')
    with Workflow() as w:
        result=invoke(w,task,FixtureModel(['FAIL']),auto_correct=False)
        model=ResponseThenCrash()
        args={'version':result['version'],'run_id':result['run_id'],'actor':'TEST_REVIEW_OPERATOR','request_id':'recover-cached','rationale':'Recheck original evidence','model':model}
        with pytest.raises(ModelCallError):w.recheck_modeling(task,**args)
        assert w.modeling_status(task)[-1]['status']=='unknown' and len(model.calls)==1
        recovered=w.recheck_modeling(task,**args)
        assert recovered['status']=='ready' and len(model.calls)==1
        assert recovered['review_recheck']['recovered_without_model_call']

def test_explicit_model_approval_can_defer_fixture_dispatch_across_restart(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel())
        state=w.inspect(task)
        arguments=dict(actor='TEST_SIMULATED_USER',request_id='deferred-approval',version=result['version'],kind='model',decision='approve',
                       math_semantic_sha256=state['mathematics']['semantic_sha256'],reason='Synthetic approval for reviewed execution',defer_execution=True)
        current=w.action(task,**arguments)
        assert current['task']['model_approved'] and current['task']['phase']=='SOLVING'
        assert current['execution'] is None and current['task']['result_revision']==0
        assert w.action(task,**arguments)['execution'] is None
    with Workflow() as w:
        state=w.resume(task)
        assert state['task']['model_approved'] and state['execution'] is None
        assert state['execution_attempts']==[] and state['execution_receipts']==[]
        with pytest.raises(WorkflowError,match='deferral'):
            w.action(task,actor='TEST',request_id='invalid',version=result['version'],kind='result',decision='approve',defer_execution=True)


def test_changed_frozen_guidance_blocks_ready_model_admission(task):
    with Workflow() as w:
        result = invoke(w, task, FixtureModel())
        assert result['status'] == 'ready'
        folder = ROOT / result['folder']
        (folder / 'collaboration-guidance.json').write_bytes(b'CHANGED SYNTHETIC POLICY')
        with pytest.raises(ValueError, match='Frozen collaboration guidance changed'):
            assert_m1(w, w.task(task))
        assert not w.task(task)['model_approved']
        assert w.inspect(task)['execution'] is None


class MalformedRecordedM1(FixtureModel):
    def call(self, folder, stage, system, data, **kwargs):
        value, meta=super().call(folder,stage,system,data,**kwargs)
        if stage=="M1":
            assert "sources" in data["allowed_artifact_ids"]
            assert "/cards" in data["valid_pointer_examples"]["sources"]
            value["checks"][0]["note"]=None
            response=Path(folder)/("M1-"+meta["call_id"]+"-response.json")
            response.write_text(json.dumps({"choices":[{"finish_reason":"stop","message":{"content":json.dumps(value)}}]}),encoding="utf-8")
            metadata={**meta,"http_status":200,"response_sha256":sha_file(response)}
            response.with_name(response.name.replace("-response.json","-metadata.json")).write_text(json.dumps(metadata),encoding="utf-8")
        return value,meta


def test_malformed_complete_m1_gets_one_fresh_review_without_editing_original(task):
    with Workflow() as w:
        with pytest.raises(ValueError): invoke(w,task,MalformedRecordedM1())
        row=w.modeling_status(task)[-1]; payload=row["payload"]
        folder=asset_path(ROOT,payload["folder"]); response=next(folder.rglob("M1-*-response.json")); original=sha_file(response)
        reviewer=FixtureModel()
        args=dict(version=row["version"],run_id=str(row["id"]),actor="TEST_OPERATOR",request_id="malformed-once",rationale="Original unadmitted reply contained an extra note field; independently review unchanged evidence",model=reviewer)
        result=w.recheck_modeling(task,**args)
        assert result["status"]=="ready" and result["snapshot_sha256"]==payload["snapshot_sha256"]
        assert result["review_recheck"]["previous_response_sha256"]==original and result["review_recheck"]["previous_receipt_sha256"] is None
        assert sha_file(response)==original and len(reviewer.calls)==1 and not w.task(task)["model_approved"]
        assert w.recheck_modeling(task,**args)["status"]=="ready" and len(reviewer.calls)==1
        with pytest.raises(WorkflowError,match="budget"):
            w.recheck_modeling(task,**{**args,"request_id":"another"})


@pytest.mark.parametrize("damage",["input","metadata"])
def test_malformed_review_recheck_rejects_changed_inputs_or_incomplete_response(task,damage):
    with Workflow() as w:
        with pytest.raises(ValueError): invoke(w,task,MalformedRecordedM1())
        row=w.modeling_status(task)[-1]; folder=asset_path(ROOT,row["payload"]["folder"])
        if damage=="input":
            c=w.db.execute("SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s",(task,row["version"])).fetchone()["content"]
            Path(c["inputs"][0]["path"]).write_text("changed fixture",encoding="utf-8")
        else:
            metadata=next(folder.rglob("M1-*-metadata.json")); value=json.loads(metadata.read_text(encoding="utf-8")); value["http_status"]=500; metadata.write_text(json.dumps(value),encoding="utf-8")
        reviewer=FixtureModel()
        with pytest.raises(ValueError):
            w.recheck_modeling(task,version=row["version"],run_id=str(row["id"]),actor="TEST_OPERATOR",request_id="refuse-damage",rationale="Try invalid review",model=reviewer)
        assert not reviewer.calls and not w.task(task)["model_approved"]


def test_malformed_review_recheck_keeps_original_unanswered_questions(task):
    class WithQuestions(MalformedRecordedM1):
        def call(self,folder,stage,system,data,**kwargs):
            value,meta=super().call(folder,stage,system,data,**kwargs)
            if stage=="modeling": value["questions"]=["Unanswered scope question"]
            return value,meta
    with Workflow() as w:
        with pytest.raises(ValueError): invoke(w,task,WithQuestions())
        row=w.modeling_status(task)[-1]
        result=w.recheck_modeling(task,version=row["version"],run_id=str(row["id"]),actor="TEST_OPERATOR",request_id="keep-questions",rationale="Check malformed response without bypassing questions",model=FixtureModel())
        assert result["status"]=="blocked" and result["open_questions"]==["Unanswered scope question"]
        assert not w.task(task)["model_approved"]
        with pytest.raises(WorkflowError): assert_m1(w,w.task(task))


def test_malformed_recheck_exhausts_budget_without_becoming_unknown_or_resending(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel(["FAIL"]),auto_correct=False)
        reviewer=MalformedRecordedM1()
        args=dict(version=result["version"],run_id=result["run_id"],actor="TEST_OPERATOR",request_id="reject-malformed",rationale="Independently review original evidence",model=reviewer)
        with pytest.raises(ValueError): w.recheck_modeling(task,**args)
        row=w.modeling_status(task)[-1]
        assert row["status"]=="needs_human" and row["payload"]["review_recheck"]["status"]=="NOT_ADMITTED"
        assert w.recheck_modeling(task,**args)["status"]=="needs_human" and len(reviewer.calls)==1
        with pytest.raises(WorkflowError,match="budget"):w.recheck_modeling(task,**{**args,"request_id":"resend"})
        assert not w.task(task)["model_approved"]
