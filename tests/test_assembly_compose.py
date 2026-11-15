"""Fast pure checks for reference/patch failures and uncaptioned tables."""
import pytest
from modelcrew import assembly_compose as ac


def manuscript(body='正文说明。'):
    return '\n\n'.join('## '+s+'\n\n'+('[1] 测试来源。' if s=='参考文献' else body) for s in ac.policy()['required_sections'])


def test_normalization_rejects_duplicate_sections():
    with pytest.raises(ValueError,match='Duplicate section'):
        ac.normalize('q',manuscript()+'\n\n## 摘要\n重复',{'figures':[]},[])


def test_normalization_rejects_reserved_markers():
    with pytest.raises(ValueError,match='Reserved'):
        ac.normalize('q',manuscript('@@ASM_figures_q_1@@'),{'figures':[]},[])


def test_generated_symbol_caption_has_stable_local_identity():
    text=manuscript().replace('## 符号说明\n\n正文说明。','## 符号说明\n\n| 符号 | 单位 |\n|---|---|\n| $x$ | m |')
    normalized=ac.normalize('q',text,{'figures':[]},[])
    assert '表1 符号说明表' in normalized['sections']['符号说明']
    assert normalized['generated_captions'][0]['local_number']==1


def test_patch_is_exact_and_audited():
    text=manuscript().replace('正文说明。','实际说明。',1)
    patch={'question_id':'q','before':'实际说明。','after':'已核对说明。','expected_count':1,'reason':'TEST_ONLY'}
    normalized=ac.normalize('q',text,{'figures':[]},[patch])
    assert normalized['edits'][0]['actual_count']==1
    assert normalized['sections']['摘要']=='已核对说明。'


def test_ambiguous_patch_rejected():
    patch={'question_id':'q','before':'正文说明。','after':'修改。','expected_count':1,'reason':'TEST_ONLY'}
    with pytest.raises(ValueError,match='occurrence'):
        ac.normalize('q',manuscript(),{'figures':[]},[patch])


def test_duplicate_reference_rejected():
    text=manuscript().replace('[1] 测试来源。','[1] 测试来源。\n\n[1] 重复。')
    with pytest.raises(ValueError,match='Duplicate reference'):
        ac.normalize('q',text,{'figures':[]},[])
