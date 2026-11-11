"""D5 safety boundaries; synthetic fixtures never approve real business artifacts."""
import json
from pathlib import Path
import pytest
from PIL import Image
from modelcrew import writing_hand as wh
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.collaboration import Artifact,Binding,Call,Snapshot,CollaborationStore
from modelcrew.modeling_paper import writing_context,policy,sha,require_review_for_export
from modelcrew.writing_reviews import selection_record

@pytest.fixture
def run(tmp_path):
    folder=tmp_path/'writing';folder.mkdir()
    store=CollaborationStore(folder/'records')
    contract={'test':'SYNTHETIC_NOT_REAL_RESULT'}
    binding=Binding(task_id='TEST_ONLY',contract_version=1,contract_sha256=digest(contract),execution_id='TEST-EXECUTION',result_revision=1)
    author=Call(call_id='test-writer',context_id='test-author-context',role='writing',binding=binding)
    modeler=Call(call_id='test-modeler',context_id='test-model-context',role='modeling',binding=binding)
    coder=Call(call_id='test-coder',context_id='test-code-context',role='coding',binding=binding)
    for c in [author,modeler,coder]:store.register_call(c)
    artifacts=[]
    for name,kind,owner,value in [('outline','outline',author,{'claims':['TEST_ONLY']}),('contract','contract',modeler,contract),('execution','execution',coder,{'status':'TEST_ONLY'}),('result','result',coder,{'result':'TEST_ONLY'})]:
        path=folder/(name+'.json');wh.new(path,value)
        artifacts.append(Artifact(artifact_id=name,kind=kind,path=wh.rel(path),sha256=sha(path),author_call_ids=[owner.call_id]))
    key=store.freeze(Snapshot(binding=binding,hand='writing',artifacts=artifacts,lineage_call_ids=[x.call_id for x in [author,modeler,coder]]))
    wh.new(folder/'run.json',{'binding':binding.model_dump(mode='json'),'inputs':[],'workflow_sha256':writing_context()['workflow_sha256'],'W1_snapshot_sha256':key})
    wh.new(folder/'W1-context.json',{'evidence':{a.artifact_id:a.path for a in artifacts}})
    wh.state_write(folder,{'phase':'WAITING_W1','manuscript_review':'pending','figure_selection':'approved_from_D4'})
    figs=[]
    for i in range(9):
        files={}
        for fmt in ['png','pdf','svg']:
            path=folder/f'f{i}.{fmt}'
            if fmt=='png':Image.new('RGB',(4,4),(i*20,70,130)).save(path,dpi=(300,300))
            else:path.write_text('TEST_ONLY '+str(i),encoding='utf-8')
            files[fmt]={'path':path.name,'sha256':sha(path)}
        figs.append({'id':f'f{i}','category':['raw','process','result'][i//3],'question_ids':['q1'],'title':'测试数据图','purpose':'测试证据','formal':True,'number':i+1,'files':files})
    catalog=folder/'figure-catalog.json';wh.new(catalog,{'figures':figs,'question_ids':['q1']})
    wh.new(folder/'figure-selection-review.json',selection_record(catalog,[f['id'] for f in figs],decision='approve',actor='TEST_SIMULATED_USER',statement='TEST_ONLY',reason='TEST_ONLY'))
    text='\n\n'.join('## '+s+'\n根据题目条件分析模型与求解结果，并说明单位、假设与局限。'*3 for s in policy()['required_sections'])
    for f in figs:
        n=f['number'];text+=f'\n\n正文图{n}说明数据。\n\n![图{n} 测试数据]({f["files"]["png"]["path"]})\n\n图{n} 测试数据。'
    draft=folder/'supplied.md';draft.write_text(text,encoding='utf-8')
    return folder,draft

def reply(folder,status='PASS',selector='/claims'):
    checks=[{'check_id':c,'status':status if c=='claims' else 'PASS','evidence':[{'artifact_id':'outline','selector':selector}],'explanation':'TEST_ONLY'} for c in ['claims','evidence','citations','outline']]
    issues=[] if status=='PASS' else [{'check_id':'claims','severity':'error','domain':'writing','target':'writing','reason':'TEST_ONLY missing claim','recheck':'Revise outline then recheck'}]
    wh.new(folder/'W1-response.json',{'status':status,'checks':checks,'issues':issues})

def pass_gate(folder):
    wh.dispatch(folder,'test-independent');reply(folder);wh.admit(folder)

def test_long_prose_blocked_without_W1(run):
    folder,draft=run
    with pytest.raises(ValueError,match='W1 must PASS'):wh.publish(folder,draft)
    assert not (folder/'单题论文-中文审阅稿.md').exists()

def test_actual_failure_routes_without_publishing(run):
    folder,draft=run;wh.dispatch(folder,'test-independent');reply(folder,'FAIL');admission=wh.admit(folder)
    assert admission['status']=='FAIL' and wh.read(folder/'state.json')['rework_targets']==['writing']
    with pytest.raises(ValueError,match='independent W1 PASS'):wh.publish(folder,draft)

def test_reviewer_cannot_reuse_writer_context(run):
    folder,_=run;meta=wh.read(folder/'run.json');store=CollaborationStore(folder/'records')
    c=Call(call_id='bad-reviewer',context_id='test-author-context',role='quality',binding=Binding.model_validate(meta['binding']));store.register_call(c)
    with pytest.raises(ValueError,match='participated'):store.dispatch_review(meta['W1_snapshot_sha256'],'W1',c.call_id)

def test_bad_pointer_cannot_be_admitted(run):
    folder,_=run;wh.dispatch(folder,'test-independent');reply(folder,selector='/missing')
    with pytest.raises(ValueError,match='does not resolve'):wh.admit(folder)
    assert not (folder/'W1-admission.json').exists()

def test_contradictory_reported_status_rejected(run):
    folder,_=run;wh.dispatch(folder,'test-independent');reply(folder)
    p=folder/'W1-response.json';x=wh.read(p);x['status']='FAIL';p.write_text(json.dumps(x),encoding='utf-8')
    with pytest.raises(ValueError,match='contradicts'):wh.admit(folder)

def test_outline_edits_after_dispatch_reject_old_receipt(run):
    folder,_=run;wh.dispatch(folder,'test-independent');reply(folder)
    (folder/'outline.json').write_text('{"claims":["changed"]}',encoding='utf-8')
    with pytest.raises(ValueError,match='changed'):wh.admit(folder)

def test_original_W1_reply_tampering_blocks_publication(run):
    folder,draft=run;pass_gate(folder)
    p=folder/'W1-response.json';p.write_text(p.read_text(encoding='utf-8')+' ',encoding='utf-8')
    with pytest.raises(ValueError,match='reply changed'):wh.publish(folder,draft)

def test_pass_delivers_pending_manuscript_with_existing_figure_consent(run):
    folder,draft=run;pass_gate(folder);s=wh.publish(folder,draft)
    assert s['state']['phase']=='WAITING_MANUSCRIPT_APPROVAL'
    assert s['state']['reviews']['manuscript']=='pending'
    assert s['state']['reviews']['figure_selection']=='approved'
    assert not s['state']['reviews']['can_export']
    assert wh.status(Path(str(folder)))==s  # A fresh path/session reads the same durable state.

def test_changed_delivered_body_blocks_resume_and_approval(run):
    folder,draft=run;pass_gate(folder);wh.publish(folder,draft)
    p=folder/'单题论文-中文审阅稿.md';p.write_text(p.read_text(encoding='utf-8')+'修改',encoding='utf-8')
    with pytest.raises(ValueError,match='Delivered'):wh.status(folder)
    with pytest.raises(ValueError,match='Delivered'):wh.record_manuscript_decision(folder,decision='approve',actor='user',statement='TEST_ONLY',reason='TEST_ONLY')

def test_selected_image_tampering_blocks_resume(run):
    folder,draft=run;pass_gate(folder);wh.publish(folder,draft)
    (folder/'f0.png').write_bytes(b'TAMPERED')
    with pytest.raises(ValueError,match='Changed figure'):wh.status(folder)

def test_real_manuscript_decision_is_separate_and_updates_export_review_bundle(run):
    folder,draft=run;pass_gate(folder);wh.publish(folder,draft)
    with pytest.raises(ValueError,match='explicit user'):wh.record_manuscript_decision(folder,decision='approve',actor='writer',statement='TEST_ONLY',reason='TEST_ONLY')
    result=wh.record_manuscript_decision(folder,decision='approve',actor='user',statement='TEST_SIMULATED_USER_ONLY',reason='TEST_ONLY')
    assert result['can_export']
    reviews=wh.read(folder/'reviews.json')
    assert require_review_for_export(folder/'单题论文-中文审阅稿.md',folder/'figure-catalog.json',reviews)['separate_reviews']['can_export']

@pytest.mark.parametrize('change',[{'current_version':2},{'result_approved':False},{'model_approved':False},{'result_revision':2},{'execution_id':'different'}])
def test_upstream_changes_block_writer(change):
    binding={'task_id':'TEST_ONLY','contract_version':1,'contract_sha256':'a'*64,'execution_id':'test-exec','result_revision':1}
    class W:
        def task(self,_):return {'current_version':1,'model_approved':True,'result_approved':True,'result_revision':1,'execution_id':'test-exec',**change}
    with pytest.raises(ValueError,match='stale'):wh.assert_upstream(W(),binding)

def test_workflow_change_invalidates_W1_before_publication(run,monkeypatch):
    folder,draft=run;pass_gate(folder)
    monkeypatch.setattr(wh,'writing_context',lambda:{'workflow_sha256':'0'*64})
    with pytest.raises(ValueError,match='workflow changed'):wh.publish(folder,draft)

def test_bad_claim_selector_fails_before_creating_run(tmp_path):
    proof=tmp_path/'proof.json';wh.new(proof,{'available':1})
    plan={'sections':[{'title':'TEST_ONLY'}],'claims':[{'evidence':[{'path':wh.rel(proof),'selector':'/missing'}]}]}
    output=tmp_path/'new-output'
    with pytest.raises(ValueError,match='does not resolve'):wh.prepare(None,output,tmp_path/'source',plan,{'references':[]},context_id='TEST_ONLY')
    assert not output.exists()

def test_changed_code_support_fails_before_creating_run(tmp_path):
    proof=tmp_path/'proof.json';wh.new(proof,{'available':1})
    code=tmp_path/'source.py';code.write_text('TEST_ONLY',encoding='utf-8')
    plan={'sections':[{'title':'TEST_ONLY'}],'claims':[{'evidence':[{'path':wh.rel(proof),'selector':'/available','support_files':[{'path':wh.rel(code),'sha256':'0'*64}]}]}]}
    output=tmp_path/'new-output'
    with pytest.raises(ValueError,match='changed'):wh.prepare(None,output,tmp_path/'source',plan,{'references':[]},context_id='TEST_ONLY')
    assert not output.exists()

def test_new_editorial_revision_preserves_previous_bytes_and_only_carries_figure_consent(run):
    folder,draft=run;pass_gate(folder);wh.publish(folder,draft)
    wh.record_manuscript_decision(folder,decision='approve',actor='user',statement='TEST_SIMULATED_USER_ONLY',reason='TEST_ONLY')
    before=sha(folder/'单题论文-中文审阅稿.md')
    destination=folder.parent/'new-revision'
    state=wh.revise_publication(folder,destination,reason='TEST_ONLY editorial correction')
    assert sha(folder/'单题论文-中文审阅稿.md')==before
    assert not (destination/'manuscript-review.json').exists()
    assert state['state']['manuscript_review']=='pending'
    replacement=destination/'supplied-revision.md';replacement.write_text(draft.read_text(encoding='utf-8')+'\n新的文字需要重新审阅。',encoding='utf-8')
    result=wh.publish(destination,replacement)
    assert result['state']['reviews']['figure_selection']=='approved'
    assert result['state']['reviews']['manuscript']=='pending'
    assert not result['state']['reviews']['can_export']
