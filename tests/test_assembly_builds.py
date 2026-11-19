"""Synthetic E lifecycle tests; approvals and exporter below are TEST ONLY."""
from contextlib import nullcontext
from copy import deepcopy
import json
import shutil
import uuid
from pathlib import Path

import pytest
from PIL import Image
from modelcrew import assembly_builds as ab
from modelcrew import assembly_compose as ac
from modelcrew import assembly_runtime as ar
from modelcrew.collaboration import sha_file
from modelcrew.workflow import WorkflowError
from modelcrew.modeling_paper import policy


class Answer:
    def __init__(self,value):self.value=value
    def fetchone(self):return deepcopy(self.value)


class Memory:
    def __init__(self):self.rows={};self.events=[];self.db=self
    def lock(self,name):return nullcontext()
    def transaction(self):return nullcontext()
    def execute(self,sql,args):
        if sql.startswith('SELECT'):
            if 'request_id=%s' in sql:
                return Answer(next((r for r in self.rows.values() if (r['project_id'],r['request_id'])==args),None))
            row=self.rows.get(str(args[0]));return Answer(row if row and row['project_id']==args[1] else None)
        if sql.startswith('INSERT INTO mc_assembly_builds('):
            key,run,project,request,identity,phase,payload=args
            self.rows[key]={'id':key,'assembly_run_id':run,'project_id':project,'request_id':request,
                            'request_sha256':identity,'phase':phase,'payload':deepcopy(payload.obj)}
        elif sql.startswith('UPDATE'):
            phase,payload,key=args;self.rows[str(key)].update(phase=phase,payload=deepcopy(payload.obj))
        elif sql.startswith('INSERT INTO mc_assembly_build_events'):
            self.events.append(deepcopy(args[2].obj))
        else:raise AssertionError(sql)
        return Answer(None)


def source(q,base,color_offset):
    base.mkdir(parents=True)
    figures=[]
    for n in range(1,10):
        files={}
        for fmt in ['png','pdf','svg']:
            path=base/'figures'/f'f{n}.{fmt}';path.parent.mkdir(exist_ok=True)
            if fmt=='png':Image.new('RGB',(3,3),(n+color_offset,10,25)).save(path,dpi=(300,300))
            else:path.write_bytes((q+str(n)+fmt).encode())
            files[fmt]={'path':'figures/'+path.name,'sha256':sha_file(path)}
        figures.append({'id':'f'+str(n),'number':n,'category':['raw','process','result'][(n-1)//3],
                        'question_ids':[q],'title':'测试资料','purpose':'合成状态验证','formal':True,
                        'source_kind':'TEST_ONLY','files':files})
    text=''
    for section in policy()['required_sections']:
        text+='## '+section+'\n\n'
        if section=='参考文献':text+='[1] 合成来源仅用于测试。\n\n';continue
        if section=='符号说明':
            text+='| 符号 | 含义 | 单位 |\n|---|---|---|\n| $x$ | 合成位置 | m |\n\n';continue
        text+='根据合成条件说明模型与单位，检验结果和适用范围。\n\n'
        if section=='模型建立':text+='$$\nx=1\\label{eq:a}\n$$\n\n式（1）与 \\eqref{eq:a} 给出说明[1]。符号释义见表2。\n\n'
        if section=='结果分析':
            text+='表1 合成数值\n\n| 数量 | 单位 |\n|---|---|\n| 1 | m |\n\n正文见表1。\n\n'
            for f in figures:
                n=f['number'];text+=f'正文图{n}说明真实输入的位置。\n\n![图{n} 测试资料]({f["files"]["png"]["path"]})\n\n图{n} 测试资料。\n\n'
    (base/ac.MD_NAME).write_text(text,encoding='utf-8')
    (base/'figure-catalog.json').write_text(json.dumps({'question_ids':[q],'figures':figures}),encoding='utf-8')
    return text


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(ab,'ROOT',tmp_path);monkeypatch.setattr(ar,'ROOT',tmp_path)
    monkeypatch.setattr(ab,'writing_context',lambda:{'workflow_sha256':'a'*64})
    monkeypatch.setattr(ab,'claim_evidence',lambda row:{'scope':'SYNTHETIC lifecycle only; real W1 claims audited separately'})
    run_id=str(uuid.uuid4());input_folder=tmp_path/'inputs'/run_id
    chapters=[]
    for q,n in [('q1',0),('q2',20)]:
        base=input_folder/'snapshot'/'original'/q
        source(q,base,n)
        chapters.append({'question_id':q,'manuscript':f'original/{q}/'+ac.MD_NAME,
                         'binding':{'task_id':q,'version':1},'task_id':q,'W1':{'TEST_ONLY':'PASS'},
                         'manuscript_sha256':sha_file(base/ac.MD_NAME),'figure_catalog_sha256':sha_file(base/'figure-catalog.json')})
    row={'id':run_id,'payload':{'chapters':chapters,'manifest_sha256':'a'*64}}
    monkeypatch.setattr(ar,'load',lambda w,project,key:deepcopy(row))
    monkeypatch.setattr(ar,'folder',lambda key:input_folder)
    monkeypatch.setattr(ab,'assert_inputs',lambda *args:{'phase':'ASSEMBLY_INPUTS_FROZEN'})
    req={'request_id':'compose-1','actor':'TEST_ONLY','title':'合成论文状态测试','abstract':'合成资料用于测试统一摘要与结果，不代表真实科研结论。','keywords':'合成资料；状态验证'}
    return Memory(),run_id,req,row


def approve(w,build_id):
    row=w.rows[build_id];source=ab.source_folder(row)
    for kind,name in [('manuscript',ac.MD_NAME),('figures','figure-catalog.json')]:
        ab.decision(w,'p',build_id,request_id='approve-'+kind,actor='user',kind=kind,decision='approve',
                    statement='TEST_SIMULATED_USER_ONLY',reason='SYNTHETIC TEST ONLY',artifact_sha256=sha_file(source/name))


def fake_export(source,out,*args):
    out.mkdir(parents=True)
    names=[ac.MD_NAME,'figure-catalog.json','user-review-confirmed.json']
    for name in names:shutil.copyfile(source/name,out/name)
    shutil.copytree(source/'figures',out/'figures')
    for name in ['paper.pdf','paper.tex','paper.docx']:(out/name).write_bytes(b'SYNTHETIC EXPORT ONLY')
    (out/'build-manifest.json').write_text(json.dumps({'source_hashes':{name:sha_file(source/name) for name in names}}),encoding='utf-8')


def test_composition_and_numbering(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req)
    assert a['phase']=='WAITING_ASSEMBLY_REVIEW'
    assert not a['reviews']['can_export'] and a['W2']=='NOT_RUN'
    report=ab.read(ab.source_folder(w.rows[a['build_id']])/'assembly-map.json')
    assert report['mechanical']['formal_figures']==18
    assert report['maps']['equations']=={'q1':{'1':1},'q2':{'1':2}}
    assert report['maps']['tables']=={'q1':{'2':1,'1':2},'q2':{'2':1,'1':3}}
    assert report['symbol_table']['coverage']=='complete'
    assert len(report['symbol_table']['rows'])==1
    text=(ab.ROOT/a['manuscript']).read_text(encoding='utf-8')
    assert '式（2）' in text and '\\eqref{q2-eq:a}' in text
    assert '@@ASM_' not in text
    symbols=text.split('## 符号说明\n',1)[1].split('## 模型建立',1)[0]
    assert '### ' not in symbols and symbols.count('| 符号 |')==1
    assert '问题1、问题2' in symbols
    assert text.count('符号释义见表1。')==2
    assert ab.compose(w,'p',run,**req)==a
    with pytest.raises(WorkflowError,match='reused'):ab.compose(w,'p',run,**{**req,'title':'其他标题'})


def test_separate_reviews_required_and_export_idempotent(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id']
    with pytest.raises(WorkflowError,match='approvals'):ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=fake_export)
    source=ab.source_folder(w.rows[bid])
    ab.decision(w,'p',bid,request_id='only-text',actor='user',kind='manuscript',decision='approve',statement='TEST_ONLY',reason='TEST_ONLY',artifact_sha256=sha_file(source/ac.MD_NAME))
    assert not ab.status(w,'p',bid)['reviews']['can_export']
    with pytest.raises(WorkflowError):ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=fake_export)
    approve(w,bid)
    count=[]
    def exporter(*args):count.append(1);fake_export(*args)
    result=ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=exporter)
    assert result['phase']=='WAITING_RENDER'
    assert ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=exporter)==result
    assert len(count)==1 and result['W2']=='NOT_RUN'
    exported=ab.ROOT/result['exports']['exp']['output']
    assert ab.read(exported/'assembly-provenance/binding.json')['build_id']==bid
    assert (exported/'assembly-provenance/claim-evidence-map.json').is_file()


def test_local_update_reuses_unmodified_chapter(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);approve(w,a['build_id'])
    patch={'question_id':'q2','before':'正文见表1。','after':'合成说明参见表1。','expected_count':1,'reason':'TEST_ONLY wording change'}
    b=ab.compose(w,'p',run,**{**req,'request_id':'compose-2','previous_build_id':a['build_id'],'patches':[patch]})
    assert b['chapter_reuse']=={'q1':'reused','q2':'rebuilt'}
    assert b['update']['reused_questions']==['q1']
    assert not b['reviews']['can_export']
    assert ab.status(w,'p',a['build_id'])['reviews']['can_export']
    old=w.rows[a['build_id']]['payload']['normalized']['q1']
    new=w.rows[b['build_id']]['payload']['normalized']['q1']
    assert old['sha256']==new['sha256']


def test_interrupted_export_recovers_without_rerunning(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id'];approve(w,bid)
    def crash(source,out,*args):fake_export(source,out);raise KeyboardInterrupt('SIMULATED CRASH')
    with pytest.raises(KeyboardInterrupt):ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=crash)
    assert ab.status(w,'p',bid)['phase']=='EXPORTING_RECOVERY_REQUIRED'
    assert ab.recover(w,'p',bid)['phase']=='WAITING_RENDER'


def test_incomplete_export_recovery_requires_new_explicit_request(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id'];approve(w,bid)
    def crash(source,out,*args):out.mkdir(parents=True);raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=crash)
    assert ab.recover(w,'p',bid)['phase']=='EXPORT_FAILED'
    assert ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=fake_export)['phase']=='EXPORT_FAILED'
    assert ab.export(w,'p',bid,request_id='exp-2',actor='TEST',exporter=fake_export)['phase']=='WAITING_RENDER'


def test_mutated_build_refused(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id'];approve(w,bid)
    (ab.ROOT/a['manuscript']).write_text('MUTATED',encoding='utf-8')
    assert ab.status(w,'p',bid)['phase']=='STALE_BUILD'
    with pytest.raises(WorkflowError):ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=fake_export)


def test_upstream_change_refuses_downstream(setup,monkeypatch):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id']
    def blocked(*args):raise WorkflowError('STALE_INPUTS')
    monkeypatch.setattr(ab,'assert_inputs',blocked)
    assert ab.status(w,'p',bid)['phase']=='STALE_BUILD'
    with pytest.raises(WorkflowError):ab.decision(w,'p',bid,request_id='d',actor='user',kind='figures',decision='approve',statement='TEST',reason='TEST',artifact_sha256='a'*64)


def test_patch_mismatch_preserves_failure(setup):
    w,run,req,_=setup
    with pytest.raises(ValueError,match='Patch occurrence'):
        ab.compose(w,'p',run,**{**req,'patches':[{'question_id':'q1','before':'ABSENT','after':'x','reason':'TEST'}]})
    assert next(iter(w.rows.values()))['phase']=='COMPOSITION_FAILED'


def test_render_pending_never_implies_W2(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id'];approve(w,bid)
    ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=fake_export)
    calls=[]
    def renderer(out,qa):calls.append(1);(qa/'TEST.txt').write_text('SYNTHETIC');return {'status':'passed','scope':'SYNTHETIC ONLY'}
    result=ab.render(w,'p',bid,request_id='render',actor='TEST',export_request_id='exp',renderer=renderer)
    assert result['phase']=='WAITING_W2' and result['W2']=='NOT_RUN'
    ab.render(w,'p',bid,request_id='render',actor='TEST',export_request_id='exp',renderer=renderer)
    assert len(calls)==1


def test_changed_previous_cache_rejected(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req)
    old=w.rows[a['build_id']]['payload']['normalized']['q1']
    (ab.ROOT/old['path']).write_text('TAMPERED',encoding='utf-8')
    with pytest.raises(WorkflowError,match='normalized chapter'):
        ab.compose(w,'p',run,**{**req,'request_id':'new','previous_build_id':a['build_id']})

def test_changed_upstream_revision_rebuilds_only_that_chapter(setup):
    w,run,req,row=setup
    first=ab.compose(w,'p',run,**req)
    row['payload']['chapters'][1]['binding']['version']=2
    second=ab.compose(w,'p',run,**{**req,'request_id':'new-input','previous_build_id':first['build_id']})
    assert second['chapter_reuse']=={'q1':'reused','q2':'rebuilt'}
    assert not second['reviews']['can_export']


def test_rejected_review_and_stale_decision_cannot_export(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id']
    args=dict(request_id='reject',actor='user',kind='manuscript',decision='reject',statement='TEST_ONLY',reason='TEST_ONLY')
    with pytest.raises(WorkflowError,match='stale artifact'):
        ab.decision(w,'p',bid,artifact_sha256='a'*64,**args)
    path=ab.source_folder(w.rows[bid])/ac.MD_NAME
    result=ab.decision(w,'p',bid,artifact_sha256=sha_file(path),**args)
    assert result['phase']=='ASSEMBLY_REJECTED'
    with pytest.raises(WorkflowError):ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=fake_export)


def test_export_provenance_mismatch_cannot_be_recovered_as_success(setup):
    w,run,req,_=setup;a=ab.compose(w,'p',run,**req);bid=a['build_id'];approve(w,bid)
    def wrong(source,out,*args):
        fake_export(source,out)
        (out/'build-manifest.json').write_text('{"source_hashes":{}}',encoding='utf-8')
    with pytest.raises(WorkflowError,match='does not bind'):
        ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=wrong)
    assert ab.status(w,'p',bid)['phase']=='EXPORT_FAILED'


def test_http_build_routes_share_workflow_and_reject_invalid_decisions():
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    calls=[]
    class Adapter:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def compose_assembly(self,project,run,**kwargs):calls.append(('compose',project,run));return {'phase':'WAITING_ASSEMBLY_REVIEW'}
        def assembly_build_status(self,project,bid):return {'phase':'WAITING_ASSEMBLY_REVIEW'}
        def export_assembly(self,project,bid,**kwargs):calls.append(('export',project,bid));return {'phase':'TEST_ONLY'}
        def render_assembly(self,project,bid,**kwargs):return {'phase':'TEST_ONLY'}
        def recover_assembly(self,project,bid):return {'phase':'TEST_ONLY'}
        def assembly_build_decision(self,*args,**kwargs):raise AssertionError('Invalid decision reached workflow')
    with TestClient(create_app(Adapter)) as client:
        path='/projects/p/assembly-builds/b'
        assert client.post('/projects/p/assembly-runs/r/builds',json={'request_id':'c','actor':'TEST','title':'测试'}).status_code==200
        assert client.get(path).status_code==200
        assert client.post(path+'/exports',json={'request_id':'e','actor':'TEST'}).status_code==200
        assert client.post(path+'/renders',json={'request_id':'r','actor':'TEST','export_request_id':'e'}).status_code==200
        assert client.post(path+'/recover').status_code==200
        assert client.post(path+'/decisions',json={'request_id':'d','actor':'codex','kind':'manuscript','decision':'approve','statement':'TEST','reason':'TEST','artifact_sha256':'a'*64}).status_code==403
    assert [c[0] for c in calls]==['compose','export']

def test_bind_existing_reviews_requires_exact_content_and_keeps_original_records(setup):
    from modelcrew.writing_reviews import manuscript_record,selection_record
    w,run,req,_=setup
    first=ab.compose(w,'p',run,**req);bid=first['build_id'];src=ab.source_folder(w.rows[bid])
    args={'decision':'approve','actor':'user','statement':'TEST_SIMULATED_EXISTING_USER_ONLY','reason':'SYNTHETIC ONLY'}
    cat=json.loads((src/'figure-catalog.json').read_text(encoding='utf-8'))
    bundle={'manuscript_review':manuscript_record(src/ac.MD_NAME,src/'figure-catalog.json',**args),
            'figure_selection_review':selection_record(src/'figure-catalog.json',[f['id'] for f in cat['figures'] if f['formal']],**args)}
    evidence=ab.ROOT/'prior-reviews.json';evidence.write_text(json.dumps(bundle),encoding='utf-8');original=evidence.read_bytes()
    request={'request_id':'existing-review-1','actor':'TEST_ONLY_ORCHESTRATOR','reason':'SYNTHETIC binding',
             'review_path':'prior-reviews.json','review_sha256':sha_file(evidence)}
    bound=ab.bind_reviews(w,'p',bid,**request)
    assert bound['phase']=='READY_TO_EXPORT' and bound['reviews']['can_export']
    assert ab.bind_reviews(w,'p',bid,**request)==bound and evidence.read_bytes()==original
    assert w.rows[bid]['payload']['manuscript_review']==bundle['manuscript_review']
    # A new manuscript cannot inherit a decision based on matching figure bytes alone.
    second=ab.compose(w,'p',run,**{**req,'request_id':'compose-different','abstract':'另一份摘要用于验证正文变化后不能继承历史批准。'})
    with pytest.raises(WorkflowError,match='do not match'):
        ab.bind_reviews(w,'p',second['build_id'],**request)
    with pytest.raises(WorkflowError,match='changed'):
        ab.bind_reviews(w,'p',second['build_id'],**{**request,'review_sha256':'0'*64})
    assert not ab.status(w,'p',second['build_id'])['reviews']['can_export']

def test_review_cache_projection_proves_all_other_evidence_unchanged(setup):
    from modelcrew.writing_reviews import manuscript_record,selection_record,review_status
    w,run,req,_=setup;built=ab.compose(w,'p',run,**req);src=ab.source_folder(w.rows[built['build_id']])
    original=ab.ROOT/'original-approved';shutil.copytree(src,original)
    path=original/'figure-catalog.json';cat=json.loads(path.read_text(encoding='utf-8'))
    for c in cat['evidence']['chapters']:c.update(identity='historical-cache',normalized_sha256='historical-cache-sha')
    path.write_text(json.dumps(cat),encoding='utf-8')
    args={'decision':'approve','actor':'user','statement':'TEST_SIMULATED_EXISTING_USER_ONLY','reason':'SYNTHETIC ONLY'}
    text=manuscript_record(original/ac.MD_NAME,path,**args)
    figures=selection_record(path,[f['id'] for f in cat['figures'] if f['formal']],**args)
    records_before=deepcopy((text,figures))
    a,b,evidence=ab._project_cache_only_reviews(src,'original-approved',text,figures)
    assert review_status(src/ac.MD_NAME,src/'figure-catalog.json',a,b)['can_export']
    assert not evidence['approval_created'] and a['original_snapshot']==text['snapshot']
    assert (text,figures)==records_before
    # Even an evidence-only semantic change, with identical MD/PNG, is blocked.
    cat['evidence']['chapters'][0]['scientific_source']='different-result'
    path.write_text(json.dumps(cat),encoding='utf-8')
    text=manuscript_record(original/ac.MD_NAME,path,**args)
    figures=selection_record(path,[f['id'] for f in cat['figures'] if f['formal']],**args)
    with pytest.raises(WorkflowError,match='scientific evidence'):
        ab._project_cache_only_reviews(src,'original-approved',text,figures)

@pytest.fixture
def w2_ready(setup,monkeypatch):
    # Frozen v1 compatibility/recovery cases; v2 has dedicated integration checks.
    from modelcrew import assembly_w2
    monkeypatch.setattr(assembly_w2,'CURRENT_PROTOCOL','1.0.0')
    w,run,req,_=setup
    path=ab.ROOT/'claim.json';path.write_text('{"number":1}',encoding='utf-8')
    monkeypatch.setattr(ab,'claim_evidence',lambda row:{'claims':[{'global_claim_id':'q1-test','statement':'SYNTHETIC',
        'evidence':[{'frozen_path':'claim.json','sha256':sha_file(path),'selector':'/number'}]}]})
    built=ab.compose(w,'p',run,**req);bid=built['build_id'];approve(w,bid)
    ab.export(w,'p',bid,request_id='exp',actor='TEST',exporter=fake_export)
    def renderer(out,qa):
        formats={}
        for kind in ['latex','word']:
            Image.new('RGB',(10,10),'white').save(qa/(kind+'-001.png'))
            formats[kind]={'pages':[{'page':1}]}
        result={'status':'passed','formats':formats,'scope':'SYNTHETIC ONLY'}
        (qa/'render-check.json').write_text(json.dumps(result),encoding='utf-8')
        return result
    ab.render(w,'p',bid,request_id='render',actor='TEST',export_request_id='exp',renderer=renderer)
    req={'request_id':'w2','actor':'TEST','export_request_id':'exp','render_request_id':'render'}
    return w,bid,req


class W2Model:
    def __init__(self,change=None):self.calls=0;self.change=change
    def call(self,folder,stage,system,data,**kwargs):
        self.calls+=1
        assert stage=='W2' and len(kwargs['image_inputs'])==2
        assert 'author conversation' in system
        answer={'status':'PASS','checks':[{'check_id':c,'status':'PASS','explanation':'SYNTHETIC REVIEW ONLY',
                    'evidence':[{'artifact_id':'render','selector':'/status'}]} for c in data['required_checks']],
                'pages_reviewed':[{'artifact_id':i['artifact_id'],'status':'PASS','finding':'SYNTHETIC PAGE ONLY'} for i in data['images']],
                'issues':[]}
        if self.change:self.change(answer)
        return answer,{'status':'completed','image_count':2,'independent_stateless_request':True}


def test_w2_independent_receipt_binding_and_idempotency(w2_ready):
    from modelcrew.assembly_w2 import start
    from modelcrew.collaboration import CollaborationStore,Snapshot,Receipt,Ticket
    w,bid,req=w2_ready;model=W2Model()
    result=start(w,'p',bid,model=model,**req)
    assert result['phase']=='W2_PASSED' and result['W2']=='PASS'
    assert start(w,'p',bid,model=model,**req)==result and model.calls==1
    op=result['w2_reviews']['w2'];store=CollaborationStore(ab.ROOT/op['folder']/'records',root=ab.ROOT)
    snap=store.load(Snapshot,op['snapshot_sha256']);ticket=store.load(Ticket,op['ticket_sha256'])
    assert ticket.gate=='W2' and ticket.binding.task_id=='assembly:'+bid
    assert ticket.reviewer_call_id not in snap.lineage_call_ids
    assert store.accept_review(store.load(Receipt,op['receipt_sha256']),op['snapshot_sha256'])==op['receipt_sha256']
    with pytest.raises(WorkflowError,match='reused'):start(w,'p',bid,model=model,**{**req,'actor':'DIFFERENT'})


@pytest.mark.parametrize('defect',['missing_page','duplicate_page','unknown_pointer','contradiction','hidden_failure'])
def test_w2_does_not_repair_bad_reviewer_output(w2_ready,defect):
    from modelcrew.assembly_w2 import start
    w,bid,req=w2_ready
    def change(a):
        if defect=='missing_page':a['pages_reviewed'].pop()
        if defect=='duplicate_page':a['pages_reviewed'][1]=a['pages_reviewed'][0]
        if defect=='unknown_pointer':a['checks'][0]['evidence'][0]['selector']='/missing'
        if defect=='contradiction':a['status']='FAIL'
        if defect=='hidden_failure':a['pages_reviewed'][0]['status']='FAIL'
    model=W2Model(change)
    with pytest.raises(ValueError):start(w,'p',bid,model=model,**req)
    assert ab.status(w,'p',bid)['phase']=='W2_INVALID_RESPONSE'
    start(w,'p',bid,model=model,**req)
    assert model.calls==1


def test_unknown_w2_is_not_resent_with_same_or_new_key(w2_ready):
    from modelcrew.assembly_w2 import start
    from modelcrew.model_client import ModelCallError
    w,bid,req=w2_ready
    class Unknown:
        calls=0
        def call(self,*args,**kwargs):self.calls+=1;raise ModelCallError('transport unknown')
    model=Unknown()
    with pytest.raises(ModelCallError):start(w,'p',bid,model=model,**req)
    with pytest.raises(ModelCallError):start(w,'p',bid,model=model,**req)
    with pytest.raises(WorkflowError,match='do not resend'):start(w,'p',bid,model=model,**{**req,'request_id':'new'})
    assert model.calls==1


def test_w2_actual_fail_and_blocked_are_preserved(w2_ready):
    from modelcrew.assembly_w2 import start
    w,bid,req=w2_ready
    def change(a):
        a['status']='BLOCKED';a['checks'][0]['status']='BLOCKED'
        a['issues']=[{'check_id':'claims','severity':'blocking','domain':'infrastructure','target':'recovery',
                     'reason':'SYNTHETIC missing evidence','recheck':'SYNTHETIC inspect source'}]
    result=start(w,'p',bid,model=W2Model(change),**req)
    assert result['phase']=='W2_BLOCKED' and result['W2']=='BLOCKED'

def test_w2_recovery_uses_cached_raw_response_without_second_provider_call(w2_ready):
    from modelcrew.assembly_w2 import start
    from modelcrew.model_client import ModelCallError
    w,bid,req=w2_ready
    class Cached(W2Model):
        def call(self,folder,stage,system,data,**kwargs):
            answer,meta=super().call(folder,stage,system,data,**kwargs)
            raw={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer)}}]}
            path=folder/'W2-fixture-response.json';path.write_text(json.dumps(raw),encoding='utf-8')
            (folder/'W2-fixture-metadata.json').write_text(json.dumps({**meta,'call_id':'fixture','response_sha256':sha_file(path)}),encoding='utf-8')
            raise ModelCallError('SYNTHETIC interruption after durable provider response')
    model=Cached()
    with pytest.raises(ModelCallError):start(w,'p',bid,model=model,**req)
    result=start(w,'p',bid,model=model,**req)
    assert result['phase']=='W2_PASSED' and model.calls==1
    assert ab.recover(w,'p',bid)['phase']=='W2_PASSED'


def test_w2_recovery_rejects_tampered_cached_raw_response(w2_ready):
    from modelcrew.assembly_w2 import start
    from modelcrew.model_client import ModelCallError
    w,bid,req=w2_ready
    class Cached(W2Model):
        def call(self,folder,*args,**kwargs):
            raw=folder/'W2-fixture-response.json';raw.write_text('{}',encoding='utf-8')
            (folder/'W2-fixture-metadata.json').write_text(json.dumps({'status':'completed','call_id':'fixture','response_sha256':sha_file(raw)}),encoding='utf-8')
            raw.write_text('{"changed":true}',encoding='utf-8')
            raise ModelCallError('SYNTHETIC interrupted')
    with pytest.raises(ModelCallError):start(w,'p',bid,model=Cached(),**req)
    with pytest.raises(WorkflowError,match='raw W2 response changed'):start(w,'p',bid,model=W2Model(),**req)
    assert ab.status(w,'p',bid)['W2']=='UNKNOWN'


def test_w2_refuses_unrendered_or_stale_export(w2_ready):
    from modelcrew.assembly_w2 import start
    w,bid,req=w2_ready
    model=W2Model()
    with pytest.raises(WorkflowError,match='completed export'):
        start(w,'p',bid,model=model,**{**req,'render_request_id':'missing'})
    # Failed packet creation cannot grant a review or consume an external call.
    assert model.calls==0 and not w.rows[bid]['payload'].get('w2_reviews')

def test_w2_delivery_retry_requires_proof_of_no_http_delivery(w2_ready):
    from modelcrew.assembly_w2 import start,retry_delivery
    from modelcrew.model_client import ModelCallError
    w,bid,req=w2_ready
    class NotSent:
        calls=0
        def call(self,folder,*args,**kwargs):
            self.calls+=1
            (folder/'W2-not-sent-metadata.json').write_text(json.dumps({'status':'not_sent','error_type':'ConnectError','http_status':None}),encoding='utf-8')
            raise ModelCallError('not delivered',domain='not_sent')
    first=NotSent()
    with pytest.raises(ModelCallError):start(w,'p',bid,model=first,**req)
    assert start(w,'p',bid,model=first,**req)['phase']=='W2_DELIVERY_BLOCKED' and first.calls==1
    model=W2Model()
    result=retry_delivery(w,'p',bid,'w2',model=model,request_id='retry-1',actor='TEST',reason='SYNTHETIC proved not delivered')
    assert result['phase']=='W2_PASSED' and model.calls==1
    with pytest.raises(WorkflowError,match='Cannot prove'):
        retry_delivery(w,'p',bid,'w2',model=model,request_id='retry-2',actor='TEST',reason='Must reject after delivery')


def test_w2_does_not_retry_read_timeout_delivery(w2_ready):
    from modelcrew.assembly_w2 import start,retry_delivery
    from modelcrew.model_client import ModelCallError
    w,bid,req=w2_ready
    class Ambiguous:
        def call(self,folder,*args,**kwargs):
            (folder/'W2-unknown-metadata.json').write_text(json.dumps({'status':'unknown','error_type':'ReadTimeout','http_status':None}),encoding='utf-8')
            raise ModelCallError('ambiguous delivery')
    with pytest.raises(ModelCallError):start(w,'p',bid,model=Ambiguous(),**req)
    with pytest.raises(WorkflowError,match='Cannot prove'):
        retry_delivery(w,'p',bid,'w2',model=W2Model(),request_id='retry',actor='TEST',reason='Must not retry ambiguous read')

def test_w2_one_recheck_has_new_context_and_preserves_rejected_response(w2_ready):
    from modelcrew.assembly_w2 import start
    w,bid,req=w2_ready
    bad=W2Model(lambda a:a.update(status='FAIL'))
    with pytest.raises(WorkflowError):start(w,'p',bid,model=bad,**req)
    original=deepcopy(w.rows[bid]['payload']['w2_reviews']['w2'])
    path=ab.ROOT/original['folder']/'answer.json';before=path.read_bytes()
    result=start(w,'p',bid,model=W2Model(),**{**req,'request_id':'recheck','recheck_of':'w2','rationale':'SYNTHETIC contradictory original'})
    assert result['phase']=='W2_PASSED' and path.read_bytes()==before
    assert result['w2_reviews']['recheck']['reviewer_context_id']!=original['reviewer_context_id']
    assert result['w2_reviews']['w2']['phase']=='INVALID_RESPONSE'
    with pytest.raises(WorkflowError,match='One independent recheck'):
        start(w,'p',bid,model=W2Model(),**{**req,'request_id':'another','recheck_of':'w2','rationale':'SYNTHETIC third attempt must block'})


def test_w2_pass_cannot_be_rechecked(w2_ready):
    from modelcrew.assembly_w2 import start
    w,bid,req=w2_ready;start(w,'p',bid,model=W2Model(),**req)
    with pytest.raises(WorkflowError,match='One independent recheck'):
        start(w,'p',bid,model=W2Model(),**{**req,'request_id':'recheck','recheck_of':'w2','rationale':'SYNTHETIC forbid repeat PASS'})

def test_w2_http_endpoint_runs_independent_lifecycle_and_rejects_incomplete_recheck(w2_ready):
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    from modelcrew.assembly_w2 import start
    w,bid,req=w2_ready;model=W2Model()
    class Adapter:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def review_assembly_w2(self,project,build_id,**kwargs):return start(w,project,build_id,model=model,**kwargs)
    with TestClient(create_app(Adapter)) as client:
        url=f'/projects/p/assembly-builds/{bid}/w2-reviews'
        response=client.post(url,json=req);assert response.status_code==200 and response.json()['W2']=='PASS'
        assert client.post(url,json=req).json()==response.json() and model.calls==1
        assert client.post(url,json={**req,'recheck_of':'w2'}).status_code==422

class W2ReferenceModel:
    def __init__(self,status='PASS'):self.calls=0;self.status=status
    def call(self,folder,stage,system,data,**kwargs):
        self.calls+=1
        assert data['output_protocol']=='w2_evidence_refs_v2'
        assert all('selector' not in v and 'artifact_id' not in v for v in data['evidence'])
        assert all(i['label'].startswith('P') for i in kwargs['image_inputs'])
        reference=data['evidence'][0]['ref_id']
        answer={'protocol_version':'2.2.0','status':self.status,
          'checks':[{'check_id':c,'status':self.status if c=='claims' else 'PASS','evidence_refs':[reference],
                     'explanation':'SYNTHETIC reference review'} for c in data['required_checks']],
          'pages_reviewed':[{'page_ref':p['page_ref'],'status':'PASS','finding':'SYNTHETIC page'} for p in data['pages']],
          'issues':[]}
        if self.status!='PASS':answer['issues']=[{'check_id':'claims','severity':'error','issue_kind':'writing',
                 'reason':'SYNTHETIC genuine issue preserved','recheck':'SYNTHETIC check source'}]
        return answer,{'status':'completed','independent_stateless_request':True}


@pytest.mark.parametrize('verdict',['PASS','FAIL','BLOCKED'])
def test_v2_reference_protocol_is_admitted_without_modifying_reviewer_verdict(w2_ready,monkeypatch,verdict):
    from modelcrew import assembly_w2
    monkeypatch.setattr(assembly_w2,'CURRENT_PROTOCOL','2.2.0')
    w,bid,req=w2_ready;model=W2ReferenceModel(verdict)
    result=assembly_w2.start(w,'p',bid,model=model,**req)
    assert result['W2']==verdict and model.calls==1
    op=result['w2_reviews']['w2'];base=ab.ROOT/op['folder']
    raw=ab.read(base/'answer.json');compiled=ab.read(base/'compiled-answer.json')
    assert raw['status']==compiled['native_answer']['status']==verdict
    assert compiled['compilation']['verdict_preserved']
    for a,b in zip(raw['issues'],compiled['native_answer']['issues']):
        assert all(a[k]==b[k] for k in ['check_id','severity','reason','recheck'])
        assert b['domain']==b['target']=='writing'
    assert 'model-packet' in {a['artifact_id'] for a in ab.read(base/'records/Snapshot'/(op['snapshot_sha256']+'.json'))['artifacts']}
    assert assembly_w2.start(w,'p',bid,model=model,**req)==result and model.calls==1


def test_v2_cached_raw_response_recovers_without_schema_or_verdict_repair(w2_ready,monkeypatch):
    from modelcrew import assembly_w2
    from modelcrew.model_client import ModelCallError
    monkeypatch.setattr(assembly_w2,'CURRENT_PROTOCOL','2.2.0')
    w,bid,req=w2_ready
    class Cached(W2ReferenceModel):
        def call(self,folder,*args,**kwargs):
            answer,meta=super().call(folder,*args,**kwargs)
            raw={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer)}}]}
            path=folder/'W2-reference-response.json';path.write_text(json.dumps(raw),encoding='utf-8')
            (folder/'W2-reference-metadata.json').write_text(json.dumps({**meta,'call_id':'reference','response_sha256':sha_file(path)}),encoding='utf-8')
            raise ModelCallError('SYNTHETIC crash after raw response')
    model=Cached('BLOCKED')
    with pytest.raises(ModelCallError):assembly_w2.start(w,'p',bid,model=model,**req)
    result=assembly_w2.start(w,'p',bid,model=model,**req)
    assert result['W2']=='BLOCKED' and model.calls==1

def test_w2_rejects_omitted_physical_pages(w2_ready):
    """A valid complete PDF audit cannot hide missing pages in the W2 image list."""
    import fitz
    from modelcrew import assembly_w2
    from modelcrew.pdf_checks import inspect_pdf
    w,bid,args=w2_ready
    row=ab.load(w,'p',bid)
    p=row['payload'];qa=ab.ROOT/p['renders']['render']['folder']
    out=ab.ROOT/p['exports']['exp']['output']
    # Synthetic test export only: replace the fixture's fake PDF with 3 real pages.
    with fitz.open() as doc:
        for n in range(3):doc.new_page().insert_text((40,80),'SYNTHETIC physical page '+str(n+1),fontsize=12)
        doc.save(out/'actual-three-pages.pdf',no_new_id=True)
    (out/'paper.pdf').write_bytes((out/'actual-three-pages.pdf').read_bytes())
    p['sealed'][ab.rel(out/'paper.pdf')]=sha_file(out/'paper.pdf')
    complete=inspect_pdf(out/'paper.pdf',qa/'latex-pdf-check')
    p['renders']['render']['result']['formats']['latex']['pdf_check']=complete
    # render['pages'] still contains only page 1, despite 3 actual physical pages.
    base=ab.folder(bid)/'w2-missing-page-fixture';base.mkdir()
    request=assembly_w2.W2Request.model_validate(args)
    with pytest.raises(WorkflowError,match='complete PDF'):
        assembly_w2.packet(row,request,base)


class W2V3Model:
    calls=0
    def call(self,folder,stage,system,data,**kwargs):
        self.calls+=1
        assert data['output_protocol']=='w2_evidence_refs_v3'
        refs=data['evidence'];pages=data['pages']
        return {'protocol_version':'3.0.0',
            'checks':[{'check_id':c,'status':'PASS','evidence_refs':[refs[0]['ref_id']],
                       'explanation':'SYNTHETIC detail '*50} for c in data['required_checks']],
            'issues':[],'pages_reviewed':[{'page_ref':p['page_ref'],'status':'PASS','finding':'SYNTHETIC page'} for p in pages]},{'status':'completed','call_id':'synthetic-v3'}


def test_v3_runtime_admission_preserves_long_original_details(w2_ready,monkeypatch):
    from modelcrew import assembly_w2 as w2
    from modelcrew.contracts import digest
    monkeypatch.setattr(w2,'CURRENT_PROTOCOL','3.0.0')
    w,bid,req=w2_ready;model=W2V3Model()
    result=w2.start(w,'p',bid,model=model,**req)
    assert result['phase']=='W2_PASSED' and model.calls==1
    op=w.rows[bid]['payload']['w2_reviews'][req['request_id']]
    base=ab.ROOT/op['folder'];raw=json.loads((base/'answer.json').read_text(encoding='utf-8'))
    details=json.loads((base/'review-details.json').read_text(encoding='utf-8'))
    assert raw==details and len(raw['checks'][0]['explanation'])>300
    compiled=json.loads((base/'compiled-answer.json').read_text(encoding='utf-8'))
    assert compiled['compilation']['detail_report']['canonical_sha256']==digest(raw)
    assert 'review-details.json' in compiled['native_answer']['checks'][0]['explanation']
    assert str((base/'review-details.json').relative_to(ab.ROOT).as_posix()) in w.rows[bid]['payload']['sealed']
