"""Synthetic combined paper and gallery; never a real approval."""
import copy,json,hashlib
from pathlib import Path
import pytest
from modelcrew.combined_paper_review import combined_pending
from modelcrew.dsh_chat import save_review_document,_verify_document
from modelcrew.business_contract import BusinessContractError,validate_request
from modelcrew.trusted_decisions import decision_request


def fixture(root):
    binding={'project_id':'p','task_id':'synthetic','version':6,'contract_sha256':'a'*64,'run_id':'synthetic-writing','execution_id':'synthetic-execution','result_revision':1}
    files=[]
    def add(name,data):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        ref={'path':name,'sha256':hashlib.sha256(data).hexdigest()};files.append({'local_path':str(p),'sha256':ref['sha256']});return ref
    figs=[]
    for i in range(13):
        assets={fmt:{**add(f'figures/f{i}.{fmt}',('SYNTHETIC_'+str(i)+fmt).encode()),'path':f'figures/f{i}.{fmt}'} for fmt in ('png','pdf','svg')}
        figs.append({'id':f'f{i}','title':f'候选图{i+1}','category':['raw','process','result'][min(i//4,2)],'formal':i<12,'number':i+1 if i<12 else None,'purpose':'真实来源的合成测试','files':assets})
    md=add('manuscript.md',('# 正文\n\n'+''.join(f'![图{i+1}](figures/f{i}.png)\n' for i in range(12))).encode())
    cat=add('figure-catalog.json',json.dumps({'figures':figs,'evidence':{'task_id':'synthetic','contract_version':6,'execution_id':'synthetic-execution','result_revision':1}},ensure_ascii=False).encode())
    plan=add('outline.json',json.dumps({'figure_plan':[{'figure_id':f'f{i}','section':'结果分析'} for i in range(12)]}).encode())
    items=[{'kind':k,'decision_operation':'hand_decide','binding':{**binding,'artifact_sha256':ref['sha256']},'artifact_ids':[k]} for k,ref in [('manuscript',md),('figures',cat)]]
    return {'pending':combined_pending(items)[0],'dossier':{'writing_review_context':{'manuscript':md,'catalog':cat,'outline':plan}},'review_files':files},items


def test_combined_scope_matches_versions_and_only_same_run(tmp_path):
    r,items=fixture(tmp_path);a=r['pending'];assert a['confirmation_scope']=='manuscript_and_figures'
    changed=copy.deepcopy(items);changed[1]['binding']['artifact_sha256']='b'*64
    assert combined_pending(changed)[0]['pending_id']!=a['pending_id']
    changed[1]['binding']['run_id']='different';assert combined_pending(changed)==[]
    assert combined_pending(items[:1])==[]
    req=decision_request(a,r,'approve','确认','确认',channel='trusted_host_ui');validate_request(req)
    assert req['arguments']['body']['approve_figures'] is True
    assert req['arguments']['body']['manuscript_sha256']==a['components']['manuscript_sha256']


def test_all_candidate_images_are_displayed_with_selection_scope(tmp_path):
    r,_=fixture(tmp_path);p=save_review_document(r,{},'session-synthetic',None,tmp_path)
    text=p['markdown'];assert text.count('### 候选图 ')==13 and text.count('![')==25
    assert '12 幅暂列正文' in text and '备选，当前不入文' in text and '拟放章节：结果分析' in text
    assert '一次同时确认当前正文' in text and p['confirmation_scope']=='manuscript_and_figures'
    assert p['renderer_version']=='readable-paper-bundle/1'
    assert save_review_document(r,{},'session-synthetic',None,tmp_path)==p
    assert len(list((Path(p['local_path']).parent/'assets').rglob('*.png')))==13


@pytest.mark.parametrize('target',['manuscript','catalog','source_image','display_image','evidence'])
def test_changed_source_or_display_prevents_confirmation(tmp_path,target):
    r,_=fixture(tmp_path);p=save_review_document(r,{},'session-synthetic',None,tmp_path);path=Path(p['local_path']);record=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    changed={'manuscript':tmp_path/'manuscript.md','catalog':tmp_path/'figure-catalog.json','source_image':tmp_path/'figures/f0.png',
             'display_image':next((path.parent/'assets').rglob('figure-001.png')),'evidence':path.parent/record['evidence_file']}[target]
    changed.write_bytes(b'CHANGED')
    with pytest.raises(BusinessContractError):_verify_document(record,path.parent,p['preview_id'],tmp_path)


def test_unregistered_or_wrong_result_cannot_enter_gallery(tmp_path):
    r,_=fixture(tmp_path);r['review_files']=r['review_files'][1:]
    with pytest.raises(BusinessContractError):save_review_document(r,{},'session-synthetic',None,tmp_path)
    r,_=fixture(tmp_path);r['pending']['binding']['execution_id']='other'
    with pytest.raises(BusinessContractError):save_review_document(r,{},'session-synthetic',None,tmp_path)


@pytest.mark.parametrize('change',['missing_hash','wrong_kind','reject'])
def test_combined_request_cannot_lose_a_component_or_change_scope(tmp_path,change):
    r,_=fixture(tmp_path);req=decision_request(r['pending'],r,'approve','确认','确认',channel='trusted_host_ui');body=req['arguments']['body']
    if change=='missing_hash':body.pop('figure_catalog_sha256')
    elif change=='wrong_kind':body['kind']='figures'
    else:body['decision']='reject'
    with pytest.raises(BusinessContractError):validate_request(req)


def test_prior_individual_approval_is_never_overwritten(tmp_path,monkeypatch):
    from modelcrew.combined_paper_review import native_decision
    from modelcrew import hand_runtime as hr
    from modelcrew.workflow import WorkflowError
    row={'phase':'WAITING_MANUSCRIPT_AND_FIGURES','payload':{'manuscript_review':{'decision':'approve','original':True}}}
    before=copy.deepcopy(row)
    monkeypatch.setattr(hr,'run_folder',lambda row:tmp_path)
    with pytest.raises(WorkflowError,match='Preserve prior'):
        native_decision(None,row,decision='approve',actor='user',statement='确认',reason='确认',artifact_sha256='a'*64,
                        request_id='synthetic',manuscript_sha256='b'*64,figure_catalog_sha256='c'*64)
    assert row==before and not list(tmp_path.iterdir())


@pytest.mark.parametrize('text',['同意','同意。','确认','通过'])
def test_plain_explicit_consent_is_supported(text):
    from modelcrew.dsh_chat import is_approval
    assert is_approval(text,'manuscript')


@pytest.mark.parametrize('text',['不同意','是否同意？','同意，但请先修改','如果没问题就同意','他说同意','“同意”'])
def test_consent_conditions_or_quotes_are_not_approval(text):
    from modelcrew.dsh_chat import is_approval
    assert not is_approval(text,'manuscript')
