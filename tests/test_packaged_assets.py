import json
from pathlib import Path
import pytest
from modelcrew.config import ROOT
from modelcrew.project_assets import asset_path
from modelcrew.package_resources import resource,verify_resources
from modelcrew.repository_migration import resolve_repository_path,resolve_repository_location


def test_runtime_resources_are_complete_and_private_inputs_are_excluded():
    checked=verify_resources()
    assert checked['status']=='passed' and checked['files']>=167
    assert asset_path(ROOT,'contracts/model-contract-1.1.0.schema.json').is_file()
    assert len(list(asset_path(ROOT,'migrations').glob('*.sql')))==15
    assert asset_path(ROOT,'execution/sandbox_runner.py').is_file()
    for name in ['paper/reference/main.tex','algorithms/reference/assets']:
        with pytest.raises(FileNotFoundError):resource(name)


def test_historical_uuid_runtime_aliases_are_distinct_from_original_objects():
    policy=json.loads((ROOT/'configs/repository-layout.json').read_text(encoding='utf-8'))
    assert len(policy['runtime_aliases'])==4
    for alias in policy['runtime_aliases']:
        key=alias['ids'][0]
        logical=alias['old_prefix']+'/'+key
        current=asset_path(ROOT,logical)
        frozen=resolve_repository_location(ROOT,logical)
        assert current==ROOT/alias['current_prefix']/key
        assert frozen.is_relative_to(ROOT/'archive') and frozen!=current
        assert current.is_dir() and frozen.is_dir()


def test_asset_locator_rejects_escape_and_does_not_forge_missing_local_references(tmp_path):
    with pytest.raises(ValueError):asset_path(tmp_path,'../outside')
    assert not asset_path(tmp_path,'stage-d/missing.json').exists()
    local=tmp_path/'resources/paper/workflow.json';local.parent.mkdir(parents=True);local.write_text('{}',encoding='utf-8')
    assert asset_path(tmp_path,'resources/paper/workflow.json')==local


def test_longest_registered_directory_mapping_preserves_nested_reference_scope(tmp_path):
    (tmp_path/'configs').mkdir()
    records=[{'source':'old','target':'archive/all','files':[]},
             {'source':'old/private','target':'archive/private','files':[]}]
    for i,record in enumerate(records):(tmp_path/f'record{i}.json').write_text(json.dumps(record),encoding='utf-8')
    (tmp_path/'configs/repository-layout.json').write_text(json.dumps({'relocation_records':['record0.json','record1.json']}),encoding='utf-8')
    assert resolve_repository_location(tmp_path,'old/private/nested')==tmp_path/'archive/private/nested'
    (tmp_path/'old').mkdir()
    with pytest.raises(ValueError):resolve_repository_location(tmp_path,'old/file')


def test_archived_external_node_link_cannot_be_traversed():
    record=json.loads((ROOT/'docs/migrations/stage-d-archive-20261111.json').read_text(encoding='utf-8'))
    assert len(record['links'])==1 and record['links'][0]['traversed'] is False
    with pytest.raises(ValueError,match='links'):
        resolve_repository_location(ROOT,record['links'][0]['new_path']+'/anything')
