import json
from pathlib import Path
import pytest
from modelcrew.config import ROOT
from modelcrew.retrieval_paths import reference_directory,mcp_log_directory
from modelcrew.repository_migration import resolve_repository_path
from modelcrew.web_references import ReferenceStore,make_hit,WebUnavailable


def test_reference_and_log_defaults_follow_data_root(tmp_path,monkeypatch):
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    assert reference_directory(tmp_path)==tmp_path/'runs/references'
    assert mcp_log_directory(tmp_path)==tmp_path/'runs/logs/mcp'
    monkeypatch.setenv('MODELCREW_DATA_DIR','custom-data')
    assert reference_directory(tmp_path)==tmp_path/'custom-data/references'
    assert mcp_log_directory(tmp_path)==tmp_path/'custom-data/logs/mcp'
    assert reference_directory(tmp_path,tmp_path/'explicit')==tmp_path/'explicit'


def test_all_original_references_keep_ids_citations_and_old_file_mapping(monkeypatch):
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    manifest=json.loads((ROOT/'docs/migrations/reference-archive-20261111.json').read_text(encoding='utf-8'))
    current=ReferenceStore(reference_directory(ROOT))
    historical=ReferenceStore(ROOT/'stage-c/runs/references')
    assert historical.root==current.root
    for item in manifest['files']:
        path=ROOT/item['new_path']
        original=json.loads(path.read_text(encoding='utf-8'))
        actual=current.get(path.stem)
        assert {key:value for key,value in actual.items() if key!='citation'}=={key:value for key,value in original.items() if key!='citation'}
        assert actual==historical.get(path.stem)
        assert actual['citation']['reference_id']==path.stem
        assert actual['citation']['bound_call_id']==original['bound_call_id']
        assert resolve_repository_path(ROOT,item['old_path'])==path


def test_explicit_old_reference_root_follows_registered_target_and_rejects_conflicts(tmp_path):
    folder=tmp_path/'configs';folder.mkdir()
    record=tmp_path/'mapping.json'
    record.write_text(json.dumps({'source':'stage-c/runs/references','target':'runs/references','files':[]}),encoding='utf-8')
    (folder/'repository-layout.json').write_text(json.dumps({'relocation_records':['mapping.json']}),encoding='utf-8')
    assert reference_directory(tmp_path,'stage-c/runs/references')==tmp_path/'runs/references'
    (tmp_path/'stage-c/runs/references').mkdir(parents=True)
    with pytest.raises(ValueError,match='Conflicting'):
        reference_directory(tmp_path,'stage-c/runs/references')


def test_new_reference_write_restart_and_tamper_detection(tmp_path):
    target=reference_directory(tmp_path)
    hit=make_hit({'url':'https://example.org/method','content':b'synthetic','retrieved_at':'2026-11-11T00:00:00Z'},'synthetic migration check','test','fixture',{'page':1})
    bound=ReferenceStore(target).bind(hit,'synthetic-call')
    ref=bound['citation']['reference_id']
    assert ReferenceStore(target).get(ref)['citation']==bound['citation']
    assert not (tmp_path/'stage-c').exists()
    (target/(ref+'.json')).write_text('{}',encoding='utf-8')
    with pytest.raises(WebUnavailable):ReferenceStore(target).get(ref)


def test_old_logs_resolve_to_sealed_archive():
    manifest=json.loads((ROOT/'docs/migrations/mcp-log-archive-20261111.json').read_text(encoding='utf-8'))
    assert len(manifest['files'])==82
    for item in manifest['files']:
        assert resolve_repository_path(ROOT,item['old_path'])==ROOT/item['new_path']
    assert not (ROOT/'stage-c/runs/mcp').exists()
