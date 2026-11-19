"""Bounded engineering quota for frozen figure contracts, not numerical acceptance."""
import pytest
from modelcrew import coder_repair as cr
from modelcrew.docker_executor import Limits


def test_thirteen_frozen_figures_fit_three_formats_without_changing_byte_or_runtime_limits(monkeypatch):
    limits=Limits(max_files=32).model_dump()
    maximum=cr.full_file_capacity(limits,13,3)
    assert maximum==44
    monkeypatch.setattr(cr,'grant',lambda row:('synthetic',{'full_max_files':maximum}))
    row={'payload':{'request':{'limits':limits}}}
    minimal=cr.execution_limits(row,False);full=cr.execution_limits(row,True)
    assert minimal==limits and full=={**limits,'max_files':44}
    assert limits['max_files']==32


def test_file_capacity_refuses_more_than_hard_bounded_quota():
    with pytest.raises(ValueError):cr.full_file_capacity(Limits(max_files=32).model_dump(),21,3)
    assert cr.full_file_capacity(Limits(max_files=32).model_dump(),0,3)==32


def test_file_count_ceiling_keeps_existing_defaults_and_rejects_65():
    assert Limits().max_files==16
    assert Limits(max_files=64).max_files==64
    with pytest.raises(ValueError):Limits(max_files=65)


def test_standing_policy_is_host_setting_not_model_payload(tmp_path,monkeypatch):
    import json
    from modelcrew import config
    monkeypatch.delenv('MODELCREW_CONFIG',raising=False)
    monkeypatch.setattr(config,'ROOT',tmp_path)
    assert cr.host_policy() is None
    path=tmp_path/'configs/local/settings.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'schema_version':'1.0.0','autonomy':{'coder_repairs':'standing','statement':'SYNTHETIC explicit user permission'}}),encoding='utf-8')
    assert cr.host_policy()['mode']=='standing'
    path.write_text(json.dumps({'schema_version':'1.0.0','autonomy':{'coder_repairs':'off'}}),encoding='utf-8')
    assert cr.host_policy() is None


def test_standing_policy_requires_explicit_statement(tmp_path,monkeypatch):
    import json
    from modelcrew import config
    from modelcrew.workflow import WorkflowError
    monkeypatch.delenv('MODELCREW_CONFIG',raising=False);monkeypatch.setattr(config,'ROOT',tmp_path)
    path=tmp_path/'configs/local/settings.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'schema_version':'1.0.0','autonomy':{'coder_repairs':'standing'}}),encoding='utf-8')
    with pytest.raises(WorkflowError,match='statement'):cr.host_policy()


def test_capabilities_report_standing_advance_without_new_model_authorization_tool(monkeypatch):
    from modelcrew.business_adapter import BusinessAdapter
    monkeypatch.setattr(cr,'host_policy',lambda:{'mode':'standing'})
    data=BusinessAdapter().capabilities()
    assert data['host_autonomy']['renewal_required'] is False
    assert data['host_autonomy']['entrypoint']=='hand_advance'
    assert 'authorize_coder_repair' not in data['operations']
