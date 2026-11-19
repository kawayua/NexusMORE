"""Readable model documents retain complete evidence and immutable identities."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from modelcrew.business_contract import BusinessContractError
from modelcrew.contracts import digest
from modelcrew.dsh_chat import save_review_document, _verify_document
from modelcrew.review_documents import render_model, RENDERER_VERSION
from test_business_mcp import contract


def review():
    c=contract({'sha256':'a'*64,'artifact_id':'synthetic'})
    return {'pending':{'kind':'model','binding':{'project_id':'p','task_id':'t','version':2}},
            'dossier':{'contract':{'content':c},'mathematics':None,'modeling_runs':[]},
            'review_files':[],'review_texts':[]}


def prose_review(tmp_path):
    r=review();source=tmp_path/'modeling/proposal.md';source.parent.mkdir()
    source.write_text('## 建模依据\n根据题目采用二维模型，保留端面影响。\n\n## 方程与求解\n扩散系数 D=7e-9*exp(-0.89/C)（eq:diffusion）。\n\n## questions 判定\nINTERNAL_ONLY_METADATA\n',encoding='utf-8')
    r['dossier']['modeling_runs']=[{'version':1,'payload':{'attempts':[{'status':'PASS','proposal_path':'missing-old.md'}]}},
        {'version':2,'payload':{'attempts':[{'status':'PASS','proposal_path':'modeling/proposal.md'}]}}]
    return r,source


def test_prose_precedes_checks_and_machine_fields_are_only_in_evidence(tmp_path):
    r,source=prose_review(tmp_path)
    title,md,sources=render_model(r,tmp_path)
    assert md.index('根据题目采用二维模型')<md.index('### 检查计划')
    assert 'D=7e-9*exp(-0.89/C)' in md
    for raw in ['artifact:','schema_version','sha256','INTERNAL_ONLY_METADATA','eq:diffusion']:
        assert raw not in md
    p=save_review_document(r,{'project_id':'p','task_id':'t'},'session-readable',None,tmp_path)
    path=Path(p['local_path']);record=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    evidence=json.loads((path.parent/record['evidence_file']).read_text(encoding='utf-8'))
    assert evidence['review']==r
    assert evidence['proposal_sources'][0]['text']==source.read_bytes().decode('utf-8-sig')
    assert sources[0]['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert evidence['renderer_version']==p['renderer_version']==RENDERER_VERSION
    assert 'dsh-resource://file/session/' in p['markdown']


def test_absent_prose_falls_back_to_current_contract_without_fabrication(tmp_path):
    r=review();_,md,sources=render_model(r,tmp_path)
    assert not sources and '没有可引用的建模说明正文' in md
    assert r['dossier']['contract']['content']['method']['steps'][0] in md
    assert '拟执行的检查' in md
    assert 'unknown' not in md and 'sha256' not in md


def test_new_model_layout_has_a_new_identity_and_keeps_old_files(tmp_path):
    r,_=prose_review(tmp_path);scope={'project_id':'p','task_id':'t'};session='session-readable'
    base=tmp_path/'runs/reviews/dsh'/digest(session);base.mkdir(parents=True)
    old_key=digest({'session':session,'review':digest(r)})
    old=base/(old_key+'.md');old.write_bytes(b'old immutable review')
    p=save_review_document(r,scope,session,None,tmp_path)
    assert p['preview_id']!=old_key and old.read_bytes()==b'old immutable review'
    assert Path(p['local_path']).parent.name=='readable-model-v1'
    assert save_review_document(r,scope,session,None,tmp_path)==p


@pytest.mark.parametrize('target',['markdown','evidence','source'])
def test_changed_document_evidence_or_prose_cannot_be_confirmed(tmp_path,target):
    r,source=prose_review(tmp_path)
    p=save_review_document(r,{'project_id':'p','task_id':'t'},'session-readable',None,tmp_path)
    path=Path(p['local_path']);record=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    changed={'markdown':path,'evidence':path.parent/record['evidence_file'],'source':source}[target]
    changed.write_text('tampered content',encoding='utf-8')
    with pytest.raises(BusinessContractError):_verify_document(record,path.parent,p['preview_id'],tmp_path)


def test_source_changes_create_a_new_preview_instead_of_overwriting(tmp_path):
    r,source=prose_review(tmp_path);scope={'project_id':'p','task_id':'t'}
    a=save_review_document(r,scope,'session-readable',None,tmp_path)
    old=Path(a['local_path']).read_bytes()
    source.write_text('## 建模思路\n变更后的说明需要重新展示。\n',encoding='utf-8')
    b=save_review_document(r,scope,'session-readable',None,tmp_path)
    assert a['preview_id']!=b['preview_id'] and Path(a['local_path']).read_bytes()==old


def test_outside_workspace_model_prose_is_rejected(tmp_path):
    r=review();r['dossier']['modeling_runs']=[{'version':2,'payload':{'attempts':[{'status':'PASS','proposal_path':'../outside.md'}]}}]
    with pytest.raises(BusinessContractError):render_model(r,tmp_path)
