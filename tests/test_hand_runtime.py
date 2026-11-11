"""Real DB orchestration tests with explicitly synthetic provider/executor replies."""
import json,uuid,copy
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from modelcrew.config import ROOT
from modelcrew.workflow import Workflow,WorkflowError
from modelcrew import hand_runtime as hr
from modelcrew.model_client import ModelCallError
from modelcrew.collaboration import REQUIRED_CHECKS,sha_file
from modelcrew.modeling_paper import policy

class Provider:
    def __init__(self,fail_gate=None,domain='implementation',broken_code=False):
        self.calls=[];self.fail_gate=fail_gate;self.domain=domain;self.broken_code=broken_code
    def call(self,folder,stage,system,data,**kw):
        self.calls.append((stage,copy.deepcopy(data)))
        meta={'call_id':str(uuid.uuid4()),'context_id':str(uuid.uuid4()),'stage':stage,'status':'completed','fixture_only':True}
        if stage=='Coder':
            code='bad Python !!!' if self.broken_code else 'print("SYNTHETIC STATE TEST, NOT A REAL SOLVER")'
            return {'code':code,'explanation':'TEST_ONLY'},meta
        if stage=='Writer-plan':return {'claims':[{'id':'C1','statement':'测试证据','evidence':[{'artifact_id':'result','selector':'/values'}]}],'sections':['问题分析','结果分析'],'references':[],'figure_plan':[{'figure_id':fig['id'],'claim_id':'C1','section':'结果分析'} for fig in data['evidence']['figure-catalog']['figures'] if fig['formal']]},meta
        if stage=='Writer':
            cat=data['evidence']['figure-catalog'];text='\n\n'.join('## '+s+'\n根据题目条件分析模型与求解结果，并说明单位、假设与局限。'*3 for s in policy()['required_sections'])
            for fig in cat['figures']:
                n=fig['number'];text+=f'\n\n正文图{n}说明数据。\n\n![图{n} 测试数据]({fig["files"]["png"]["path"]})\n\n图{n} 测试数据。'
            return {'markdown':text},meta
        gate=stage;failed=self.fail_gate==gate
        if failed:self.fail_gate=None
        aid='outline' if gate=='W1' else 'result'
        selector='/claims' if gate=='W1' else '/result.json'
        checks=[{'check_id':c,'status':'FAIL' if failed and i==0 else 'PASS','evidence':[{'artifact_id':aid,'selector':selector}],'explanation':'SYNTHETIC ONLY'} for i,c in enumerate(REQUIRED_CHECKS[gate])]
        target={'implementation':'coding','model':'modeling','infrastructure':'recovery','writing':'writing','explanation':'writing' if gate=='W1' else 'coding'}[self.domain]
        issues=[{'check_id':checks[0]['check_id'],'severity':'error','domain':self.domain,'target':target,'reason':'Injected failure','recheck':'New frozen version'}] if failed else []
        return {'status':'FAIL' if failed else 'PASS','checks':checks,'issues':issues},meta

@pytest.fixture
def task(tmp_path):
    c=json.loads((ROOT/'contracts/examples/valid-2024-a-q1.json').read_text(encoding='utf-8-sig'))
    p=tmp_path/'input.txt';p.write_text('SYNTHETIC INPUT',encoding='utf-8')
    c['inputs']=[{'id':'input0','source_id':'statement','path':str(p),'sha256':sha_file(p),'role':'problem_statement'}]
    c['outputs']=[{'id':'result','path':'result.json','format':'json','fields':[{'name':'values','shape':[3],'unit':'1'}],'decimal_places':None}]
    identifier='test-hand-'+uuid.uuid4().hex
    with Workflow() as w:
        w.create(identifier,c,executor_key='pending-code')
        w.action(identifier,actor='TEST_SIMULATED_USER',request_id='approved-model',version=1,kind='model',decision='approve',defer_execution=True)
    return identifier

@pytest.fixture
def execution(monkeypatch,tmp_path):
    root=ROOT/'tmp'/('runtime-executor-'+uuid.uuid4().hex);root.mkdir(parents=True)
    monkeypatch.setattr(hr,'executor_root',lambda:root)
    calls=[]
    def trace(w,task,version,service,tool,args,key):
        calls.append(tool);jid=args.get('job_id',args.get('run_id'));job=hr.read(root/'jobs'/jid/'job.json')
        folder=root/'runs'/jid/'artifacts';folder.mkdir(parents=True,exist_ok=True)
        full='full-' in jid
        value={'TEST_SYNTHETIC':True,'values':[1,4,9]}
        (folder/'result.json').write_text(json.dumps(value),encoding='utf-8')
        if full:
            row=w.db.execute('SELECT payload FROM mc_hand_runs WHERE task_id=%s AND hand=%s',(task,'coding')).fetchone()
            figs=[]
            for i in range(9):
                files={}
                for fmt in ['png','pdf','svg']:
                    p=folder/f'f{i}.{fmt}'
                    if fmt=='png':Image.new('RGB',(8,8),(20*i,80,130)).save(p,dpi=(300,300))
                    else:p.write_text('SYNTHETIC '+str(i),encoding='utf-8')
                    files[fmt]={'path':p.name,'sha256':sha_file(p)}
                figs.append({'id':f'f{i}','category':['raw','process','result'][i//3],'question_ids':['q1'],'title':'测试图','purpose':'测试证据','formal':True,'number':i+1,'files':files})
            (folder/'figure-catalog.json').write_text(json.dumps({'question_ids':['q1'],'evidence':row['payload']['binding'],'figures':figs}),encoding='utf-8')
        artifacts=[{'path':p.relative_to(root).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size} for p in folder.iterdir()]
        result={'status':'succeeded','run_id':jid,'job_sha256':job['job_sha256'],'code_sha256':job['code_sha256'],'authorization':job['authorization'],'artifacts':artifacts,'cleanup':{'removed':True},'TEST_SYNTHETIC':True}
        return 'SYNTHETIC_TRACE',{'status':'ok','data':result}
    monkeypatch.setattr(hr,'trace_call',trace)
    return root,calls

def start(w,task,request_id='start'):
    return w.start_hand(task,'coding',version=1,actor='TEST_OPERATOR',request_id=request_id,guidance='SYNTHETIC orchestrator test')

def until(w,task,rid,model,phase,limit=30):
    for _ in range(limit):
        state=w.hand_status(task,rid)
        if state['phase']==phase:return state
        w.advance_hand(task,rid,model=model)
    raise AssertionError(w.hand_status(task,rid))

def test_complete_runtime_preserves_both_business_and_writing_gates(task,execution):
    model=Provider()
    with Workflow() as w:
        r=start(w,task);rid=r['run_id']
        assert start(w,task)['run_id']==rid
        until(w,task,rid,model,'ATTACHED')
        assert not w.task(task)['result_approved']
        assert len(execution[1])==3 and execution[1]==['code_execute']*3
        before=len(model.calls)
    with Workflow() as w:
        assert w.advance_hand(task,rid,model=model)['phase']=='ATTACHED' and len(model.calls)==before
        hr.verify_result(w,task,rid)
        w.action(task,actor='TEST_SIMULATED_USER',request_id='approve-result',version=1,kind='result',decision='approve',result_revision=1)
        code=hr.load(w,task,rid)
        cat=code['payload']['figure_catalog']
        r=w.start_hand(task,'writing',version=1,actor='TEST_OPERATOR',request_id='write',guidance='SYNTHETIC中文稿',figure_catalog=cat)
        wid=r['run_id'];until(w,task,wid,model,'WAITING_MANUSCRIPT_AND_FIGURES')
        st=w.hand_status(task,wid);assert not st['reviews']['can_export']
        row=hr.load(w,task,wid);f=hr.run_folder(row)
        kw={'decision':'approve','actor':'user','statement':'TEST_SIMULATED_USER_ONLY','reason':'SYNTHETIC TEST'}
        w.hand_decision(task,wid,kind='manuscript',artifact_sha256=sha_file(ROOT/row['payload']['manuscript']),request_id='md',**kw)
        assert not w.hand_status(task,wid)['reviews']['can_export']
        result=w.hand_decision(task,wid,kind='figures',artifact_sha256=sha_file(f/'figure-catalog.json'),request_id='fig',**kw)
        assert result['phase']=='READY_FOR_E_EXPORT' and result['reviews']['can_export']
        assert [stage for stage,_ in model.calls]==['Coder','P1','Coder','P2','Writer-plan','W1','Writer']
        assert all('feedback' not in data for stage,data in model.calls if stage in ['P1','P2','W1'])

@pytest.mark.parametrize('gate,domain,expected',[('P1','implementation','GENERATE_MINIMAL'),('P1','model','NEEDS_MODEL_REVISION'),('P1','infrastructure','NEEDS_HUMAN'),('P2','implementation','GENERATE_MINIMAL')])
def test_independent_failure_routes(task,execution,gate,domain,expected):
    m=Provider(fail_gate=gate,domain=domain)
    with Workflow() as w:
        rid=start(w,task)['run_id']
        until(w,task,rid,m,'REVIEW_'+gate)
        state=w.advance_hand(task,rid,model=m)
        assert state['phase']==expected and not w.task(task)['result_revision']
        row=hr.load(w,task,rid);assert row['payload']['reviews'][gate+'-0']['status']=='FAIL'
        if expected=='GENERATE_MINIMAL':until(w,task,rid,m,'ATTACHED')

def test_static_retry_budget_and_stale_version(task,execution):
    m=Provider(broken_code=True)
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,m,'NEEDS_HUMAN')
        assert len(m.calls)==4 and not execution[1]
        w.db.execute('UPDATE mc_tasks SET model_approved=false WHERE id=%s',(task,))
        with pytest.raises(WorkflowError,match='stale'):w.hand_status(task,rid)


def test_unknown_model_outcome_never_resends(task,execution):
    class Unknown:
        def __init__(self):self.calls=0
        def call(self,*a,**k):self.calls+=1;raise ModelCallError('unknown')
    m=Unknown()
    with Workflow() as w:
        rid=start(w,task)['run_id']
        with pytest.raises(ModelCallError):w.advance_hand(task,rid,model=m)
    with Workflow() as w:
        with pytest.raises(ModelCallError):w.advance_hand(task,rid,model=m)
        assert m.calls==1 and w.hand_status(task,rid)['phase']=='PROVIDER_UNKNOWN'


def test_execution_ambiguity_recovers_only_by_status(task,execution,monkeypatch):
    old=hr.trace_call;first=True
    def interrupted(*a,**kw):
        nonlocal first
        if first:first=False;raise RuntimeError('SYNTHETIC transport disconnect')
        return old(*a,**kw)
    monkeypatch.setattr(hr,'trace_call',interrupted)
    with Workflow() as w:
        rid=start(w,task)['run_id'];w.advance_hand(task,rid,model=Provider())
        with pytest.raises(RuntimeError):w.advance_hand(task,rid)
    with Workflow() as w:
        result=w.advance_hand(task,rid)
        assert result['phase']=='REVIEW_P1' and execution[1]==['code_execution_status']


def test_changed_outputs_block_result_admission(task,execution):
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'READY_TO_ATTACH')
        p=hr.load(w,task,rid)['payload'];output=hr.read(ROOT/p['full_packet'])['artifacts'][0]
        (ROOT/output['path']).write_bytes(b'TAMPERED')
        with pytest.raises(WorkflowError,match='changed'):w.advance_hand(task,rid)
        assert w.task(task)['result_revision']==0


def test_http_runtime_routes_and_conflict(task,execution):
    from modelcrew.api import create_app
    with TestClient(create_app()) as c:
        prefix='/tasks/'+task
        body={'version':1,'actor':'TEST','request_id':'http','guidance':'TEST_ONLY'}
        r=c.post(prefix+'/hands/coding/runs',json=body)
        assert r.status_code==200,r.text
        rid=r.json()['run_id']
        assert c.get(prefix+'/hand-runs/'+rid).status_code==200
        assert c.post(prefix+'/hands/coding/runs',json={**body,'guidance':'changed'}).status_code==409
        assert c.post(prefix+'/hands/quality/runs',json=body).status_code==422
        assert c.post(prefix+'/hand-runs/'+rid+'/decisions',json={'kind':'manuscript','decision':'approve','actor':'agent','statement':'x','reason':'x','artifact_sha256':'0'*64,'request_id':'bad'}).status_code==422

def test_W1_failure_returns_to_writer_with_new_snapshot(task,execution):
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='result',version=1,kind='result',decision='approve',result_revision=1)
        catalog=hr.load(w,task,rid)['payload']['figure_catalog']
        wid=w.start_hand(task,'writing',version=1,actor='TEST',request_id='writer-rework',guidance='SYNTHETIC',figure_catalog=catalog)['run_id']
        model=Provider(fail_gate='W1',domain='writing')
        until(w,task,wid,model,'REVIEW_W1')
        assert w.advance_hand(task,wid,model=model)['phase']=='PLAN'
        row=hr.load(w,task,wid);assert row['payload']['reviews']['W1-0']['status']=='FAIL'
        until(w,task,wid,model,'WAITING_MANUSCRIPT_AND_FIGURES')
        row=hr.load(w,task,wid)
        assert row['payload']['reviews']['W1-1']['snapshot_sha256']!=row['payload']['reviews']['W1-0']['snapshot_sha256']
        assert not w.hand_status(task,wid)['reviews']['can_export']
        path=ROOT/row['payload']['manuscript']
        w.hand_decision(task,wid,kind='manuscript',decision='reject',actor='user',statement='TEST_SIMULATED_USER_ONLY',reason='SYNTHETIC',artifact_sha256=sha_file(path),request_id='reject')
        assert w.hand_status(task,wid)['phase']=='NEEDS_WRITING_REVISION'
        assert w.start_hand(task,'writing',version=1,actor='TEST',request_id='new-writer-revision',guidance='SYNTHETIC user revision',figure_catalog=catalog)['phase']=='PLAN'


def test_invalid_independent_proof_is_never_rewritten(task,execution):
    class Bad(Provider):
        def call(self,folder,stage,system,data,**kw):
            answer,meta=super().call(folder,stage,system,data,**kw)
            if stage=='P1':answer['checks'][0]['evidence'][0]['selector']='/NONEXISTENT'
            return answer,meta
    with Workflow() as w:
        rid=start(w,task)['run_id'];m=Bad();until(w,task,rid,m,'NEEDS_HUMAN')
        assert len(m.calls)==2 and not w.task(task)['result_revision']
        row=hr.load(w,task,rid)
        assert not row['payload']['reviews'] and row['payload']['failure_domain']=='review_output'


def test_cached_provider_response_recovers_after_commit_gap(task,execution):
    class Crash:
        calls=0
        def call(self,folder,stage,system,data,**kw):
            self.calls+=1
            ident='synthetic-cached-id'
            hr.write(folder/(stage+'-'+ident+'-response.json'),{'choices':[{'message':{'content':json.dumps({'code':'print("SYNTHETIC")'})}}]})
            hr.write(folder/(stage+'-'+ident+'-metadata.json'),{'status':'completed','call_id':ident})
            raise ModelCallError('SYNTHETIC crash after cached response')
    m=Crash()
    with Workflow() as w:
        rid=start(w,task)['run_id']
        with pytest.raises(ModelCallError):w.advance_hand(task,rid,model=m)
    with Workflow() as w:
        assert w.advance_hand(task,rid,model=m)['phase']=='EXECUTE_MINIMAL' and m.calls==1


def test_writing_does_not_start_before_explicit_result_confirmation(task,execution):
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'ATTACHED')
        with pytest.raises(WorkflowError,match='Confirmed results'):
            w.start_hand(task,'writing',version=1,actor='TEST',request_id='early',guidance='TEST',figure_catalog=hr.load(w,task,rid)['payload']['figure_catalog'])

def test_model_failure_cannot_be_bypassed_by_new_run(task,execution):
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(fail_gate='P1',domain='model'),'NEEDS_MODEL_REVISION')
        with pytest.raises(WorkflowError,match='Model revision'):
            start(w,task,request_id='attempt-to-reset-model-issue')


def test_missing_full_contract_output_is_reworked_before_P2(task,execution):
    with Workflow() as w:
        rid=start(w,task)['run_id']
        row=hr.load(w,task,rid);contract=hr.read(hr.run_folder(row)/'contract.json')
        # Exercise the trusted execution validation boundary with an explicit additional output requirement.
        contract['outputs'].append({'id':'required','path':'required.json','format':'json','fields':[],'decimal_places':None})
        m=Provider();until(w,task,rid,m,'EXECUTE_FULL')
        row=hr.load(w,task,rid);hr.execute(w,row,contract,True)
        updated=hr.load(w,task,rid)
        assert updated['phase']=='GENERATE_MINIMAL'
        assert updated['payload']['feedback']['missing_contract_outputs']==['required.json']
        assert not w.task(task)['result_revision']

def test_changed_registered_job_never_dispatches(task,execution,monkeypatch):
    old=hr.trace_call
    def interrupted(*args,**kwargs):raise RuntimeError('SYNTHETIC before dispatch')
    monkeypatch.setattr(hr,'trace_call',interrupted)
    with Workflow() as w:
        rid=start(w,task)['run_id'];w.advance_hand(task,rid,model=Provider())
        with pytest.raises(RuntimeError):w.advance_hand(task,rid)
        row=hr.load(w,task,rid);job=next(iter(row['payload']['jobs'].values()))['job']
        jobpath=execution[0]/'jobs'/job['job_id']/'job.json'
        changed=hr.read(jobpath);changed['authorization']['task_id']='ANOTHER-TASK';changed.pop('job_sha256');changed['job_sha256']=hr.digest(changed)
        jobpath.write_text(json.dumps(changed),encoding='utf-8')
        monkeypatch.setattr(hr,'trace_call',old)
        state=w.advance_hand(task,rid)
        assert state['phase']=='NEEDS_HUMAN' and not execution[1]

def test_one_read_only_recheck_preserves_original_failure(task,execution):
    with Workflow() as w:
        rid=start(w,task)['run_id'];m=Provider(fail_gate='P1',domain='model')
        until(w,task,rid,m,'NEEDS_MODEL_REVISION')
        old=copy.deepcopy(hr.load(w,task,rid)['payload']['reviews']['P1-0'])
        assert w.recheck_hand(task,rid,rationale='SYNTHETIC read-only appeal; preserve original') ['phase']=='REVIEW_P1'
        assert w.advance_hand(task,rid,model=m)['phase']=='GENERATE_FULL'
        row=hr.load(w,task,rid)
        assert row['payload']['reviews']['P1-0']==old and row['payload']['reviews']['P1-0-recheck']['status']=='PASS'
        with pytest.raises(WorkflowError,match='One read-only'):w.recheck_hand(task,rid,rationale='cannot loop')


def test_writer_alias_returns_original_bytes_not_a_review_rewrite(task,execution):
    class Alias(Provider):
        def call(self,folder,stage,system,data,**kw):
            a,m=super().call(folder,stage,system,data,**kw)
            if stage=='Writer':a={'manuscript_markdown':a['markdown'],'notes':'SYNTHETIC provider shape'}
            return a,m
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='r-yes',version=1,kind='result',decision='approve',result_revision=1)
        catalog=hr.load(w,task,rid)['payload']['figure_catalog']
        wid=w.start_hand(task,'writing',version=1,actor='TEST',request_id='alias',guidance='TEST',figure_catalog=catalog)['run_id']
        until(w,task,wid,Alias(),'WAITING_MANUSCRIPT_AND_FIGURES')
        row=hr.load(w,task,wid);assert row['payload']['writer_response_field']=='manuscript_markdown'
        raw=hr.read(hr.run_folder(row)/'operations/draft-0/answer.json')['manuscript_markdown']
        assert (ROOT/row['payload']['manuscript']).read_text(encoding='utf-8')==raw

@pytest.mark.parametrize('domain,expected',[('implementation','NEEDS_CODE_REVISION'),('explanation','NEEDS_RESULT_INTERPRETATION')])
def test_W1_coding_issues_preserve_confirmed_execution(task,execution,domain,expected):
    class Routed(Provider):
        def call(self,folder,stage,system,data,**kw):
            value,meta=super().call(folder,stage,system,data,**kw)
            if stage=='W1' and value.get('issues'):
                value['issues'][0]['target']='coding'
            return value,meta
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='confirm-route',version=1,kind='result',decision='approve',result_revision=1)
        before=w.task(task);cat=hr.load(w,task,rid)['payload']['figure_catalog']
        wid=w.start_hand(task,'writing',version=1,actor='TEST',request_id='route-'+domain,guidance='TEST',figure_catalog=cat)['run_id']
        m=Routed(fail_gate='W1',domain=domain);until(w,task,wid,m,'REVIEW_W1')
        assert w.advance_hand(task,wid,model=m)['phase']==expected
        after=w.task(task)
        assert after['execution_id']==before['execution_id'] and after['result_approved']
        assert hr.load(w,task,wid)['payload']['rework_target']=='coding'

def test_writer_mechanical_rework_receives_failed_text_and_findings(task,execution):
    class Fixing(Provider):
        drafts=0
        plan_failures=0
        def call(self,folder,stage,system,data,**kw):
            answer,meta=super().call(folder,stage,system,data,**kw)
            if stage=='Writer-plan' and self.drafts==1 and not self.plan_failures:
                self.plan_failures+=1;answer['claims'][0]['evidence'][0]['selector']='/NONEXISTENT'
            if stage=='Writer':
                self.drafts+=1
                assert '## 关键词' in data['manuscript_requirements']['section_headings']
                assert len(data['manuscript_requirements']['formal_figures'])==9
                assert data['manuscript_requirements']['formal_figures'][0]['embed'].startswith('![图1 ')
                if self.drafts==1:answer['markdown']='THIS IS AN EXPLICITLY INVALID SYNTHETIC DRAFT'
                else:
                    assert data['previous_draft']=='THIS IS AN EXPLICITLY INVALID SYNTHETIC DRAFT'
                    assert data['paper_findings']
                    assert data['feedback']['invalid_output_type']
            return answer,meta
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='feedback-result',version=1,kind='result',decision='approve',result_revision=1)
        cat=hr.load(w,task,rid)['payload']['figure_catalog']
        wid=w.start_hand(task,'writing',version=1,actor='TEST',request_id='feedback',guidance='TEST',figure_catalog=cat)['run_id']
        model=Fixing();until(w,task,wid,model,'WAITING_MANUSCRIPT_AND_FIGURES')
        assert model.drafts==2
        assert (hr.run_folder(hr.load(w,task,wid))/'author-draft-0.md').read_text(encoding='utf-8')=='THIS IS AN EXPLICITLY INVALID SYNTHETIC DRAFT'


def test_recheck_targets_current_P1_after_older_full_packet(task,execution):
    with Workflow() as w:
        rid=start(w,task)['run_id'];model=Provider(fail_gate='P2')
        until(w,task,rid,model,'REVIEW_P2')
        assert w.advance_hand(task,rid,model=model)['phase']=='GENERATE_MINIMAL'
        model.fail_gate='P1';model.domain='model'
        until(w,task,rid,model,'NEEDS_MODEL_REVISION')
        before=copy.deepcopy(hr.load(w,task,rid)['payload']['reviews'])
        assert w.recheck_hand(task,rid,rationale='SYNTHETIC current P1 recheck')['phase']=='REVIEW_P1'
        assert w.advance_hand(task,rid,model=model)['phase']=='GENERATE_FULL'
        after=hr.load(w,task,rid)['payload']['reviews']
        assert all(after[key]==value for key,value in before.items())
        assert after['P1-1-recheck']['status']=='PASS' and 'P2-1-recheck' not in after

def test_passed_review_cannot_reopen_exhausted_author_budget(task,execution):
    class InvalidDraft(Provider):
        def call(self,folder,stage,system,data,**kw):
            answer,meta=super().call(folder,stage,system,data,**kw)
            if stage=='Writer':answer['markdown']='INVALID SYNTHETIC DRAFT'
            return answer,meta
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='budget-result',version=1,kind='result',decision='approve',result_revision=1)
        cat=hr.load(w,task,rid)['payload']['figure_catalog']
        wid=w.start_hand(task,'writing',version=1,actor='TEST',request_id='budget',guidance='TEST',figure_catalog=cat)['run_id']
        until(w,task,wid,InvalidDraft(),'NEEDS_HUMAN')
        before=hr.load(w,task,wid)
        assert before['payload']['retries']==3
        with pytest.raises(WorkflowError,match='Only rejected reviewer output'):
            w.recheck_hand(task,wid,rationale='Cannot turn a passed review into extra author retries')
        assert hr.load(w,task,wid)['phase']=='NEEDS_HUMAN'

def test_cached_raw_writer_response_recovers_without_call_or_text_rewrite(task,execution):
    class CrashWriter(Provider):
        drafts=0
        def call(self,folder,stage,system,data,**kw):
            answer,meta=super().call(folder,stage,system,data,**kw)
            if stage=='Writer':
                assert data['output_protocol']=='raw_markdown_v1'
                assert 'Return ONE JSON object' not in system
                self.drafts+=1
                ident='cached-raw-writer'
                text=answer['markdown']+'\n\n'+r'数学表达 $\theta$ 与 $\,\mathrm du$。'+'\n'
                self.original=text
                hr.write(folder/(stage+'-'+ident+'-response.json'),{'choices':[{'finish_reason':'stop','message':{'content':text}}]})
                hr.write(folder/(stage+'-'+ident+'-metadata.json'),{'status':'completed','call_id':ident,'output_protocol':'raw_markdown_v1'})
                raise ModelCallError('SYNTHETIC crash after persisted raw response')
            return answer,meta
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='raw-result',version=1,kind='result',decision='approve',result_revision=1)
        cat=hr.load(w,task,rid)['payload']['figure_catalog']
        wid=w.start_hand(task,'writing',version=1,actor='TEST',request_id='raw-writer',guidance='TEST',figure_catalog=cat)['run_id']
        model=CrashWriter();until(w,task,wid,model,'DRAFT')
        with pytest.raises(ModelCallError):w.advance_hand(task,wid,model=model)
        assert w.advance_hand(task,wid,model=model)['phase']=='WAITING_MANUSCRIPT_AND_FIGURES'
        row=hr.load(w,task,wid)
        assert (ROOT/row['payload']['manuscript']).read_text(encoding='utf-8')==model.original and model.drafts==1
        assert not w.hand_status(task,wid)['reviews']['can_export']
