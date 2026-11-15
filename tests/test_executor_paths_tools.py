import json
from pathlib import Path
import pytest
from modelcrew.config import ROOT
from modelcrew.execution_paths import execution_directory
from modelcrew.tool_discovery import discover_tool,tex_cache_directory,ToolUnavailable
from modelcrew.docker_executor import DockerExecutor


def test_executor_default_and_explicit_priority(tmp_path,monkeypatch):
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    monkeypatch.delenv('MODELCREW_EXECUTION_ROOT',raising=False)
    assert execution_directory(tmp_path)==tmp_path/'runs/execution'
    monkeypatch.setenv('MODELCREW_DATA_DIR','custom-data')
    assert execution_directory(tmp_path)==tmp_path/'custom-data/execution'
    monkeypatch.setenv('MODELCREW_EXECUTION_ROOT','configured-execution')
    assert execution_directory(tmp_path)==tmp_path/'configured-execution'
    assert execution_directory(tmp_path,'explicit')==tmp_path/'explicit'


def test_executor_registered_legacy_root_rejects_conflict(tmp_path):
    (tmp_path/'configs').mkdir()
    (tmp_path/'mapping.json').write_text(json.dumps({'source':'stage-c/execution','target':'runs/execution','files':[]}),encoding='utf-8')
    (tmp_path/'configs/repository-layout.json').write_text(json.dumps({'relocation_records':['mapping.json']}),encoding='utf-8')
    assert execution_directory(tmp_path,'stage-c/execution')==tmp_path/'runs/execution'
    (tmp_path/'stage-c/execution').mkdir(parents=True)
    with pytest.raises(ValueError,match='Conflicting'):
        execution_directory(tmp_path,'stage-c/execution')


def test_all_original_jobs_and_receipts_recover_without_docker(monkeypatch):
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    monkeypatch.delenv('MODELCREW_EXECUTION_ROOT',raising=False)
    def forbidden(*args,**kwargs):pytest.fail('Completed historical jobs must not invoke Docker or redispatch')
    monkeypatch.setattr(DockerExecutor,'docker',forbidden)
    current=DockerExecutor();old=DockerExecutor(ROOT/'stage-c/execution')
    assert old.root==current.root==ROOT/'runs/execution'
    manifest=json.loads((ROOT/'docs/migrations/execution-data-20261111.json').read_text(encoding='utf-8'))
    results=[i for i in manifest['files'] if Path(i['old_path']).name=='result.json' and Path(i['old_path']).parent.parent.as_posix()=='stage-c/execution/runs']
    assert len(results)==53
    for item in results:
        path=ROOT/item['new_path'];original=json.loads(path.read_text(encoding='utf-8'))
        assert current.status(path.parent.name)==old.status(path.parent.name)==original


def test_tools_explicit_environment_path_and_local_precedence(tmp_path,monkeypatch):
    import modelcrew.tool_discovery as tools
    paths=[tmp_path/name for name in ['explicit.exe','environment.exe','path.exe','configs/local/tools/pandoc/pandoc.exe']]
    for p in paths:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'synthetic test placeholder, never executed')
    monkeypatch.setenv('MODELCREW_PANDOC',str(paths[1]))
    monkeypatch.setattr(tools.shutil,'which',lambda name:str(paths[2]))
    assert discover_tool('pandoc',paths[0],root=tmp_path)==paths[0]
    assert discover_tool('pandoc',root=tmp_path)==paths[1]
    monkeypatch.delenv('MODELCREW_PANDOC')
    assert discover_tool('pandoc',root=tmp_path)==paths[2]
    monkeypatch.setattr(tools.shutil,'which',lambda name:None)
    assert discover_tool('pandoc',root=tmp_path)==paths[3]
    with pytest.raises(ToolUnavailable,match='missing'):
        discover_tool('pandoc',tmp_path/'missing.exe',root=tmp_path)
    with pytest.raises(ValueError):discover_tool('unsupported',root=tmp_path)


def test_legacy_tool_files_and_cache_defaults(monkeypatch):
    monkeypatch.delenv('TECTONIC_CACHE_DIR',raising=False)
    assert tex_cache_directory(ROOT)==ROOT/'configs/local/tex-cache'
    monkeypatch.setenv('TECTONIC_CACHE_DIR','custom-cache')
    assert tex_cache_directory(ROOT)==ROOT/'custom-cache'
    assert discover_tool('pandoc',ROOT/'stage-c-plus/tools/pandoc/pandoc.exe')==ROOT/'configs/local/tools/pandoc/pandoc.exe'
    assert discover_tool('tectonic',ROOT/'stage-c-plus/tools/tectonic.exe')==ROOT/'configs/local/tools/tectonic.exe'
