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
from proposal_fixtures import document, audit


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
                    'source_decisions':decisions,'proposal':'合成模型输出：'+data['user_guidance'],'questions':[],
                    'review_document':document(baseline['sources'][0]['id'])},meta
        state=self.statuses.pop(0) if self.statuses else 'PASS'
        checks=[{'check_id':c,'status':'PASS','explanation':'Fixture only; no mathematical assessment',
                 'evidence':[{'artifact_id':'contract','selector':'/missing' if self.invalid_selector else '/method'}]} for c in REQUIRED_CHECKS['M1']]
        issues=[]
        if state!='PASS':
            checks[0]['status']=state
            issues=[{'check_id':'model','severity':'blocking','domain':'model','target':'modeling','reason':'Injected issue','recheck':'M1 after revision'}]
        return {'status':state,'checks':checks,'issues':issues,'proposal_audit':audit()},meta


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


@pytest.mark.parametrize('initial_status',['FAIL','BLOCKED'])
def test_explicit_read_only_recheck_preserves_fail_and_cannot_loop(task,initial_status):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel([initial_status]),auto_correct=False)
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



def test_summary_only_new_proposal_cannot_publish_contract_or_reach_M1(task):
    class SummaryOnly(FixtureModel):
        def call(self,*args,**kwargs):
            value,meta=super().call(*args,**kwargs)
            if args[1]=='modeling':value.pop('review_document')
            return value,meta
    model=SummaryOnly()
    with Workflow() as w:
        result=invoke(w,task,model,auto_correct=False)
        assert result['status']=='needs_human' and result['attempts'][0]['status']=='STRUCTURE_FAIL'
        assert w.task(task)['current_version']==1 and not w.task(task)['model_approved']
        assert [c['stage'] for c in model.calls]==['planning','modeling']


def test_new_M1_blanket_pass_without_section_audit_is_blocked(task):
    class BlankPass(FixtureModel):
        def call(self,*args,**kwargs):
            value,meta=super().call(*args,**kwargs)
            if args[1]=='M1':value.pop('proposal_audit')
            return value,meta
    with Workflow() as w:
        result=invoke(w,task,BlankPass(),auto_correct=False)
        assert result['status']=='blocked'
        with pytest.raises(WorkflowError,match='independent M1'):assert_m1(w,w.task(task))
        assert not w.task(task)['model_approved']


def test_subcriterion_math_failure_overrides_declared_M1_pass(task):
    class WrongOrder(FixtureModel):
        def call(self,*args,**kwargs):
            value,meta=super().call(*args,**kwargs)
            if args[1]=='M1':
                finding=next(x for x in value['proposal_audit'] if x['criterion']=='convergence_reasoning')
                finding.update(status='FAIL',explanation='合成反例：加密比值1.5不能证明二阶收敛。')
            return value,meta
    with Workflow() as w:
        result=invoke(w,task,WrongOrder(),auto_correct=False)
        assert result['status']=='needs_human' and result['attempts'][-1]['status']=='FAIL'
        assert not w.task(task)['model_approved']


def test_readable_proposal_edit_after_M1_blocks_new_admission(task):
    with Workflow() as w:
        result=invoke(w,task,FixtureModel())
        assert assert_m1(w,w.task(task))
        path=ROOT/result['attempts'][-1]['proposal_path']
        path.write_text('Changed user-facing proposal',encoding='utf-8')
        with pytest.raises(WorkflowError,match='Readable modeling proposal changed'):assert_m1(w,w.task(task))


def test_recheck_precondition_rejection_does_not_claim_or_fence_task(task):
    from modelcrew.business_adapter import BusinessAdapter
    from modelcrew.business_store import BusinessStore
    with Workflow() as w:
        w.setup()
        result=invoke(w,task,FixtureModel())
        current=w.task(task)
        sha=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,result['version'])).fetchone()['sha256']
    key='recheck-already-passed'
    request={'contract_version':'1.0.0','operation':'modeling_recheck','request_id':key,
        'expected_binding':{'task_id':task,'run_id':result['run_id'],'version':result['version'],'contract_sha256':sha},
        'arguments':{'task_id':task,'run_id':result['run_id'],'body':{'version':result['version'],
            'actor':'TEST_REVIEW_OPERATOR','request_id':key,'rationale':'An already passed review cannot be challenged'}}}
    response=BusinessAdapter().invoke('modeling_recheck',request)
    assert response['status']=='error' and response['error']['code']=='workflow_conflict'
    with Workflow() as w:
        store=BusinessStore(w.db)
        scope={'project_id':current['project_id'],'task_id':task,'run_id':result['run_id']}
        assert store.get(scope,'modeling_recheck',key) is None
        assert store.unresolved('task:'+task) is None
        assert not w.task(task)['model_approved']


def test_internal_reference_repair_receives_located_feedback_before_any_publish(task):
    class InternalFirst(FixtureModel):
        def __init__(self):super().__init__();self.invalid=True
        def call(self,*args,**kwargs):
            value,meta=super().call(*args,**kwargs)
            if args[1]=='modeling' and self.invalid:
                self.invalid=False
                value['review_document']['verification_plan']+=' eq:heat2d'
            return value,meta
    model=InternalFirst()
    with Workflow() as w:
        result=invoke(w,task,model)
        assert result['status']=='ready' and result['version']==2
        assert [a['status'] for a in result['attempts']]==['STRUCTURE_FAIL','PASS']
        correction=model.calls[2]['data']
        error=correction['M1_feedback']['validation_errors'][0]
        assert error['loc']==['review_document','verification_plan'] and error['matched_text']=='eq:heat2d'
        assert 'eq:heat2d' in correction['readable_prose_rule']['forbidden_examples']
        assert [c['stage'] for c in model.calls]==['planning','modeling','modeling','M1']
        assert not w.task(task)['model_approved']


def test_missing_m1_item_routes_to_review_recovery_without_rewriting_author(task):
    class MissingReviewItem(FixtureModel):
        def call(self,*args,**kwargs):
            value,meta=super().call(*args,**kwargs)
            if args[1]=='M1':value['checks']=[x for x in value['checks'] if x['check_id']!='validation_plan']
            return value,meta
    model=MissingReviewItem()
    with Workflow() as w:
        result=invoke(w,task,model)
        assert result['status']=='needs_human' and result['rework_target']=='recovery'
        assert result['failure_domain']=='review_output'
        assert result['review_coverage']['missing']==['validation_plan']
        assert [c['stage'] for c in model.calls]==['planning','modeling','M1']
        assert not w.task(task)['model_approved']
        from modelcrew.collaboration import CollaborationStore,Receipt
        receipt=CollaborationStore(asset_path(ROOT,result['folder'])/'records').load(Receipt,result['receipt_sha256'])
        assert receipt.status=='BLOCKED' and len(receipt.checks)==6
        assert next(x for x in receipt.checks if x.check_id=='validation_plan').status=='BLOCKED'


class RecordedPartialM1(FixtureModel):
    def call(self,folder,stage,system,data,**kwargs):
        value,meta=super().call(folder,stage,system,data,**kwargs)
        if stage=='modeling':value['edits']=[]
        if stage=='M1':
            value['checks']=[c for c in value['checks'] if c['check_id']!='validation_plan']
            response=Path(folder)/('M1-'+meta['call_id']+'-response.json')
            response.write_text(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}),encoding='utf-8')
            meta.update(http_status=200,finish_reason='stop',response_sha256=sha_file(response))
            response.with_name(response.name.replace('-response.json','-metadata.json')).write_text(json.dumps(meta),encoding='utf-8')
        return value,meta


def test_cached_partial_original_m1_recovers_without_new_model_call(task,monkeypatch):
    from modelcrew import modeling_hand as mh
    original=mh.admit_m1_answer
    def old_bug(*a,**k):raise ValueError('Required M1 check missing: validation_plan')
    monkeypatch.setattr(mh,'admit_m1_answer',old_bug)
    model=RecordedPartialM1(['FAIL'])
    with Workflow() as w:
        with pytest.raises(ValueError):invoke(w,task,model,request_id='old-partial-review')
        row=w.modeling_status(task)[-1]
        folder=asset_path(ROOT,row['payload']['folder'])
        raw=next(folder.rglob('M1-*-response.json'));raw_hash=sha_file(raw)
        monkeypatch.setattr(mh,'admit_m1_answer',original)
        result=mh.recover_completed_modeling_review(w,task,str(row['id']))
        assert result['status']=='needs_human' and result['cached_review_recovery']['no_model_call']
        assert result['review_coverage']['missing']==['validation_plan']
        assert len(model.calls)==3 and sha_file(raw)==raw_hash
        assert not w.task(task)['model_approved']
        assert mh.recover_completed_modeling_review(w,task,str(row['id']))['receipt_sha256']==result['receipt_sha256']
        assert len(model.calls)==3


def test_business_status_recovers_legacy_partial_review_and_releases_fence(task,monkeypatch):
    from modelcrew import modeling_hand as mh
    from modelcrew.business_adapter import BusinessAdapter
    from modelcrew.business_store import BusinessStore
    original=mh.admit_m1_answer
    def old_bug(*a,**k):raise ValueError('Required M1 check missing: validation_plan')
    monkeypatch.setattr(mh,'admit_m1_answer',old_bug)
    model=RecordedPartialM1(['FAIL'])
    class RecordingWorkflow(Workflow):
        def run_modeling(self,task_id,**kwargs):return super().run_modeling(task_id,model=model,**kwargs)
    class OldAdapter(BusinessAdapter):
        def _reconcile(self,*a,**k):pass
    with Workflow() as w:
        w.setup();t=w.task(task)
        baseline=w.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=1',(task,)).fetchone()['content']
        from modelcrew.mathematics import latest
        package=latest(w,task,1)['content']
        from modelcrew.business_artifacts import register_input,ArtifactRegistry
        new_task=task+'-registered';owner={'project_id':t['project_id'],'task_id':new_task,'version':1}
        item=register_input(w,ROOT,owner,baseline['inputs'][0]['path'])
        path,sha_input=ArtifactRegistry(w,ROOT).resolve_input('artifact:'+item['artifact_id'],owner)
        baseline['inputs'][0]['path']=path;baseline['inputs'][0]['sha256']=sha_input
        w.create(new_task,baseline,project=t['project_id'],math_package=package)
        task=new_task;t=w.task(task)
        sha=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=1',(task,)).fetchone()['sha256']
    key='legacy-partial-m1'
    request={'contract_version':'1.0.0','operation':'modeling_start','request_id':key,
        'expected_binding':{'task_id':task,'version':1,'contract_sha256':sha},
        'arguments':{'task_id':task,'body':{'actor':'TEST_HOST','version':1,'request_id':key,'guidance':'Synthetic cached review recovery'}}}
    old=OldAdapter(RecordingWorkflow).invoke('modeling_start',request)
    assert old['status']=='outcome_unknown'
    monkeypatch.setattr(mh,'admit_m1_answer',original)
    adapter=BusinessAdapter()
    response=adapter.invoke('operation_status',{'contract_version':'1.0.0','operation':'operation_status',
        'arguments':{'project_id':t['project_id'],'task_id':task,'operation_name':'modeling_start','request_id':key}})
    assert response['receipt']['state']=='succeeded'
    assert len(model.calls)==3
    with Workflow() as w:
        assert BusinessStore(w.db).unresolved('task:'+task) is None
        assert not w.task(task)['model_approved']
    replay=adapter.invoke('modeling_start',request)
    assert replay['replayed'] and replay['status']!='outcome_unknown'


def prepared_file(w, task, *, mutate=None):
    from modelcrew.algorithm_lookup import builtin_context
    from modelcrew.mathematics import latest
    references=builtin_context('geometry',card_ids=['bracketed-root'])
    current=w.task(task);version=current['current_version']
    contract=w.db.execute('SELECT content,sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
    proposal={'task_graph':[{'id':'q1','scope':'synthetic prepared proposal','conclusion_type':'simulation','depends_on':[]}],
        'edits':[],'source_decisions':[{'citation_id':c['citation_id'],'decision':'adopted',
        'reason':'Synthetic explicit decision','adaptation':'Check bracketed premises','limitations':'No computation or user approval'} for c in references['cards']],
        'proposal':'合成完整方案；正式显示从结构化正文渲染。','questions':[],
        'review_document':document(contract['content']['sources'][0]['id'])}
    value={'binding':{'task_id':task,'version':version,'contract_sha256':contract['sha256'],
                     'math_package_sha256':digest(latest(w,task,version)['content'])},
        'plan':{'task_graph':proposal['task_graph'],'category':'geometry','card_ids':['bracketed-root'],
                'facts':{},'research_question':'Synthetic prepared proposal premises'},
        'proposal':proposal,'authorship':{'kind':'prepared_file','statement':'Synthetic imported author; not a provider call'}}
    if mutate:mutate(value)
    path=ROOT/'runs'/'test-prepared-proposals'/str(uuid.uuid4())/'submission.json'
    path.parent.mkdir(parents=True);path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha_file(path)},value


def test_prepared_proposal_enters_real_review_without_model_rewrite(task):
    model=FixtureModel()
    with Workflow() as w:
        files,source=prepared_file(w,task)
        result=invoke(w,task,model,proposal_files=files,request_id='prepared-same')
        assert result['status']=='ready' and result['version']==1
        assert [c['stage'] for c in model.calls]==['M1']
        assert result['proposal_import']['content_rewritten'] is False
        assert result['proposal_import']['provider_author_call'] is False
        folder=ROOT/result['folder'];proposal=json.loads((folder/'attempt-0/proposal.json').read_text(encoding='utf-8'))
        from modelcrew.modeling_proposal import ReviewDocument
        assert proposal['review_document']==ReviewDocument.model_validate(source['proposal']['review_document']).model_dump(mode='json')
        assert (folder/'prepared-proposal.json').read_bytes()==(ROOT/files['path']).read_bytes()
        assert not w.task(task)['model_approved']
        assert assert_m1(w,w.task(task))['receipt_sha256']==result['receipt_sha256']
        replay=invoke(w,task,model,proposal_files=files,request_id='prepared-same')
        assert replay['run_id']==result['run_id'] and len(model.calls)==1


def test_prepared_review_failure_never_regenerates_imported_prose(task):
    model=FixtureModel(['FAIL'])
    with Workflow() as w:
        files,_=prepared_file(w,task)
        result=invoke(w,task,model,proposal_files=files,auto_correct=True)
        assert result['status']=='needs_human' and [c['stage'] for c in model.calls]==['M1']
        assert len(result['attempts'])==1 and result['attempts'][0]['status']=='FAIL'
        assert not w.task(task)['model_approved']


@pytest.mark.parametrize('defect',['stale','edits','changed','outside','decisions'])
def test_invalid_prepared_proposal_is_rejected_before_modeling_run(task,tmp_path,defect):
    from modelcrew.business_contract import BusinessContractError
    model=FixtureModel()
    with Workflow() as w:
        def mutate(value):
            if defect=='stale':value['binding']['math_package_sha256']='f'*64
            if defect=='edits':value['proposal']['edits']=[{'op':'replace','path':'/contract/problem/title','value':'not allowed'}]
            if defect=='decisions':value['proposal']['source_decisions']=[]
        files,_=prepared_file(w,task,mutate=mutate)
        if defect=='changed':(ROOT/files['path']).write_text('{}',encoding='utf-8')
        if defect=='outside':
            files['path']=str(ROOT.parent/'outside-prepared-not-readable.json')
        with pytest.raises(BusinessContractError):invoke(w,task,model,proposal_files=files)
        assert w.modeling_status(task)==[] and model.calls==[]
