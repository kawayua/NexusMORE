import pytest
from modelcrew import config
from scripts.start_database import compose_command


def test_database_configuration_moves_without_requiring_stage_root(tmp_path,monkeypatch):
    monkeypatch.delenv('MODELCREW_DATABASE_CONFIG',raising=False)
    monkeypatch.delenv('MODELCREW_DATABASE_URL',raising=False)
    monkeypatch.setattr(config,'ROOT',tmp_path)
    current=tmp_path/'configs/local/database.env';current.parent.mkdir(parents=True)
    current.write_text('MODELCREW_DATABASE_URL=postgresql://TEST_ONLY\n',encoding='utf-8')
    assert config.database_url()=='postgresql://TEST_ONLY'
    legacy=tmp_path/'stage-b/.env';legacy.parent.mkdir();legacy.write_text('conflict')
    with pytest.raises(RuntimeError,match='Conflicting'):
        config.database_env_file()


def test_explicit_configuration_does_not_silently_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv('MODELCREW_DATABASE_CONFIG','missing.env')
    with pytest.raises(RuntimeError,match='missing'):
        config.database_env_file(tmp_path)
    monkeypatch.setenv('MODELCREW_DATABASE_URL','postgresql://ENV_OVERRIDE')
    assert config.database_url()=='postgresql://ENV_OVERRIDE'


def test_compose_identity_preserves_existing_database_volume(tmp_path):
    command=compose_command(tmp_path,tmp_path/'configs/local/database.env',check=True)
    assert command[command.index('-p')+1]=='stage-b'
    assert command[-2:]==['config','--quiet']
    assert str(tmp_path/'configs/services/postgres.yaml') in command
    assert 'up' not in command
