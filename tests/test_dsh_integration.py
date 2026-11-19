"""Version-specific DSH profile safety and rollback, using synthetic profiles."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from modelcrew import dsh_integration as d


@pytest.fixture
def config(tmp_path):
    return d.configuration(Path(sys.executable), tmp_path)


@pytest.fixture
def profile(tmp_path, monkeypatch):
    path = tmp_path/'desktop'; path.mkdir()
    (path/'package.json').write_text('{"private":true}')
    (path/'cordis.patch.yml').write_bytes(b'# user settings\r\n- id: existing\r\n  config:\r\n    provider: retained\r\n')
    monkeypatch.setattr(d.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0,stdout=json.dumps({'adapter_sha256':d.sha256((Path(d.__file__).parent/'resources/harness/nexusmore-dsh-decisions.mjs').read_bytes()),'host_resources':d.host_resource_hashes()})))
    return path


def test_append_preserves_bytes_and_is_idempotent(config):
    old = b'# user settings\r\n- id: other\r\n  config: {reasoningEfforts: {false: null}}\r\n'
    result = d.merge_patch(old, config)
    assert result.startswith(old)
    assert d.merge_patch(result, config) == result
    assert d._parse(result)[-1] == config
    entry = config['insert'][0]
    assert entry['config']['args'] == ['-m','modelcrew.workflow_mcp']
    assert set(entry['config']['env']) == {'MODELCREW_WORKSPACE','PYTHONIOENCODING'}
    assert 'insert' in config and entry['config']['transport'] == 'stdio'


@pytest.mark.parametrize('old', [b'[]\n', b'# preserved\n[]\n'])
def test_empty_patch(config, old):
    result = d.merge_patch(old, config)
    assert d._parse(result) == [config]
    assert d.merge_patch(result, config) == result


@pytest.mark.parametrize('old', [
    b'- id: nexusmore-workflow\n', b'- config: {serverName: nexusmore}\n',
    b'- insert: [{id: nexusmore-connection-panel}]\n', b'- id: x\n  id: y\n',
    b'- config: !!js process.env\n', b'- config: !!python/object/apply:os.system [bad]\n',
    b'{}\n', b'[{"id":"other"}]\n', b'- config: &a {loop: *a}\n',
])
def test_conflicts_and_unhandled_yaml_fail_closed(config, old):
    with pytest.raises(d.DshConfigurationError): d.merge_patch(old, config)


def test_changed_managed_block_is_not_rewritten(config):
    current = d.merge_patch(b'[]\n', config)
    with pytest.raises(d.DshConfigurationError):
        d.merge_patch(current.replace(b'900000', b'900001'), config)


def test_managed_block_does_not_hide_an_extra_registration(config):
    current = d.merge_patch(b'[]\n', config)
    with pytest.raises(d.DshConfigurationError):
        d.merge_patch(current + b'- config: {serverName: nexusmore}\n', config)


def test_install_backup_readback_and_rollback(profile, tmp_path):
    patch = profile/'cordis.patch.yml'; original = patch.read_bytes()
    result = d.install(profile, Path(sys.executable), tmp_path)
    assert result['status'] == 'configured'
    assert result['host_connection_verified'] is False
    assert patch.read_bytes().startswith(original)
    assert not (profile/'package.json.lock').exists()
    assert d.install(profile, Path(sys.executable), tmp_path)['status'] == 'already_configured'
    record = json.loads(Path(result['receipt']).read_text())
    assert Path(record['backup']).read_bytes() == original
    assert d.rollback(result['receipt'])['status'] == 'rolled_back'
    assert patch.read_bytes() == original


def test_rollback_refuses_later_user_edits(profile, tmp_path):
    result = d.install(profile, Path(sys.executable), tmp_path)
    patch = profile/'cordis.patch.yml'; changed = patch.read_bytes()+b'# later edit\n'; patch.write_bytes(changed)
    with pytest.raises(d.DshConfigurationError): d.rollback(result['receipt'])
    assert patch.read_bytes() == changed


def test_failed_python_probe_writes_nothing(profile, tmp_path, monkeypatch):
    monkeypatch.setattr(d.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1))
    original = (profile/'cordis.patch.yml').read_bytes()
    with pytest.raises(d.DshConfigurationError): d.install(profile, Path(sys.executable), tmp_path)
    assert (profile/'cordis.patch.yml').read_bytes() == original
    assert not (profile/'nexusmore-backups').exists()


def test_existing_dsh_writer_lock_is_never_truncated(profile, tmp_path):
    lock = profile/'package.json.lock'; lock.write_bytes(b'12345\n')
    with pytest.raises(d.DshConfigurationError, match='busy'):
        d.install(profile, Path(sys.executable), tmp_path)
    assert lock.read_bytes() == b'12345\n'
    assert not (profile/'nexusmore-backups').exists()


def test_rollback_missing_original_patch(profile, tmp_path):
    patch = profile/'cordis.patch.yml'; patch.unlink()
    result = d.install(profile, Path(sys.executable), tmp_path)
    d.rollback(result['receipt'])
    assert not patch.exists()


def test_packaged_host_panel_matches_project_source():
    root = Path(__file__).resolve().parents[1]
    assert (root/'src/harness/nexusmore-dsh.mjs').read_bytes() == (root/'src/modelcrew/resources/harness/nexusmore-dsh.mjs').read_bytes()


def test_migrate_reports_applied_database_version(monkeypatch, capsys):
    from modelcrew import workflow_mcp, workflow
    class FakeWorkflow:
        def __enter__(self): self.db = self; return self
        def __exit__(self, *args): pass
        def setup(self): pass
        def execute(self, query): assert query == 'SELECT max(version) AS version FROM mc_migrations'; return self
        def fetchone(self): return {'version': 14}
    monkeypatch.setattr(workflow, 'Workflow', FakeWorkflow)
    monkeypatch.setattr(sys, 'argv', ['workflow_mcp','migrate'])
    workflow_mcp.main()
    assert json.loads(capsys.readouterr().out)['migration'] == 14


def test_native_bridge_resource_matches_project_source():
    root=Path(__file__).resolve().parents[1]
    assert (root/'src/harness/nexusmore-dsh-decisions.mjs').read_bytes()==(root/'src/modelcrew/resources/harness/nexusmore-dsh-decisions.mjs').read_bytes()


def test_incompatible_selected_backend_never_writes_profile(profile,tmp_path,monkeypatch):
    monkeypatch.setattr(d.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='{"adapter_sha256":"different"}'))
    original=(profile/'cordis.patch.yml').read_bytes()
    with pytest.raises(d.DshConfigurationError,match='same package version'):d.install(profile,Path(sys.executable),tmp_path)
    assert (profile/'cordis.patch.yml').read_bytes()==original


def test_conversation_resources_match_project_source():
    root=Path(__file__).resolve().parents[1]
    for name in d.HOST_FILES:
        assert (root/'src/harness'/name).read_bytes()==(root/'src/modelcrew/resources/harness'/name).read_bytes()
