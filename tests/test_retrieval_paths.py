from pathlib import Path
import json
import pytest
from modelcrew.retrieval_paths import algorithm_config_path,algorithm_catalog_path
from modelcrew.config import ROOT


def test_defaults_are_function_named_and_respect_data_root(tmp_path,monkeypatch):
    monkeypatch.delenv('MODELCREW_ALGORITHM_CONFIG',raising=False)
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    assert algorithm_config_path(tmp_path)==tmp_path/'runs/algorithm-retrieval/index.json'
    assert algorithm_catalog_path(tmp_path)==tmp_path/'runs/algorithm-retrieval/catalog.json'
    monkeypatch.setenv('MODELCREW_DATA_DIR','local-runs')
    assert algorithm_config_path(tmp_path)==tmp_path/'local-runs/algorithm-retrieval/index.json'


def test_explicit_and_environment_config_priority(tmp_path,monkeypatch):
    monkeypatch.setenv('MODELCREW_ALGORITHM_CONFIG','environment.json')
    assert algorithm_config_path(tmp_path)==tmp_path/'environment.json'
    assert algorithm_config_path(tmp_path,'explicit.json')==tmp_path/'explicit.json'
    # Missing configured files stay missing: no implicit fallback to a stage directory.
    assert not algorithm_config_path(tmp_path).exists()
    with pytest.raises(ValueError):
        algorithm_catalog_path(tmp_path,'../outside.json')


def test_existing_config_and_catalog_keep_historical_identity():
    from modelcrew.algorithm_retrieval import verify_sources
    catalog=algorithm_catalog_path(ROOT)
    assert algorithm_catalog_path(ROOT,'stage-c-plus/algorithm-catalog.json')==catalog
    historical=algorithm_config_path(ROOT,'stage-c-plus/runs/algorithm-index.json')
    assert 'archive' in historical.parts
    old=json.loads(historical.read_text(encoding='utf-8'))
    new=json.loads(algorithm_config_path(ROOT).read_text(encoding='utf-8'))
    assert old['catalog_path'] != new['catalog_path']
    assert {k:v for k,v in old.items() if k!='catalog_path'} == {k:v for k,v in new.items() if k!='catalog_path'}
    assert algorithm_catalog_path(ROOT,old['catalog_path']) == algorithm_catalog_path(ROOT,new['catalog_path'])
    value=json.loads(catalog.read_text(encoding='utf-8'))
    # New knowledge editions may invalidate a frozen index. Never rewrite its identity.
    import hashlib
    from modelcrew.project_assets import asset_path
    from modelcrew.retrieval import RetrievalUnavailable
    current=hashlib.sha256(asset_path(ROOT,'resources/algorithms/index.md').read_bytes()).hexdigest()
    if current != value['index']['sha256']:
        with pytest.raises(RetrievalUnavailable,match='rebuild catalog'): verify_sources(value)
    else:
        verify_sources(value)


def test_paper_config_precedence_data_root_and_historical_alias(tmp_path,monkeypatch):
    from modelcrew.retrieval_paths import paper_config_path
    monkeypatch.delenv('MODELCREW_RETRIEVAL_CONFIG',raising=False)
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    assert paper_config_path(tmp_path)==tmp_path/'runs/paper-retrieval/index.json'
    monkeypatch.setenv('MODELCREW_DATA_DIR','custom-runs')
    assert paper_config_path(tmp_path)==tmp_path/'custom-runs/paper-retrieval/index.json'
    monkeypatch.setenv('MODELCREW_RETRIEVAL_CONFIG','environment.json')
    assert paper_config_path(tmp_path)==tmp_path/'environment.json'
    assert paper_config_path(tmp_path,'explicit.json')==tmp_path/'explicit.json'
    assert not paper_config_path(tmp_path).exists()
    monkeypatch.delenv('MODELCREW_RETRIEVAL_CONFIG')
    monkeypatch.delenv('MODELCREW_DATA_DIR')
    assert paper_config_path(ROOT,'stage-c/runs/retrieval-index.json')==paper_config_path(ROOT)


def test_paper_missing_default_never_loads_model(tmp_path,monkeypatch):
    import modelcrew.retrieval as retrieval
    monkeypatch.setattr(retrieval,'ROOT',tmp_path)
    monkeypatch.delenv('MODELCREW_RETRIEVAL_CONFIG',raising=False)
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    def forbidden(*args,**kwargs):
        pytest.fail('Missing configuration must fail before loading an embedding model')
    monkeypatch.setattr(retrieval,'LocalBge',forbidden)
    with pytest.raises(retrieval.RetrievalUnavailable,match='configuration unavailable'):
        retrieval.from_config()


def test_paper_index_existing_config_fails_before_model_or_index_mutation(tmp_path,monkeypatch):
    import sys
    import modelcrew.retrieval as retrieval
    monkeypatch.setattr(retrieval,'ROOT',tmp_path)
    monkeypatch.delenv('MODELCREW_RETRIEVAL_CONFIG',raising=False)
    monkeypatch.delenv('MODELCREW_DATA_DIR',raising=False)
    config=tmp_path/'runs/paper-retrieval/index.json'
    config.parent.mkdir(parents=True)
    config.write_text('preserved original configuration',encoding='utf-8')
    monkeypatch.setattr(sys,'argv',['retrieval','index',str(tmp_path/'absent-corpus.json'),'--model','absent-model'])
    with pytest.raises(FileExistsError,match='choose a new output version'):
        retrieval.main()
    assert config.read_text(encoding='utf-8')=='preserved original configuration'
