"""Real DB orchestration tests with explicitly synthetic provider/executor replies."""
from modelcrew.project_assets import asset_path,local_history
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

@pytest.fixture(autouse=True)
def isolated_host_repair_permission(monkeypatch):
    # Real local host settings never grant authority to synthetic test tasks.
    from modelcrew import coder_repair as cr
    monkeypatch.setattr(cr,'host_policy',lambda:None)


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
        answer={'status':'FAIL' if failed else 'PASS','checks':checks,'issues':issues}
        if kw.get('image_inputs'):
            images=kw['image_inputs']
            answer['visual_pages']=[{'image_id':i['image_id'],'status':'PASS','observations':'SYNTHETIC engineering image fixture only.'} for i in images]
            meta.update(image_count=len(images),image_manifest=[{'image_id':i['image_id'],'sha256':i['sha256'],'size_bytes':Path(i['path']).stat().st_size} for i in images])
        return answer,meta

@pytest.fixture
def task(tmp_path):
    c=json.loads((asset_path(ROOT,'contracts/examples/valid-2024-a-q1.json')).read_text(encoding='utf-8-sig'))
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
                    elif fmt=='pdf':
                        import fitz
                        with fitz.open() as document:
                            page=document.new_page(width=240,height=180)
                            page.insert_text((30,60),'SYNTHETIC fixture '+str(i),fontsize=12)
                            document.save(p,no_new_id=True)
                    else:p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180"><text x="30" y="60">SYNTHETIC '+str(i)+'</text></svg>',encoding='utf-8')
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
        w.hand_decision(task,wid,kind='manuscript',artifact_sha256=sha_file(asset_path(ROOT,row['payload']['manuscript'])),request_id='md',**kw)
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
        p=hr.load(w,task,rid)['payload'];output=hr.read(asset_path(ROOT,p['full_packet']))['artifacts'][0]
        (asset_path(ROOT,output['path'])).write_bytes(b'TAMPERED')
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
        denied=c.post(prefix+'/hand-runs/'+rid+'/decisions',json={'kind':'manuscript','decision':'approve','actor':'agent','statement':'x','reason':'x','artifact_sha256':'0'*64,'request_id':'bad'})
        assert denied.status_code==403 and denied.json()['error']['code']=='untrusted_user_event'

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
        path=asset_path(ROOT,row['payload']['manuscript'])
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
        assert (asset_path(ROOT,row['payload']['manuscript'])).read_text(encoding='utf-8')==raw

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
        assert (asset_path(ROOT,row['payload']['manuscript'])).read_text(encoding='utf-8')==model.original and model.drafts==1
        assert not w.hand_status(task,wid)['reviews']['can_export']

def test_p2_blocks_bad_last_pdf_page_in_unselected_candidate(task,execution,monkeypatch):
    """All candidates are checked before dispatching the independent P2 call."""
    import fitz
    original=hr.trace_call
    def trace(*args,**kwargs):
        key,envelope=original(*args,**kwargs)
        if envelope['status']=='ok' and 'full-' in envelope['data']['run_id']:
            folder=execution[0]/'runs'/envelope['data']['run_id']/'artifacts'
            catalog=json.loads((folder/'figure-catalog.json').read_text(encoding='utf-8'))
            catalog['figures'][-1]['formal']=False
            pdf=folder/'f8.pdf'
            with fitz.open() as document:
                for n in range(3):
                    page=document.new_page(width=240,height=180)
                    page.insert_text((30,60),'SYNTHETIC candidate page '+str(n+1),fontsize=3 if n==2 else 12)
                pdf.write_bytes(document.tobytes(no_new_id=True))
            catalog['figures'][-1]['files']['pdf']['sha256']=sha_file(pdf)
            (folder/'figure-catalog.json').write_text(json.dumps(catalog),encoding='utf-8')
            envelope['data']['artifacts']=[{'path':p.relative_to(execution[0]).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size} for p in folder.iterdir()]
        return key,envelope
    monkeypatch.setattr(hr,'trace_call',trace)
    model=Provider()
    with Workflow() as w:
        rid=start(w,task)['run_id']
        until(w,task,rid,model,'REVIEW_P2')
        state=w.advance_hand(task,rid,model=model)
        assert state['phase']=='GENERATE_MINIMAL'
        assert 'P2' not in [stage for stage,_ in model.calls]
        assert not w.task(task)['result_revision']
        check=hr.run_folder(hr.load(w,task,rid))/'P2-0-figure-check/figure-0009/pdf-check.json'
        report=json.loads(check.read_text(encoding='utf-8'))
        assert report['page_count']==3 and report['status']=='failed'
        assert 'font_below_minimum' in report['pages'][-1]['findings']

def test_interrupted_figure_check_recovers_without_code_retry(task,execution):
    model=Provider()
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,model,'REVIEW_P2')
        row=hr.load(w,task,rid);partial=hr.run_folder(row)/'P2-0-figure-check'
        partial.mkdir();(partial/'interrupted.txt').write_text('SYNTHETIC crash before sealing',encoding='utf-8')
        state=w.advance_hand(task,rid,model=model)
        assert state['phase']=='READY_TO_ATTACH'
        row=hr.load(w,task,rid)
        assert row['payload']['retries']==0
        assert 'figure-check-recovery-' in row['payload']['figure_check']
        assert (partial/'interrupted.txt').is_file()
        assert [stage for stage,_ in model.calls].count('P2')==1


def repair_request(w, task, rid, name='repair-1'):
    row=hr.load(w,task,rid)
    source=hr.run_folder(row)/('operator-source-'+name+'.py')
    source.write_text('print("SYNTHETIC MANUAL REPAIR; NOT A NUMERICAL SOLVER")\n',encoding='utf-8')
    return dict(version=1,actor='TEST_OPERATOR',request_id=name,
                statement='SYNTHETIC USER REQUEST: repair by points',rationale='SYNTHETIC implementation repair',
                code_path=hr.rel(source),code_sha256=sha_file(source),
                previous_code_sha256=sha_file(asset_path(ROOT,row['payload']['minimal_code_path'])))


def exhaust_minimal(w, task):
    class FailEveryP1(Provider):
        def call(self, folder, stage, system, data, **kwargs):
            if stage=='P1':self.fail_gate='P1'
            return super().call(folder,stage,system,data,**kwargs)
    rid=start(w,task)['run_id']
    until(w,task,rid,FailEveryP1(),'NEEDS_HUMAN')
    return rid


def test_operator_repair_preserves_budget_reviews_and_independent_p1(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task)
        before=hr.load(w,task,rid)['payload'];old_reviews=copy.deepcopy(before['reviews'])
        request=repair_request(w,task,rid)
        assert w.repair_hand(task,rid,**request)['phase']=='EXECUTE_MINIMAL'
        current=hr.load(w,task,rid)['payload']
        assert current['attempt']==4 and current['retries']==3 and current['reviews']==old_reviews
        identity=current['current_author'];assert identity.startswith('operator-repair-')
        assert w.repair_hand(task,rid,**request)['phase']=='EXECUTE_MINIMAL'
        assert len(hr.load(w,task,rid)['payload']['operator_repairs'])==1
        with pytest.raises(WorkflowError,match='idempotency'):
            w.repair_hand(task,rid,**{**request,'rationale':'different'})
        reviewer=Provider()
        assert w.advance_hand(task,rid,model=reviewer)['phase']=='REVIEW_P1'
        assert w.advance_hand(task,rid,model=reviewer)['phase']=='GENERATE_FULL'
        after=hr.load(w,task,rid)['payload']
        assert after['retries']==3 and after['reviews']['P1-4']['status']=='PASS'
        assert all(after['reviews'][k]==v for k,v in old_reviews.items())
        op=after['ops']['P1-4'];assert op['call_id']!=identity
        assert not w.task(task)['result_revision'] and not w.task(task)['result_approved']
        assert [stage for stage,_ in reviewer.calls]==['P1']  # No fake Coder/provider generation.


def test_failed_manual_repair_cannot_reopen_automatic_budget(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);request=repair_request(w,task,rid)
        w.repair_hand(task,rid,**request)
        w.advance_hand(task,rid,model=Provider())
        assert w.advance_hand(task,rid,model=Provider(fail_gate='P1'))['phase']=='NEEDS_HUMAN'
        p=hr.load(w,task,rid)['payload'];assert p['retries']==3 and p['attempt']==4
        assert w.advance_hand(task,rid,model=Provider())['phase']=='NEEDS_HUMAN'


@pytest.mark.parametrize('field,value,message',[
    ('version',2,'exhausted'),('previous_code_sha256','0'*64,'previous code hash'),
    ('code_sha256','0'*64,'code hash')])
def test_operator_repair_rejects_wrong_bindings(task,execution,field,value,message):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);request=repair_request(w,task,rid)
        with pytest.raises(WorkflowError,match=message):w.repair_hand(task,rid,**{**request,field:value})
        assert w.hand_status(task,rid)['phase']=='NEEDS_HUMAN'
        assert 'operator_repairs' not in hr.load(w,task,rid)['payload']


def test_operator_repair_rejects_unsafe_phases_and_model_failure(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);request=repair_request(w,task,rid)
        for phase,domain in [('PROVIDER_UNKNOWN','infrastructure'),('NEEDS_MODEL_REVISION','model'),('NEEDS_HUMAN','review_output')]:
            row=hr.load(w,task,rid);row['payload']['failure_domain']=domain;hr.save(w,row,phase)
            with pytest.raises(WorkflowError,match='exhausted'):w.repair_hand(task,rid,**request)


def test_http_operator_repair_route_and_input_validation(task,execution):
    from modelcrew.api import create_app
    with Workflow() as w:
        rid=exhaust_minimal(w,task);request=repair_request(w,task,rid)
    with TestClient(create_app()) as client:
        url=f'/tasks/{task}/hand-runs/{rid}/repair'
        assert client.post(url,json={**request,'unapproved_extra':True}).status_code==422
        assert client.post(url,json=request).json()['phase']=='EXECUTE_MINIMAL'
        assert client.post(url,json=request).status_code==200


def test_full_operator_repair_preserves_p1_requires_new_execution_replica_p2(task,execution):
    class FailEveryFull(Provider):
        def call(self,folder,stage,system,data,**kwargs):
            if stage=='P2':self.fail_gate='P2'
            return super().call(folder,stage,system,data,**kwargs)
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,FailEveryFull(),'NEEDS_HUMAN')
        row=hr.load(w,task,rid);p=row['payload'];old_reviews=copy.deepcopy(p['reviews'])
        accepted=copy.deepcopy(p['accepted_reviews']);old_full=p['full_packet'];old_jobs=set(p['jobs'])
        request=repair_request(w,task,rid,'full-repair-test')
        request.update(stage='full',previous_code_sha256=sha_file(asset_path(ROOT,p['full_code_path'])))
        with pytest.raises(WorkflowError,match='previous code hash'):
            w.repair_hand(task,rid,**{**request,'previous_code_sha256':'0'*64})
        with pytest.raises(WorkflowError,match='minimal coding'):
            w.repair_hand(task,rid,**{**request,'stage':'minimal'})
        assert w.hand_status(task,rid)['phase']=='NEEDS_HUMAN'
        assert w.repair_hand(task,rid,**request)['phase']=='EXECUTE_FULL'
        assert w.repair_hand(task,rid,**request)['phase']=='EXECUTE_FULL'
        after=hr.load(w,task,rid)['payload']
        assert after['retries']==3 and after['attempt']==4
        assert after['accepted_reviews']=={'P1':accepted['P1']} and after['reviews']==old_reviews
        assert set(after['jobs'])==old_jobs and old_full in after['sealed'] and not after.get('full_packet')
        provider=Provider();until(w,task,rid,provider,'ATTACHED')
        after=hr.load(w,task,rid)['payload']
        assert [stage for stage,_ in provider.calls]==['P2']
        assert after['accepted_reviews']['P1']==accepted['P1']
        assert after['accepted_reviews']['P2']=='P2-4'
        assert 'full-4' in after['jobs'] and 'full-4-replica' in after['jobs']
        assert not w.task(task)['result_approved']


def test_full_operator_repair_rejects_missing_p1_and_previous_hash(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);req=repair_request(w,task,rid,'full-invalid');req['stage']='full'
        with pytest.raises(WorkflowError,match='accepted independent P1'):
            w.repair_hand(task,rid,**req)
        assert not hr.load(w,task,rid)['payload'].get('operator_repairs')

@pytest.fixture
def numeric_execution(execution,monkeypatch):
    """Synthetic executor only: exercise missing/empty catalog admission."""
    original=hr.trace_call;mode={'catalog':False}
    def trace(*args,**kwargs):
        trace_id,response=original(*args,**kwargs)
        packet=response['data'];jid=packet['run_id']
        if 'full-' in jid:
            folder=execution[0]/'runs'/jid/'artifacts'
            # Fixture-owned exact files only; no workspace traversal/deletion.
            for path in list(folder.iterdir()):
                if path.name!='result.json':path.unlink()
            if mode['catalog']:
                w,task=args[:2]
                row=w.db.execute("SELECT * FROM mc_hand_runs WHERE task_id=%s AND hand='coding'",(task,)).fetchone()
                value={'figures':[],'question_ids':['q1'],'evidence':row['payload']['binding'],
                       'numeric_only_scope_sha256':row['payload'].get('numeric_only_scope',{}).get('sha256')}
                hr.write(folder/'figure-catalog.json',value)
            packet['artifacts']=[{'path':p.relative_to(execution[0]).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size} for p in folder.iterdir()]
        return trace_id,response
    monkeypatch.setattr(hr,'trace_call',trace)
    return mode


def numeric_scope_record(row):
    from modelcrew.numeric_test_scope import PROTOCOL
    from modelcrew.modeling_paper import POLICY_PATH
    return {'protocol':PROTOCOL,'run_id':str(row['id']),'binding':row['payload']['binding'],
            'actor':'user','user_statement':'TEST_SIMULATED_USER_ONLY: confirm zero figures',
            'decision_context':'SYNTHETIC current numerical test only','reason':'SYNTHETIC trivial arithmetic',
            'base_paper_policy_sha256':sha_file(POLICY_PATH),
            'figures':{'minimum_candidates':0,'minimum_formal':0,'allowed_count':0},
            'scope':'numeric_result_acceptance_only',
            'required_gates':['P1','full_execution','byte_reproduction','P2','user_result_confirmation'],
            'paper_export_allowed':False}


def exhaust_figure_preflight(w,task):
    rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'NEEDS_HUMAN')
    row=hr.load(w,task,rid)
    assert row['payload']['retries']==3 and row['payload']['accepted_reviews']=={'P1':'P1-3'}
    assert not any(k.startswith('P2-') for k in row['payload']['ops'])
    return rid,row


def test_numeric_scope_empty_catalog_requires_real_p2_and_retains_user_gate(task,numeric_execution):
    from modelcrew.numeric_test_scope import adopt
    with Workflow() as w:
        rid,row=exhaust_figure_preflight(w,task)
        original_reviews=copy.deepcopy(row['payload']['reviews'])
        decision=hr.run_folder(row)/'synthetic-zero-figure-decision.json';hr.write(decision,numeric_scope_record(row))
        assert adopt(w,task,rid,hr.rel(decision))['phase']=='NEEDS_HUMAN'
        assert adopt(w,task,rid,hr.rel(decision))['phase']=='NEEDS_HUMAN'
        req=repair_request(w,task,rid,'numeric-full-repair')
        req.update(stage='full',previous_code_sha256=sha_file(asset_path(ROOT,row['payload']['full_code_path'])))
        w.repair_hand(task,rid,**req);numeric_execution['catalog']=True
        provider=Provider();until(w,task,rid,provider,'ATTACHED')
        row=hr.load(w,task,rid);p=row['payload']
        assert p['retries']==3 and p['attempt']==4 and p['accepted_reviews']=={'P1':'P1-3','P2':'P2-4'}
        assert all(p['reviews'][k]==v for k,v in original_reviews.items())
        assert [stage for stage,_ in provider.calls]==['P2']
        data=provider.calls[0][1]
        assert data['numeric_only_scope']['figures']['allowed_count']==0
        assert set(data['required_checks'])==set(REQUIRED_CHECKS['P2'])
        assert data['evidence']['numeric-only-scope']['paper_export_allowed'] is False
        assert not w.task(task)['result_approved']
        result=w.db.execute('SELECT review FROM mc_results WHERE task_id=%s',(task,)).fetchone()
        assert result['review']['acceptance_scope']['figures']==0
        hr.verify_result(w,task,rid)
        w.action(task,actor='TEST_SIMULATED_USER',request_id='approve-test-result',version=1,kind='result',decision='approve',result_revision=1)
        with pytest.raises(WorkflowError,match='excludes paper'):
            w.start_hand(task,'writing',version=1,actor='TEST_OPERATOR',request_id='no-paper',guidance='SYNTHETIC')


@pytest.mark.parametrize('field,value',[('run_id','other-run'),('base_paper_policy_sha256','0'*64),('paper_export_allowed',True),('figures',{'minimum_candidates':0,'minimum_formal':0,'allowed_count':9})])
def test_numeric_scope_rejects_wrong_or_broader_decision(task,numeric_execution,field,value):
    from modelcrew.numeric_test_scope import adopt
    with Workflow() as w:
        rid,row=exhaust_figure_preflight(w,task);record=numeric_scope_record(row);record[field]=value
        decision=hr.run_folder(row)/'synthetic-bad-scope.json';hr.write(decision,record)
        with pytest.raises(WorkflowError,match='does not match'):adopt(w,task,rid,hr.rel(decision))
        assert not (hr.run_folder(row)/'numeric-only-test-scope.json').exists()
        assert 'numeric_only_scope' not in hr.load(w,task,rid)['payload']


def test_numeric_scope_tampering_and_graphical_outputs_blocked(task,numeric_execution):
    from modelcrew.numeric_test_scope import adopt,validate_empty_catalog
    with Workflow() as w:
        rid,row=exhaust_figure_preflight(w,task)
        decision=hr.run_folder(row)/'synthetic-scope.json';hr.write(decision,numeric_scope_record(row));adopt(w,task,rid,hr.rel(decision))
        row=hr.load(w,task,rid);catalog={'figures':[],'numeric_only_scope_sha256':row['payload'].get('numeric_only_scope',{}).get('sha256')}
        with pytest.raises(WorkflowError,match='graphical'):validate_empty_catalog(row,{'artifacts':[{'path':'unexpected.pdf'}]},catalog)
        with pytest.raises(WorkflowError,match='explicitly declare'):validate_empty_catalog(row,{'artifacts':[]},{**catalog,'numeric_only_scope_sha256':'0'*64})
        target=asset_path(ROOT,row['payload']['numeric_only_scope']['path']);target.write_text('{}',encoding='utf-8')
        with pytest.raises(WorkflowError,match='changed'):hr.guard(w,row)


def test_numeric_scope_cannot_reclassify_an_actual_p2_failure(task,numeric_execution):
    from modelcrew.numeric_test_scope import adopt
    with Workflow() as w:
        rid,row=exhaust_figure_preflight(w,task)
        row['payload']['ops']['P2-3']={'status':'unknown'};hr.save(w,row)
        decision=hr.run_folder(row)/'synthetic-scope.json';hr.write(decision,numeric_scope_record(row))
        with pytest.raises(WorkflowError,match='Only exhausted'):adopt(w,task,rid,hr.rel(decision))


def test_default_p2_still_rejects_empty_catalog(task,numeric_execution):
    numeric_execution['catalog']=True
    with Workflow() as w:
        rid=start(w,task)['run_id'];provider=Provider()
        until(w,task,rid,provider,'REVIEW_P2')
        assert w.advance_hand(task,rid,model=provider)['phase']=='GENERATE_MINIMAL'
        p=hr.load(w,task,rid)['payload']
        assert p['feedback']['error']=='Candidate/formal figure policy incomplete'
        assert not any(stage=='P2' for stage,_ in provider.calls)
        assert not w.task(task)['result_revision']


COMPILE_INVALID = "def solver():\n    print(hm)\n    global hm\n"


def test_generated_symbol_table_error_rejected_before_execution(task,execution):
    class InvalidCompile(Provider):
        def call(self,*args,**kwargs):
            answer,meta=super().call(*args,**kwargs)
            answer['code']=COMPILE_INVALID
            return answer,meta
    with Workflow() as w:
        rid=start(w,task)['run_id']
        state=w.advance_hand(task,rid,model=InvalidCompile())
        p=hr.load(w,task,rid)['payload']
        assert state['phase']=='GENERATE_MINIMAL' and p['retries']==1
        assert 'global declaration' in p['feedback']['static_error']
        assert not p.get('jobs') and not execution[1]


def test_operator_symbol_table_error_rejected_without_state_change(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);req=repair_request(w,task,rid)
        path=asset_path(ROOT,req['code_path']);path.write_text(COMPILE_INVALID,encoding='utf-8')
        req['code_sha256']=sha_file(path)
        with pytest.raises(SyntaxError,match='global declaration'):w.repair_hand(task,rid,**req)
        p=hr.load(w,task,rid)['payload']
        assert p['attempt']==3 and p['retries']==3 and not p.get('operator_repairs')


@pytest.mark.parametrize('literal',['NaN','Infinity','-Infinity','1e999'])
def test_nonfinite_output_is_implementation_failure_not_infrastructure(task,execution,monkeypatch,literal):
    original=hr.trace_call
    def nonfinite(*args,**kwargs):
        tid,envelope=original(*args,**kwargs)
        receipt=envelope['data'];item=receipt['artifacts'][0]
        path=execution[0]/item['path']
        path.write_text('{"values":['+literal+']}',encoding='utf-8')
        item.update(sha256=sha_file(path),size_bytes=path.stat().st_size)
        return tid,envelope
    monkeypatch.setattr(hr,'trace_call',nonfinite)
    with Workflow() as w:
        rid=start(w,task)['run_id'];w.advance_hand(task,rid,model=Provider())
        row=hr.load(w,task,rid);row['payload'].update(retries=3,attempt=3);hr.save(w,row)
        state=w.advance_hand(task,rid,model=Provider());p=hr.load(w,task,rid)['payload']
        assert state['phase']=='NEEDS_HUMAN' and p['failure_domain']=='implementation'
        assert p['rework_target']=='coding' and p['retries']==3
        assert 'non-finite' in p['feedback']['error']
        assert not (hr.run_folder(row)/'minimal-3-execution.json').exists()
        assert execution[1]==['code_execute']


def test_local_nonfinite_recovery_preserves_evidence_budget_and_repair_gate(task,execution):
    from modelcrew.hand_repair import recover_nonfinite_output
    with Workflow() as w:
        rid=start(w,task)['run_id'];w.advance_hand(task,rid,model=Provider())
        row=hr.load(w,task,rid);row['payload'].update(retries=3,attempt=3);hr.save(w,row)
        w.advance_hand(task,rid,model=Provider())
        row=hr.load(w,task,rid);p=row['payload'];saved=p['jobs']['minimal-3']
        job=saved['job'];root=execution[0];jid=job['job_id']
        out=root/'runs'/jid/'artifacts'/'result.json'
        out.write_text('{"values": [NaN]}',encoding='utf-8')
        receipt=dict(status='succeeded',cleanup={'removed':True},run_id=jid,
                     **{k:job[k] for k in ('job_sha256','code_sha256','authorization')},
                     artifacts=[dict(path=out.relative_to(root).as_posix(),sha256=sha_file(out),size_bytes=out.stat().st_size)])
        # Recreate the pre-fix state and sealed bytes, not an actual P1 approval.
        p['sealed'][hr.rel(out)]=sha_file(out)
        p.update(failure_domain='infrastructure',rework_target='recovery',error_type='ValueError')
        hr.save(w,row,'NEEDS_HUMAN');hr.write(root/'runs'/jid/'result.json',receipt)
        request=dict(version=1,actor='TEST_OPERATOR',request_id='recover',statement='SYNTHETIC repair request')
        before=sha_file(out);calls=list(execution[1])
        state=recover_nonfinite_output(w,task,rid,**request)
        p=hr.load(w,task,rid)['payload']
        assert state['phase']=='NEEDS_HUMAN' and p['failure_domain']=='implementation'
        assert p['retries']==3 and p['attempt']==3 and sha_file(out)==before
        assert execution[1]==calls and not w.task(task)['result_revision']
        assert recover_nonfinite_output(w,task,rid,**request)==state
        with pytest.raises(WorkflowError,match='idempotency'):
            recover_nonfinite_output(w,task,rid,**{**request,'statement':'changed'})
        assert w.repair_hand(task,rid,**repair_request(w,task,rid))['phase']=='EXECUTE_MINIMAL'


class MissingReviewIssues(Provider):
    def call(self,folder,stage,system,data,**kw):
        answer,meta=super().call(folder,stage,system,data,**kw)
        if stage=='P1':
            answer['checks'][0]['status']='FAIL'
            answer['status']='FAIL';answer['issues']=[]
        return answer,meta


def rejected_p1_with_spent_recheck(w,task):
    from modelcrew.business_adapter import BusinessAdapter
    rid=start(w,task)['run_id'];until(w,task,rid,MissingReviewIssues(),'NEEDS_HUMAN')
    cmd=dict(contract_version='1.0.0',operation='hand_recheck',request_id='first-recheck',
             arguments=dict(task_id=task,run_id=rid,body=dict(rationale='SYNTHETIC incomplete issue coverage')))
    bound=hr.load(w,task,rid)['payload']['binding']
    cmd['expected_binding']=dict(task_id=task,run_id=rid,version=1,contract_sha256=bound['contract_sha256'])
    a=BusinessAdapter()
    result=a.invoke('hand_recheck',cmd)
    assert result['phase']=='REVIEW_P1',result
    w.advance_hand(task,rid,model=MissingReviewIssues())
    assert hr.load(w,task,rid)['payload']['recheck_used']
    return rid,cmd


def legacy_used_recheck_claim(w,task,cmd):
    from modelcrew.business_adapter import scope_for,resource_for
    from modelcrew.business_store import BusinessStore
    from modelcrew.business_contract import request_digest
    req=copy.deepcopy(cmd);req['request_id']='second-recheck'
    scope=scope_for('hand_recheck',req['arguments'],w);store=BusinessStore(w.db)
    row=store.claim(scope,'hand_recheck',req['request_id'],request_digest(req),req,resource_for(scope),None)
    row=store.save(row,'dispatched');return store.save(row,'outcome_unknown')


def test_spent_recheck_preflight_never_claims_or_fences_task(task,execution):
    from modelcrew.business_adapter import BusinessAdapter
    with Workflow() as w:
        rid,cmd=rejected_p1_with_spent_recheck(w,task);before=copy.deepcopy(hr.load(w,task,rid)['payload'])
        for name in ['second-recheck','third-recheck']:
            result=BusinessAdapter().invoke('hand_recheck',{**cmd,'request_id':name})
            assert result['status']=='error' and result['error']['code']=='workflow_conflict'
            assert not w.db.execute('SELECT 1 FROM mc_business_operations WHERE request_id=%s AND resource_key=%s',(name,'task:'+task)).fetchone()
        assert hr.load(w,task,rid)['payload']==before


def test_trusted_used_recheck_recovery_preserves_core_and_old_request(task,execution):
    from modelcrew.business_recovery import recover_used_hand_recheck
    from modelcrew.business_store import BusinessStore
    with Workflow() as w:
        rid,cmd=rejected_p1_with_spent_recheck(w,task);legacy=legacy_used_recheck_claim(w,task,cmd)
        before=copy.deepcopy(hr.load(w,task,rid)['payload'])
        assert not recover_used_hand_recheck(w,task,'second-recheck')['applied']
        assert BusinessStore(w.db).unresolved('task:'+task)
        result=recover_used_hand_recheck(w,task,'second-recheck',apply=True)
        assert result['receipt']['state']=='failed' and not BusinessStore(w.db).unresolved('task:'+task)
        assert recover_used_hand_recheck(w,task,'second-recheck',apply=True)['replayed']
        assert hr.load(w,task,rid)['payload']==before
        saved=BusinessStore(w.db).get(legacy['scope'],'hand_recheck','second-recheck')
        assert saved['request']==legacy['request'] and saved['request_sha256']==legacy['request_sha256']
        assert w.db.execute("SELECT count(*) AS n FROM mc_business_operation_events WHERE scope_sha256=%s AND operation='hand_recheck' AND request_id='second-recheck'",(legacy['scope_sha256'],)).fetchone()['n']==4


@pytest.mark.parametrize('boundary',['changed-core','no-prior-success','no-spent-flag'])
def test_used_recheck_recovery_refuses_insufficient_proof(task,execution,boundary):
    from modelcrew.business_recovery import recover_used_hand_recheck
    with Workflow() as w:
        rid,cmd=rejected_p1_with_spent_recheck(w,task)
        if boundary=='no-spent-flag':
            row=hr.load(w,task,rid);row['payload']['recheck_used']=False;hr.save(w,row)
        if boundary=='no-prior-success':
            w.db.execute("UPDATE mc_business_operations SET state='failed' WHERE resource_key=%s AND request_id='first-recheck'",('task:'+task,));w.db.commit()
        legacy_used_recheck_claim(w,task,cmd)
        if boundary=='changed-core':
            row=hr.load(w,task,rid);row['payload']['local_test_note']='changed';hr.save(w,row)
        with pytest.raises(ValueError):recover_used_hand_recheck(w,task,'second-recheck',apply=True)


def test_invalid_p1_author_rework_spends_existing_budget_without_reviewer_or_approval(task,execution):
    from modelcrew.hand_repair import retry_after_invalid_p1
    with Workflow() as w:
        rid,cmd=rejected_p1_with_spent_recheck(w,task)
        before=copy.deepcopy(hr.load(w,task,rid)['payload']);key=before['last_review']['stage_key']
        path=hr.run_folder(hr.load(w,task,rid))/'operations'/key/'answer.json';sha=sha_file(path)
        calls=list(execution[1]);req=dict(version=1,actor='TEST_OPERATOR',request_id='repair-invalid-p1',
             statement='SYNTHETIC explicit author repair request',rationale='SYNTHETIC invalid reviewer issue coverage')
        assert retry_after_invalid_p1(w,task,rid,**req)['phase']=='GENERATE_MINIMAL'
        after=hr.load(w,task,rid)['payload']
        assert after['attempt']==before['attempt']+1 and after['retries']==before['retries']+1
        assert after['recheck_used'] and after['reviews']==before['reviews']
        assert after['ops']==before['ops'] and execution[1]==calls and sha_file(path)==sha
        record=after['invalid_p1_repairs'][req['request_id']]
        assert record['missing_issue_check_ids']==['execution'] and record['review_status']=='NOT_ADMITTED'
        assert not w.task(task)['result_revision'] and not after.get('accepted_reviews')
        retry_after_invalid_p1(w,task,rid,**req)
        assert hr.load(w,task,rid)['payload']['retries']==after['retries']
        with pytest.raises(WorkflowError,match='idempotency'):
            retry_after_invalid_p1(w,task,rid,**{**req,'rationale':'different'})
        # Newly generated code still needs actual execution and a new independent P1.
        provider=Provider();w.advance_hand(task,rid,model=provider);w.advance_hand(task,rid,model=provider)
        assert w.hand_status(task,rid)['phase']=='REVIEW_P1'
        assert w.advance_hand(task,rid,model=provider)['phase']=='GENERATE_FULL'
        review_data=next(data for stage,data in provider.calls if stage=='P1')
        assert 'review_coverage_rule' in review_data
        assert review_data['schema']['$defs']['Evidence']['oneOf']


def test_invalid_p1_author_rework_cannot_clear_fence_or_reset_budget(task,execution):
    from modelcrew.hand_repair import retry_after_invalid_p1
    from modelcrew.business_recovery import recover_used_hand_recheck
    with Workflow() as w:
        rid,cmd=rejected_p1_with_spent_recheck(w,task);legacy_used_recheck_claim(w,task,cmd)
        req=dict(version=1,actor='TEST_OPERATOR',request_id='repair-invalid-p1',statement='SYNTHETIC',rationale='SYNTHETIC')
        with pytest.raises(WorkflowError,match='fence'):retry_after_invalid_p1(w,task,rid,**req)
        recover_used_hand_recheck(w,task,'second-recheck',apply=True)
        row=hr.load(w,task,rid);row['payload']['retries']=3;hr.save(w,row)
        with pytest.raises(WorkflowError,match='remaining author budget'):retry_after_invalid_p1(w,task,rid,**req)


@pytest.mark.parametrize('exhausted',[False,True])
def test_new_coding_run_cannot_reset_stopped_run_budget_or_create_fence(task,execution,exhausted):
    from modelcrew.business_adapter import BusinessAdapter
    with Workflow() as w:
        rid=start(w,task)['run_id'];row=hr.load(w,task,rid)
        row['payload'].update(retries=3 if exhausted else 1,attempt=3 if exhausted else 1)
        hr.save(w,row,'NEEDS_HUMAN');before=copy.deepcopy(row['payload'])
        with pytest.raises(WorkflowError,match='cannot reset'):start(w,task,request_id='reset-budget')
        bound=dict(task_id=task,version=1,contract_sha256=before['binding']['contract_sha256'])
        cmd=dict(contract_version='1.0.0',operation='hand_start',request_id='reset-budget',expected_binding=bound,
                 arguments=dict(task_id=task,hand='coding',body=dict(version=1,actor='TEST',request_id='reset-budget',guidance='SYNTHETIC')))
        result=BusinessAdapter().invoke('hand_start',cmd)
        assert result['error']['code']=='workflow_conflict',result
        assert not w.db.execute('SELECT 1 FROM mc_business_operations WHERE resource_key=%s AND request_id=%s',('task:'+task,'reset-budget')).fetchone()
        assert hr.load(w,task,rid)['payload']==before
        assert start(w,task)['run_id']==rid  # Same-key recovery remains idempotent.



def delegated_permission(w,task,rid,max_repairs=3):
    return w.authorize_coder_repair(task,rid,version=1,actor='TEST_TRUSTED_HOST',request_id='user-repair-permission',
             statement='SYNTHETIC USER: authorize Coder repair',max_repairs=max_repairs)


def test_delegated_coder_repairs_use_existing_advance_and_keep_independent_gates(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);before=copy.deepcopy(hr.load(w,task,rid)['payload'])
        approved=delegated_permission(w,task,rid,max_repairs=1)
        assert approved['phase']=='NEEDS_HUMAN' and approved['coder_repair']['remaining']==1
        assert delegated_permission(w,task,rid,max_repairs=1)==approved
        assert w.advance_hand(task,rid)['phase']=='GENERATE_MINIMAL'
        provider=Provider();w.advance_hand(task,rid,model=provider)
        p=hr.load(w,task,rid)['payload']
        assert p['retries']==3 and p['attempt']==4 and p['reviews']==before['reviews']
        assert p['ops']['code-minimal-4']['generation_origin']=='delegated_coder_repair'
        assert provider.calls[0][1]['authorized_coder_repair']['origin']=='delegated_coder_repair'
        assert not p.get('operator_repairs') and not w.task(task)['result_revision']
        w.advance_hand(task,rid,model=provider)
        assert w.hand_status(task,rid)['phase']=='REVIEW_P1'
        assert w.advance_hand(task,rid,model=provider)['phase']=='GENERATE_FULL'
        p=hr.load(w,task,rid)['payload']
        assert p['accepted_reviews']['P1']=='P1-4'
        assert p['ops']['P1-4']['call_id']!=p['ops']['code-minimal-4']['call_id']
        assert w.hand_status(task,rid)['coder_repair']['remaining']==0


def test_delegated_repair_budget_cannot_be_reset_or_consumed_twice(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid,max_repairs=2)
        w.advance_hand(task,rid);provider=Provider(broken_code=True)
        # Static failures consume the already claimed repair slot; each next slot has a new operation.
        assert w.advance_hand(task,rid,model=provider)['phase']=='GENERATE_MINIMAL'
        assert w.advance_hand(task,rid,model=provider)['phase']=='NEEDS_HUMAN'
        row=hr.load(w,task,rid);p=row['payload']
        assert p['retries']==3 and p['attempt']==5 and len(p['coder_repair_uses'])==2
        assert len(provider.calls)==2
        assert w.advance_hand(task,rid,model=provider)['phase']=='NEEDS_HUMAN'
        assert len(provider.calls)==2
        with pytest.raises(WorkflowError,match='idempotency'):
            delegated_permission(w,task,rid,max_repairs=3)
        with pytest.raises(WorkflowError,match='extending'):
            w.authorize_coder_repair(task,rid,version=1,actor='TEST',request_id='extend-budget',statement='SYNTHETIC',max_repairs=3)
        assert not p.get('accepted_reviews') and not w.task(task)['result_approved']


def test_delegated_full_generation_failure_preserves_accepted_minimal_p1(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid,max_repairs=2)
        w.advance_hand(task,rid);until(w,task,rid,Provider(),'GENERATE_FULL')
        before=hr.load(w,task,rid)['payload'];p1=before['accepted_reviews']['P1']
        assert w.advance_hand(task,rid,model=Provider(broken_code=True))['phase']=='GENERATE_FULL'
        after=hr.load(w,task,rid)['payload']
        assert after['attempt']==5 and after['retries']==3 and after['accepted_reviews']=={'P1':p1}
        assert after['coder_repair_uses'][-1]['stage']=='full'
        assert not after.get('full_packet') and not after.get('operator_repairs')


def test_delegated_permission_cannot_override_review_model_or_binding_failures(task,execution):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid)
        original=copy.deepcopy(hr.load(w,task,rid)['payload'])
        for domain in ['review_output','infrastructure','model']:
            row=hr.load(w,task,rid);row['payload']['failure_domain']=domain;hr.save(w,row,'NEEDS_HUMAN')
            assert w.advance_hand(task,rid,model=Provider())['phase']=='NEEDS_HUMAN'
            assert not hr.load(w,task,rid)['payload']['coder_repair_uses']
        row=hr.load(w,task,rid);row['payload']=original;hr.save(w,row)
        with pytest.raises(WorkflowError,match='Current model|approval|frozen|changed|Hand|Current'):
            # Preserve bytes; a stale binding must refuse before consuming a slot.
            row['payload']['binding']['contract_sha256']='0'*64;hr.save(w,row)
            w.advance_hand(task,rid)


def test_coder_authorization_is_local_only_and_tampering_is_rejected(task,execution):
    from modelcrew.business_adapter import IMPLEMENTED
    assert 'authorize_coder_repair' not in IMPLEMENTED and 'hand_repair' not in IMPLEMENTED
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid)
        row=hr.load(w,task,rid);entry=row['payload']['coder_repair_authorizations']['user-repair-permission']
        path=asset_path(ROOT,entry['path']);original=path.read_bytes();path.write_bytes(original+b' ')
        try:
            with pytest.raises(WorkflowError,match='changed'):w.advance_hand(task,rid)
        finally:path.write_bytes(original)
        assert not hr.load(w,task,rid)['payload']['coder_repair_uses']



def test_delegated_full_repair_executes_reproduces_and_requires_new_p2(task,execution,monkeypatch):
    from modelcrew import coder_repair as cr
    # Synthetic engineering quota: exercise registration/receipt checks above the old 32-file ceiling.
    monkeypatch.setattr(cr,'full_file_capacity',lambda limits,figures,outputs:44)
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid,max_repairs=2)
        w.advance_hand(task,rid);until(w,task,rid,Provider(),'GENERATE_FULL')
        p1=hr.load(w,task,rid)['payload']['accepted_reviews']['P1']
        assert w.advance_hand(task,rid,model=Provider(broken_code=True))['phase']=='GENERATE_FULL'
        provider=Provider();until(w,task,rid,provider,'ATTACHED')
        p=hr.load(w,task,rid)['payload']
        assert p['accepted_reviews']=={'P1':p1,'P2':'P2-5'}
        assert p['jobs']['full-5']['job']['limits']['max_files']==44
        assert p['jobs']['full-5-replica']['job']['limits']['max_files']==44
        assert p['jobs']['minimal-4']['job']['limits']['max_files']==32
        assert p['request']['limits']['max_files']==32 and p['retries']==3
        assert [stage for stage,_ in provider.calls]==['Coder','P2']
        assert not w.task(task)['result_approved'] and not p.get('operator_repairs')


def test_host_standing_permission_continues_without_per_round_renewal(task,execution,monkeypatch):
    from modelcrew import coder_repair as cr
    policy={'mode':'standing','statement':'SYNTHETIC host standing permission','scope':'coding_implementation_only'}
    with Workflow() as w:
        rid=exhaust_minimal(w,task)
        monkeypatch.setattr(cr,'host_policy',lambda:policy)
        assert w.advance_hand(task,rid)['phase']=='GENERATE_MINIMAL'
        provider=Provider(broken_code=True)
        for _ in range(7):assert w.advance_hand(task,rid,model=provider)['phase']=='GENERATE_MINIMAL'
        p=hr.load(w,task,rid)['payload'];state=w.hand_status(task,rid)
        assert p['retries']==3 and p['attempt']==11 and len(provider.calls)==7
        assert len(p['coder_repair_uses'])==8 and len(p['coder_repair_authorizations'])==1
        assert state['coder_repair']['remaining'] is None and state['coder_repair']['mode']=='standing'
        assert not w.task(task)['result_approved'] and not p.get('operator_repairs')
        # Revocation takes effect at the next implementation failure, with no slot reset.
        monkeypatch.setattr(cr,'host_policy',lambda:None)
        assert w.advance_hand(task,rid,model=provider)['phase']=='NEEDS_HUMAN'
        assert len(hr.load(w,task,rid)['payload']['coder_repair_uses'])==8


def test_host_standing_permission_preserves_exhausted_grant_and_all_gates(task,execution,monkeypatch):
    from modelcrew import coder_repair as cr
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid,max_repairs=1)
        w.advance_hand(task,rid);w.advance_hand(task,rid,model=Provider(broken_code=True))
        before=copy.deepcopy(hr.load(w,task,rid)['payload'])
        monkeypatch.setattr(cr,'host_policy',lambda:{'mode':'standing','statement':'SYNTHETIC continuing user permission','scope':'coding_implementation_only'})
        assert w.advance_hand(task,rid)['phase']=='GENERATE_MINIMAL'
        p=hr.load(w,task,rid)['payload']
        assert p['coder_repair_authorizations']['user-repair-permission']==before['coder_repair_authorizations']['user-repair-permission']
        assert p['coder_repair_uses'][:1]==before['coder_repair_uses']
        until(w,task,rid,Provider(),'GENERATE_FULL')
        p=hr.load(w,task,rid)['payload'];assert p['accepted_reviews']['P1']=='P1-5'
        assert not w.task(task)['result_revision'] and not w.task(task)['result_approved']


def test_host_standing_permission_does_not_bypass_nonimplementation_failures(task,execution,monkeypatch):
    from modelcrew import coder_repair as cr
    with Workflow() as w:
        rid=exhaust_minimal(w,task)
        monkeypatch.setattr(cr,'host_policy',lambda:{'mode':'standing','statement':'SYNTHETIC permission','scope':'coding_implementation_only'})
        for domain in ('review_output','infrastructure','model'):
            row=hr.load(w,task,rid);row['payload']['failure_domain']=domain;hr.save(w,row,'NEEDS_HUMAN')
            assert w.advance_hand(task,rid)['phase']=='NEEDS_HUMAN'
            assert not hr.load(w,task,rid)['payload'].get('coder_repair_authorizations')


def test_host_standing_permission_works_through_dispatched_business_advance(task,execution,monkeypatch):
    from modelcrew import coder_repair as cr
    from modelcrew.business_adapter import BusinessAdapter
    from modelcrew.business_projection import binding
    with Workflow() as w:
        rid=exhaust_minimal(w,task)
        args={'task_id':task,'run_id':rid};expected=binding(w,args)
    monkeypatch.setattr(cr,'host_policy',lambda:{'mode':'standing','statement':'SYNTHETIC explicit host permission','scope':'coding_implementation_only'})
    result=BusinessAdapter().invoke('hand_advance',{'contract_version':'1.0.0','operation':'hand_advance',
        'arguments':args,'request_id':'synthetic-standing-start','expected_binding':expected})
    assert result['status'] not in ('error','outcome_unknown')
    assert result['phase']=='GENERATE_MINIMAL'
    assert result['data']['coder_repair']['mode']=='standing'
    assert result['data']['coder_repair']['remaining'] is None
    with Workflow() as w:assert hr.load(w,task,rid)['payload']['retries']==3


def submit_fixture_revision(w,task,rid,path,key='synthetic-code-revision'):
    from modelcrew.business_adapter import BusinessAdapter
    from modelcrew.business_projection import binding
    row=hr.load(w,task,rid);p=row['payload'];stage='full' if row['phase']=='GENERATE_FULL' else 'minimal'
    args={'task_id':task,'run_id':rid,'code_revision':{'stage':stage,'code_path':str(path),
        'code_sha256':sha_file(path),'previous_code_sha256':sha_file(asset_path(ROOT,p.get(stage+'_code_path') or p['minimal_code_path'])),
        'rationale':'SYNTHETIC targeted Coder patch; not user approval'}}
    request={'contract_version':'1.0.0','operation':'hand_advance','arguments':args,'request_id':key,'expected_binding':binding(w,args)}
    return BusinessAdapter(),request


def test_dsh_code_revision_submits_snapshot_replays_and_reaches_independent_p1(task,execution,tmp_path):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid,max_repairs=1);w.advance_hand(task,rid)
        source=tmp_path/'patched.py';source.write_text('print("SYNTHETIC REVISED SOLVER")',encoding='utf-8')
        adapter,request=submit_fixture_revision(w,task,rid,source)
        before=copy.deepcopy(hr.load(w,task,rid)['payload'])
        response=adapter.invoke('hand_advance',request)
        assert response['phase']=='EXECUTE_MINIMAL' and response['status']=='running'
        replay=adapter.invoke('hand_advance',request);assert replay['replayed']
        p=hr.load(w,task,rid)['payload'];record=p['coder_code_revisions']['synthetic-code-revision']
        assert record['origin']=='dsh_submitted_coder_revision'
        assert p['attempt']==before['attempt'] and p['retries']==3 and p['coder_repair_uses']==before['coder_repair_uses']
        assert not p.get('operator_repairs') and p['minimal_code']==source.read_text(encoding='utf-8')
        assert sha_file(asset_path(ROOT,p['minimal_code_path']))==request['arguments']['code_revision']['code_sha256']
        # Mutable DSH workspace is not a frozen input: later edits cannot alter the submitted snapshot.
        source.write_text('print("LATER WORKING COPY")',encoding='utf-8')
        assert w.advance_hand(task,rid)['phase']=='REVIEW_P1'
        provider=Provider();assert w.advance_hand(task,rid,model=provider)['phase']=='GENERATE_FULL'
        after=hr.load(w,task,rid)['payload']
        assert after['accepted_reviews']['P1']=='P1-4'
        assert after['ops']['P1-4']['call_id']!=record['call_id']
        assert not w.task(task)['result_revision'] and not w.task(task)['result_approved']


def test_dsh_code_revision_rejects_bad_source_before_claim_without_fence(task,execution,tmp_path):
    from modelcrew.business_store import BusinessStore
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid,max_repairs=1);w.advance_hand(task,rid)
        source=tmp_path/'patched.py';source.write_text('print("SYNTHETIC")',encoding='utf-8')
        adapter,request=submit_fixture_revision(w,task,rid,source)
        for field in ('code_sha256','previous_code_sha256'):
            bad=copy.deepcopy(request);bad['request_id']='bad-'+field;bad['arguments']['code_revision'][field]='0'*64
            assert adapter.invoke('hand_advance',bad)['status']=='error'
            assert BusinessStore(w.db).unresolved('task:'+task) is None
        source.write_text('bad Python !!!',encoding='utf-8')
        request['arguments']['code_revision']['code_sha256']=sha_file(source)
        assert adapter.invoke('hand_advance',request)['status']=='error'
        assert BusinessStore(w.db).unresolved('task:'+task) is None
        assert hr.load(w,task,rid)['phase']=='GENERATE_MINIMAL'
        assert not hr.load(w,task,rid)['payload'].get('coder_code_revisions')


def test_dsh_code_revision_requires_grant_and_does_not_replace_claimed_generation(task,execution,tmp_path):
    with Workflow() as w:
        rid=start(w,task)['run_id'];provider=Provider();w.advance_hand(task,rid,model=provider)
        source=tmp_path/'patched.py';source.write_text('print("SYNTHETIC")',encoding='utf-8')
        adapter,request=submit_fixture_revision(w,task,rid,source)
        assert adapter.invoke('hand_advance',request)['status']=='error'
        assert len(provider.calls)==1 and hr.load(w,task,rid)['phase']=='EXECUTE_MINIMAL'


def test_dsh_full_code_revision_preserves_p1_and_requires_reproduction_and_p2(task,execution,tmp_path):
    with Workflow() as w:
        rid=exhaust_minimal(w,task);delegated_permission(w,task,rid,max_repairs=2);w.advance_hand(task,rid)
        until(w,task,rid,Provider(),'GENERATE_FULL')
        w.advance_hand(task,rid,model=Provider(broken_code=True))
        before=copy.deepcopy(hr.load(w,task,rid)['payload']);p1=before['accepted_reviews']['P1']
        source=tmp_path/'full-patched.py';source.write_text('print("SYNTHETIC FULL REVISION")',encoding='utf-8')
        adapter,request=submit_fixture_revision(w,task,rid,source)
        assert adapter.invoke('hand_advance',request)['phase']=='EXECUTE_FULL'
        assert hr.load(w,task,rid)['payload']['accepted_reviews']=={'P1':p1}
        until(w,task,rid,Provider(),'ATTACHED')
        after=hr.load(w,task,rid)['payload']
        assert after['accepted_reviews']=={'P1':p1,'P2':'P2-5'}
        assert 'full-5' in after['jobs'] and 'full-5-replica' in after['jobs']
        assert not w.task(task)['result_approved']


@pytest.mark.parametrize('field',['category','number'])
def test_p2_missing_catalog_fields_are_coder_rework_before_reviewer_dispatch(task,execution,monkeypatch,field):
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,Provider(),'REVIEW_P2')
        original=hr.catalog_at
        def malformed(path):
            value=copy.deepcopy(original(path));value['figures'][0].pop(field,None);return value
        monkeypatch.setattr(hr,'catalog_at',malformed)
        provider=Provider();state=w.advance_hand(task,rid,model=provider)
        row=hr.load(w,task,rid);p=row['payload']
        assert state['phase']=='GENERATE_MINIMAL'
        assert p['failure_domain']=='implementation' and p['rework_target']=='coding'
        assert p['coding_failure_stage']=='full'
        assert p['feedback']['catalog_defects'][0]['field']==field
        assert not provider.calls and not any(k.startswith('P2-') for k in p['ops'])
        assert not w.task(task)['result_approved']


@pytest.mark.parametrize('mode',['approve','changed_manuscript','changed_catalog','record_failure'])
def test_combined_native_chat_records_both_or_neither(task,execution,monkeypatch,mode):
    """Synthetic provider/user in an explicitly disposable database, no real approval."""
    import os
    from modelcrew.dsh_chat import prepare_review,confirm_review
    from modelcrew.dsh_decisions import adapter_sha256
    from modelcrew.trusted_decisions import TrustedDecisions
    from modelcrew.business_contract import BusinessContractError
    from modelcrew import writing_reviews
    from modelcrew.contracts import digest
    monkeypatch.setattr('modelcrew.trusted_decisions.local_principal',lambda:{'kind':'test_simulated_dsh','subject_sha256':'c'*64})
    model=Provider()
    with Workflow() as w:
        rid=start(w,task)['run_id'];until(w,task,rid,model,'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='approve-result',version=1,kind='result',decision='approve',result_revision=1)
        cat=hr.load(w,task,rid)['payload']['figure_catalog']
        wid=w.start_hand(task,'writing',version=1,actor='TEST_OPERATOR',request_id='combined-writer',guidance='SYNTHETIC',figure_catalog=cat)['run_id']
        until(w,task,wid,model,'WAITING_MANUSCRIPT_AND_FIGURES')
        scope={'project_id':w.task(task)['project_id'],'task_id':task,'run_id':wid}
        row=hr.load(w,task,wid);md=asset_path(ROOT,row['payload']['manuscript']);catalog=hr.run_folder(row)/'figure-catalog.json'
    service=TrustedDecisions()
    host={'instance_id':'TEST_ENGINEERING_INSTANCE','session_id':'TEST_COMBINED_'+uuid.uuid4().hex,'pid':os.getppid(),'adapter_sha256':adapter_sha256(),'engineering_only':True}
    before={'id':'TEST_BEFORE','rpc_id':'TEST_RPC_BEFORE','text':'展示合并稿'}
    message={'id':'TEST_CONFIRM','rpc_id':'TEST_RPC_CONFIRM','text':'确认'}
    preview=prepare_review(scope,host,before,service)
    assert preview['confirmation_scope']=='manuscript_and_figures'
    assert preview['markdown'].count('### 候选图 ')==9
    assert preview['markdown'].count('![')==18
    with pytest.raises(BusinessContractError):confirm_review(scope,host,preview['preview_id'],{**before,'text':'确认'},service)
    if mode.startswith('changed_'):
        target=md if mode=='changed_manuscript' else catalog
        target.write_bytes(target.read_bytes()+bytes([10]))
        with pytest.raises((BusinessContractError,WorkflowError,ValueError)):confirm_review(scope,host,preview['preview_id'],message,service)
    else:
        if mode=='record_failure':
            def fail(*a,**kw):raise ValueError('SYNTHETIC second record validation failure')
            monkeypatch.setattr(writing_reviews,'selection_record',fail)
        result=confirm_review(scope,host,preview['preview_id'],message,service)
        if mode=='approve':
            assert result['receipt']['state']=='succeeded',result
            assert result['data']['user_decision']['confirmation_scope']=='manuscript_and_figures'
            repeat=confirm_review(scope,host,preview['preview_id'],message,service)
            assert repeat['status']=='already_received'
        else:assert result['status']=='outcome_unknown',result
    with Workflow() as w:
        p=hr.load(w,task,wid)['payload']
        assert bool(p.get('manuscript_review'))==bool(p.get('figure_review'))==(mode=='approve')
        if mode=='approve':
            assert w.hand_status(task,wid)['reviews']['can_export']
            assert p['manuscript_review']['user_statement']==p['figure_review']['user_statement']=='确认'
            assert len(p['combined_user_decisions'])==1
            event=w.db.execute("SELECT request FROM mc_trusted_user_events WHERE request->'arguments'->>'run_id'=%s",(wid,)).fetchone()['request']
            assert p['decisions'][event['request_id']]==digest({k:v for k,v in event['arguments']['body'].items() if k!='request_id'})
        claims=w.db.execute("SELECT count(*) AS n FROM mc_trusted_user_event_claims c JOIN mc_trusted_user_events e USING(event_id) WHERE e.request->'arguments'->>'run_id'=%s",(wid,)).fetchone()['n']
        assert claims==(1 if mode in ('approve','record_failure') else 0)
