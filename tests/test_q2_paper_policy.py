import json,copy
from pathlib import Path
import pytest
from modelcrew.modeling_paper import scoped_figure_minimum,policy,POLICY_PATH,sha

def bundle(tmp_path):
    binding={'task_id':'q2','result_revision':1};ids=[str(i) for i in range(7)]
    value={'actor':'user','user_statement':'前两图重复，其他7图通过','reason':'跨题去重','base_policy_sha256':sha(POLICY_PATH),'binding':binding,'question_ids':['q2'],'selected_figure_ids':ids,'minimum_formal':7}
    f=tmp_path/'exception.json';f.write_text(json.dumps(value),encoding='utf-8')
    catalog={'evidence':binding,'question_ids':['q2'],'figures':[{'id':i,'formal':True} for i in ids],'policy_override':{'path':f.name,'sha256':sha(f)}}
    return f,value,catalog

def test_no_exception_keeps_global_eight(tmp_path):
    assert scoped_figure_minimum(tmp_path/'cat.json',{},policy())==8

def test_explicit_bound_user_exception_seven(tmp_path):
    f,v,c=bundle(tmp_path);assert scoped_figure_minimum(tmp_path/'cat.json',c,policy())==7

def test_exception_cannot_apply_to_another_result(tmp_path):
    f,v,c=bundle(tmp_path);c['evidence']={'task_id':'q2','result_revision':2}
    with pytest.raises(ValueError,match='another result'):scoped_figure_minimum(tmp_path/'cat.json',c,policy())

def test_exception_tamper_rejected(tmp_path):
    f,v,c=bundle(tmp_path);f.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='Changed'):scoped_figure_minimum(tmp_path/'cat.json',c,policy())
