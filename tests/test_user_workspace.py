import copy
import json
from pathlib import Path
import os
import subprocess
import sys
import pytest
from modelcrew import config
from modelcrew.user_workspace import initialize, configuration_summary, doctor
from modelcrew.runtime_paths import data_root


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for key in list(os.environ):
        if key.startswith('MODELCREW_') or key=='TECTONIC_CACHE_DIR': monkeypatch.delenv(key)


def settings(root, **sections):
    path=root/'configs/local/settings.json';path.parent.mkdir(parents=True,exist_ok=True)
    value={'schema_version':'1.0.0',**sections};path.write_text(json.dumps(value),encoding='utf-8')
    return path


def test_init_is_idempotent_preserves_credentials_and_history(tmp_path):
    first=initialize(tmp_path)
    secret=tmp_path/'configs/local/secrets.env';secret.write_text('MODELCREW_LLM_API_KEY=FAKE_SECRET',encoding='utf-8')
    historical=tmp_path/'old-approval.json';historical.write_bytes(b'original bytes')
    second=initialize(tmp_path)
    assert len(first['created'])==4 and second['created']==[]
    assert secret.read_text()=='MODELCREW_LLM_API_KEY=FAKE_SECRET'
    assert historical.read_bytes()==b'original bytes'
    assert not first['services_started'] and not first['model_called']


def test_init_missing_root(tmp_path):
    root=tmp_path/'new'/'nested';initialize(root)
    assert (root/'runs').is_dir()


def test_unified_settings_reach_existing_consumers(tmp_path,monkeypatch):
    settings(tmp_path, paths={'data_dir':'private-data'}, execution={'root':'private-data/exec','image':'test:chosen'},
             retrieval={'paper_config':'paper.json','algorithm_config':'algo.json'},
             export={'pandoc':'tools/pandoc.exe','tex_cache':'private-cache'},
             model={'name':'chosen','base_url':'https://example.invalid/v1','api_key_env':'PRIVATE_MODEL_KEY'})
    monkeypatch.setenv('PRIVATE_MODEL_KEY','FAKE_SECRET')
    assert data_root(tmp_path)==tmp_path/'private-data'
    from modelcrew.execution_paths import execution_directory
    from modelcrew.retrieval_paths import paper_config_path,algorithm_config_path
    assert execution_directory(tmp_path)==tmp_path/'private-data/exec'
    assert paper_config_path(tmp_path)==tmp_path/'paper.json'
    assert algorithm_config_path(tmp_path)==tmp_path/'algo.json'
    assert paper_config_path(tmp_path,'explicit.json')==tmp_path/'explicit.json'
    assert config.model_environment(tmp_path)['MODELCREW_LLM_API_KEY']=='FAKE_SECRET'
    monkeypatch.setenv('MODELCREW_DATA_DIR','environment')
    assert data_root(tmp_path)==tmp_path/'environment'
    from modelcrew.tool_discovery import discover_tool,tex_cache_directory
    tool=tmp_path/'tools/pandoc.exe';tool.parent.mkdir();tool.write_bytes(b'fake')
    assert discover_tool('pandoc',root=tmp_path)==tool
    assert tex_cache_directory(tmp_path)==tmp_path/'private-cache'


@pytest.mark.parametrize('section',[{'schema_version':'future'},{'unknown':{}},{'model':{'api_key':'FAKE_SECRET'}},
    {'model':{'w2_response_format':'guess'}},{'paths':{'data_dir':''}}, {'execution':{'image':''}}])
def test_invalid_configuration_never_echoes_values_or_falls_back(tmp_path,section):
    path=settings(tmp_path);raw={'schema_version':'1.0.0',**section};path.write_text(json.dumps(raw))
    with pytest.raises(ValueError) as error: config.load_settings(tmp_path)
    assert 'FAKE_SECRET' not in str(error.value)
    assert not (tmp_path/'runs').exists()


def test_duplicate_fields_rejected(tmp_path):
    path=settings(tmp_path);path.write_text('{"schema_version":"1.0.0","model":{},"model":{}}')
    with pytest.raises(ValueError):config.load_settings(tmp_path)


def test_explicit_missing_settings_no_fallback(tmp_path,monkeypatch):
    settings(tmp_path);monkeypatch.setenv('MODELCREW_CONFIG','absent.json')
    with pytest.raises(RuntimeError,match='missing'): config.load_settings(tmp_path)


@pytest.mark.parametrize('value',['..','.','src/private','configs/local','C:/Windows'])
def test_data_directory_rejects_escape_and_code(tmp_path,value):
    settings(tmp_path,paths={'data_dir':value})
    with pytest.raises(ValueError):data_root(tmp_path)


def test_summary_and_doctor_redact_all_sensitive_fields(tmp_path,monkeypatch):
    initialize(tmp_path)
    settings(tmp_path,model={'base_url':'https://user:FAKE_SECRET@example.invalid/?token=FAKE_SECRET','name':'FAKE_SECRET'})
    monkeypatch.setenv('MODELCREW_LLM_API_KEY','FAKE_SECRET')
    monkeypatch.setenv('MODELCREW_DATABASE_URL','postgresql://user:FAKE_SECRET@localhost/db')
    monkeypatch.setattr(config,'ROOT',tmp_path)
    text=json.dumps(configuration_summary(tmp_path))+json.dumps(doctor(tmp_path,profile='workflow'))
    assert 'FAKE_SECRET' not in text
    assert not doctor(tmp_path)['model_called']


def test_empty_explicit_setting_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('MODELCREW_DATA_DIR','')
    with pytest.raises(ValueError,match='empty'):data_root(tmp_path)


def test_no_implicit_provider_or_model(tmp_path):
    initialize(tmp_path);env=config.model_environment(tmp_path)
    assert not env.get('MODELCREW_LLM_MODEL') and not env.get('MODELCREW_LLM_BASE_URL')


def test_secret_precedence_and_legacy_read_only(tmp_path,monkeypatch):
    initialize(tmp_path)
    legacy=tmp_path/'.env';legacy.write_text('MODELCREW_LLM_API_KEY=OLD\nMODELCREW_LLM_MODEL=legacy')
    secret=tmp_path/'configs/local/secrets.env';secret.write_text('MODELCREW_LLM_API_KEY=NEW')
    assert config.model_environment(tmp_path)['MODELCREW_LLM_API_KEY']=='NEW'
    monkeypatch.setenv('MODELCREW_LLM_API_KEY','ENV')
    assert config.model_environment(tmp_path)['MODELCREW_LLM_API_KEY']=='ENV'
    assert legacy.read_text().endswith('legacy')


def test_installer_directory_forbidden(monkeypatch):
    with pytest.raises(ValueError):config.workspace_path(Path(sys.prefix)/'user-data')
    with pytest.raises(ValueError):config.workspace_path(Path(config.__file__).parent/'runs')


def test_cli_applies_workspace_before_business_imports(tmp_path):
    run=subprocess.run([sys.executable,'-m','modelcrew','--workspace',str(tmp_path),'init'],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)['workspace']==str(tmp_path.resolve())
    run=subprocess.run([sys.executable,'-m','modelcrew','--workspace',str(tmp_path),'doctor'],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)['status']=='passed'


def test_doctor_uninitialized_is_read_only(tmp_path):
    root=tmp_path/'absent'
    result=doctor(root)
    assert result['status']=='incomplete' and not root.exists()


def test_link_directory_rejected_when_supported(tmp_path):
    target=tmp_path/'target';target.mkdir();link=tmp_path/'link'
    try:link.symlink_to(target,target_is_directory=True)
    except OSError:pytest.skip('OS does not permit unprivileged symbolic links')
    with pytest.raises(ValueError):initialize(link)
    root=tmp_path/'workspace';root.mkdir();(root/'runs').symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError):initialize(root)


def test_database_configured_alias_and_precedence(tmp_path,monkeypatch):
    initialize(tmp_path);settings(tmp_path,database={'url_env':'PRIVATE_DB_URL'})
    (tmp_path/'configs/local/secrets.env').write_text('PRIVATE_DB_URL=postgresql://LOCAL_FAKE')
    assert config.database_url(tmp_path)=='postgresql://LOCAL_FAKE'
    monkeypatch.setenv('PRIVATE_DB_URL','postgresql://ENV_FAKE')
    assert config.database_url(tmp_path)=='postgresql://ENV_FAKE'
    monkeypatch.setenv('PRIVATE_DB_URL','')
    with pytest.raises(RuntimeError):config.database_url(tmp_path)


def test_invalid_environment_does_not_override_valid_file_silently(tmp_path,monkeypatch):
    settings(tmp_path,model={'w2_response_format':'json_object'})
    monkeypatch.setenv('MODELCREW_W2_RESPONSE_FORMAT','invalid')
    with pytest.raises(ValueError,match='environment'):config.model_environment(tmp_path)


def test_docker_image_uses_unified_setting_but_explicit_argument_wins(tmp_path,monkeypatch):
    settings(tmp_path,execution={'image':'chosen:test'})
    monkeypatch.setattr(config,'ROOT',tmp_path)
    from modelcrew import docker_executor
    monkeypatch.setattr(docker_executor,'ROOT',tmp_path)
    monkeypatch.setenv('MODELCREW_CONFIG',str(tmp_path/'configs/local/settings.json'))
    assert docker_executor.DockerExecutor().image=='chosen:test'
    assert docker_executor.DockerExecutor(image='historical:explicit').image=='historical:explicit'


def test_workspace_junction_rejected_before_any_files(tmp_path,monkeypatch):
    root=tmp_path/'linked'
    original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda path: path==root or original(path))
    with pytest.raises(ValueError,match='junction'):initialize(root)
    assert not root.exists()


def test_nested_data_junction_rejected(tmp_path,monkeypatch):
    settings(tmp_path,paths={'data_dir':'linked/runs'})
    original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda path: path==tmp_path/'linked' or original(path))
    with pytest.raises(ValueError,match='links'):initialize(tmp_path)
    assert not (tmp_path/'runs').exists()


def test_missing_custom_key_never_falls_back_to_other_credentials(tmp_path,monkeypatch):
    initialize(tmp_path);settings(tmp_path,model={'api_key_env':'ABSENT_PROVIDER_KEY'})
    monkeypatch.setenv('MODELCREW_LLM_API_KEY','OTHER_PROVIDER_FAKE')
    assert config.model_environment(tmp_path)['MODELCREW_LLM_API_KEY']==''


def test_docker_permission_failure_is_not_reported_as_engine_stopped(tmp_path,monkeypatch):
    initialize(tmp_path)
    import modelcrew.user_workspace as workspace
    monkeypatch.setattr(workspace.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a,1,'','permission denied FAKE_SECRET'))
    result=doctor(tmp_path,profile='workflow',services=True)
    check=next(row for row in result['checks'] if row['name']=='docker_linux')
    assert check['failure_category']=='permission_denied'
    assert 'permissions' in check['action'] and 'FAKE_SECRET' not in json.dumps(result)
