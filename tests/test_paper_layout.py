"""Pagination and template checks without generating formal paper artifacts."""
import sys
from types import SimpleNamespace
from copy import deepcopy
import pytest
from modelcrew.paper_layout import contract, frontmatter, split_ast, rendered_frontmatter
from modelcrew.modeling_paper import writing_context
from modelcrew import assembly_compose as ac

MD='# 测试论文\n\n## 摘要\n\n真实摘要。\n\n## 关键词\n\n运动；约束\n\n## 问题重述\n\n正文。'

def test_template_read_and_mapping():
    context=writing_context();result=contract(context)
    assert len(result['read_log'])==5
    assert result['margins_mm']==25 and result['body_font_pt']==12
    assert result['frontmatter_max_pages']==1 and not result['shrink_text_to_fit']
    context['documents']=[d for d in context['documents'] if not d['path'].endswith('main.tex')]
    with pytest.raises(ValueError,match='five'):contract(context)

@pytest.mark.parametrize('bad',['### 问题一\n\n原摘要。','![图](a.png)','$$x=1$$','| 列 |'])
def test_disallow_stacked_or_nonprose_abstract(bad):
    with pytest.raises(ValueError,match='full-paper'):frontmatter(MD.replace('真实摘要。',bad))

def test_unified_keywords():
    assert frontmatter(MD)['keywords']=='运动；约束'
    with pytest.raises(ValueError,match='unified'):frontmatter(MD.replace('运动；约束','运动\n\n约束'))

def h(level,text):return {'t':'Header','c':[level,['',[],[]],[{'t':'Str','c':text}]]}
def p(text):return {'t':'Para','c':[{'t':'Str','c':text}]}

def test_ast_separates_frontmatter_and_body_without_altering_prose():
    ast={'blocks':[h(1,'测试论文'),h(2,'摘要'),p('真实摘要。'),h(2,'关键词'),p('运动；约束'),h(2,'一、问题重述'),p('正文。')],'meta':{}}
    before=deepcopy(ast);result=split_ast(ast)
    assert result['abstract']==[p('真实摘要。')]
    assert result['body_start_heading']=='一、问题重述'
    assert result['body'][1]==p('正文。')
    assert result['word_blocks'][2]['c'][0]['t']=='Strong'
    assert ast==before

@pytest.mark.parametrize('keywords_page,body_page,passed',[(1,2,True),(2,2,False),(1,1,False)])
def test_actual_page_check_requires_keywords_on_first_and_body_on_second(monkeypatch,keywords_page,body_page,passed):
    import fitz
    texts=['测试论文\n摘要\n真实摘要提及问题重述但不是标题。','']
    texts[keywords_page-1]+='\n关键词：运动；约束'
    texts[body_page-1]+='\n问题重述\n正文。'
    class Page:
        rect=SimpleNamespace(width=595,height=842)
        def __init__(self,text):self.text=text
        def get_text(self,**kwargs):return self.text
    class Document:
        def __enter__(self):return [Page(t) for t in texts]
        def __exit__(self,*args):pass
    monkeypatch.setattr(fitz,'open',lambda path:Document())
    assert (rendered_frontmatter('not-created.pdf',MD)['status']=='passed')==passed

def test_multichapter_does_not_concatenate_abstracts(tmp_path):
    with pytest.raises(ValueError,match='full-paper abstract'):
        ac.compose([{'question_id':'q1'},{'question_id':'q2'}],tmp_path/'unused','标题')
    assert not (tmp_path/'unused').exists()
