import json
from pathlib import Path
import pytest
from modelcrew.repository_migration import snapshot, backup, verify, resolve_historical, relative_path


def test_backup_move_restore_and_detect_tampering(tmp_path):
    old = tmp_path / 'old'
    old.mkdir()
    (old / 'receipt.json').write_bytes(b'{"approved":true}\r\n')
    manifest = snapshot(tmp_path, 'old', 'archive/old', 'synthetic historical preservation')
    backup_dir = backup(tmp_path, manifest, 'tmp/backup')
    assert (backup_dir / 'old/receipt.json').read_bytes() == (old / 'receipt.json').read_bytes()
    assert json.loads((backup_dir / 'manifest.json').read_text()) == manifest
    (tmp_path / 'archive').mkdir()
    old.rename(tmp_path / 'archive/old')
    assert verify(tmp_path, manifest, 'new_path') == 1
    path = resolve_historical(tmp_path, 'old/receipt.json', [manifest])
    assert path.read_bytes() == b'{"approved":true}\r\n'
    path.write_text('tampered')
    with pytest.raises(ValueError, match='changed'):
        resolve_historical(tmp_path, 'old/receipt.json', [manifest])


def test_reject_conflicting_mapping_and_source(tmp_path):
    (tmp_path / 'source').write_text('a')
    manifest = snapshot(tmp_path, 'source', 'target', 'test')
    with pytest.raises(ValueError, match='coexist'):
        resolve_historical(tmp_path, 'source', [manifest])
    with pytest.raises(ValueError, match='Conflicting'):
        resolve_historical(tmp_path, 'source', [manifest, manifest])
    (tmp_path / 'target').write_text('b')
    with pytest.raises(FileExistsError):
        snapshot(tmp_path, 'source', 'target', 'test')


@pytest.mark.parametrize('name', ['../escape', 'C:/escape', '/escape', 'a\\b', '.', ''])
def test_unsafe_migration_paths(tmp_path, name):
    with pytest.raises(ValueError):
        relative_path(tmp_path, name)


def test_overlap_and_backup_overwrite_rejected(tmp_path):
    (tmp_path / 'original').mkdir()
    (tmp_path / 'original/file').write_text('x')
    with pytest.raises(ValueError, match='Overlapping'):
        snapshot(tmp_path, 'original', 'original/inside', 'test')
    manifest = snapshot(tmp_path, 'original', 'new', 'test')
    backup(tmp_path, manifest, 'tmp/backup')
    with pytest.raises(FileExistsError):
        backup(tmp_path, manifest, 'tmp/backup')


def test_changed_source_prevents_backup(tmp_path):
    source = tmp_path / 'receipt'
    source.write_text('approved')
    manifest = snapshot(tmp_path, 'receipt', 'archive/receipt', 'test')
    source.write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        backup(tmp_path, manifest, 'tmp/backup')
    assert not (tmp_path / 'tmp/backup').exists()


def test_registered_resolution_preserves_old_identity(tmp_path):
    from modelcrew.repository_migration import resolve_repository_path
    (tmp_path/'original').write_bytes(b'old approved bytes')
    manifest=snapshot(tmp_path,'original','archive/original','test')
    (tmp_path/'archive').mkdir()
    (tmp_path/'original').rename(tmp_path/'archive/original')
    (tmp_path/'configs').mkdir()
    (tmp_path/'configs/record.json').write_text(json.dumps(manifest),encoding='utf-8')
    (tmp_path/'configs/repository-layout.json').write_text(
        json.dumps({'relocation_records':['configs/record.json']}),encoding='utf-8')
    assert resolve_repository_path(tmp_path,'original').read_bytes() == b'old approved bytes'
    assert resolve_repository_path(tmp_path,'unmapped') == tmp_path/'unmapped'


def test_actual_registered_relocations_preserve_original_bytes():
    from scripts.verify_repository_relocations import check
    result=check(Path(__file__).resolve().parents[1])
    assert result['records'] >= 4
    assert result['verified_files'] >= 130
    assert result['database_recovery_verified'] is False


def test_chained_relocation_preserves_original_identity_and_rejects_cycles(tmp_path):
    from modelcrew.repository_migration import sha256
    (tmp_path/'new').write_bytes(b'original bytes')
    expected=sha256(tmp_path/'new')
    records=[{'files':[{'old_path':'old','new_path':'middle','sha256':expected}]},
             {'files':[{'old_path':'middle','new_path':'new','sha256':expected}]}]
    assert resolve_historical(tmp_path,'old',records)==tmp_path/'new'
    records[1]['files'][0]['new_path']='old'
    with pytest.raises(ValueError,match='Cyclic'):
        resolve_historical(tmp_path,'old',records)
    records[1]['files'][0]['sha256']='0'*64
    with pytest.raises(ValueError,match='changes file identity'):
        resolve_historical(tmp_path,'old',records)


def test_declared_source_revision_preserves_old_object_without_replacing_current(tmp_path):
    import hashlib
    original=b'original source bytes'
    expected=hashlib.sha256(original).hexdigest()
    (tmp_path/'src').mkdir();(tmp_path/'src/module.py').write_bytes(b'current revised source')
    (tmp_path/'archive').mkdir();(tmp_path/'archive/original.py').write_bytes(original)
    (tmp_path/'configs').mkdir()
    version={'files':[{'path':'src/module.py','sha256':expected,'snapshot':'archive/original.py','bytes':len(original)}]}
    (tmp_path/'configs/versions.json').write_text(json.dumps(version),encoding='utf-8')
    (tmp_path/'configs/repository-layout.json').write_text(json.dumps({'revision_records':['configs/versions.json']}),encoding='utf-8')
    mappings=[{'files':[{'old_path':'old/module.py','new_path':'src/module.py','sha256':expected}]}]
    assert resolve_historical(tmp_path,'old/module.py',mappings)==tmp_path/'archive/original.py'
    assert resolve_historical(tmp_path,'src/module.py',mappings)==tmp_path/'src/module.py'
    (tmp_path/'archive/original.py').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='snapshot changed'):
        resolve_historical(tmp_path,'old/module.py',mappings)
