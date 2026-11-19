"""Deterministic movement fixtures, never a scientific manuscript approval."""
from collections import Counter
import pytest
from modelcrew.writing_layout_repair import move_subsection,validate_plan_order
from modelcrew.workflow import WorkflowError


def test_move_preserves_subsection_verbatim_and_all_other_bytes():
    source='## 模型求解\r\n\r\n### 输出取值\r\nT=33.5765\r\n\r\n## 结果分析\r\n图6\r\n\r\n## 检验\r\n### 守恒\r\n公式 $R=1e-8$\r\n![图5](f5.png)\r\n图5 题注\r\n\r\n### 网格\r\n后文\r\n'
    updated,proof=move_subsection(source,'### 守恒','### 输出取值')
    assert updated.index('![图5]')<updated.index('图6') and Counter(source.encode())==Counter(updated.encode())
    assert '\r\n' in updated and 'T=33.5765' in updated and proof['characters_unchanged']==len(source)
    assert source[proof['source_start']:proof['source_end']] in updated


def test_only_known_later_subsection_can_move():
    with pytest.raises(WorkflowError):move_subsection('### A\ntext\n### B\ntext\n','### A','### B')
    with pytest.raises(WorkflowError):move_subsection('### A\ntext\n','### Missing','### A')


def test_conflicting_plan_is_rejected_before_draft_generation():
    catalog={'figures':[{'id':'fig5','formal':True},{'id':'fig6','formal':True}]}
    plan={'sections':['求解','结果','检验'],'figure_plan':[{'figure_id':'fig5','section':'检验'},{'figure_id':'fig6','section':'结果'}]}
    with pytest.raises(WorkflowError,match='conflicts'):validate_plan_order(plan,catalog)
    plan['figure_plan'][0]['section']='求解';validate_plan_order(plan,catalog)

def test_prepared_publish_never_bypasses_w1_or_resets_user_decisions(tmp_path,monkeypatch):
    from modelcrew import hand_runtime as hr
    from modelcrew.writing_layout_repair import publish_prepared
    monkeypatch.setattr(hr,'run_folder',lambda row:tmp_path)
    row={'phase':'DRAFT','payload':{'prepared_writer_draft':{'attempt':4},'attempt':4,'reviews':{},'accepted_reviews':{}}}
    with pytest.raises(WorkflowError,match='independent W1'):publish_prepared(None,row)
    row['phase']='WAITING_MANUSCRIPT_AND_FIGURES';row['payload']['manuscript_review']={'decision':'approve'}
    with pytest.raises(WorkflowError,match='Preserve existing'):publish_prepared(None,row)
    assert row['payload']['manuscript_review']=={'decision':'approve'}
