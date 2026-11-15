"""Unsafe upstream archives must fail closed during source/notice review."""
import io
import tarfile
import zipfile

import pytest
from scripts.prepare_release_source_evidence import inspect_source, safe_name


@pytest.mark.parametrize('name', ['../LICENSE', '/LICENSE', r'..\LICENSE', 'C:/LICENSE'])
def test_source_notice_rejects_escape_paths(name):
    with pytest.raises(ValueError, match='Unsafe archive member'):
        safe_name(name)


def test_notice_inventory_never_follows_source_symlinks(tmp_path):
    source = tmp_path/'upstream.tar.gz'
    data = b'Original component license\n'
    with tarfile.open(source, 'w:gz') as archive:
        info = tarfile.TarInfo('project/licenses/vendor.txt')
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo('project/LICENSE-symlink')
        link.type = tarfile.SYMTYPE
        link.linkname = '/outside-secret'
        archive.addfile(link)
    with zipfile.ZipFile(tmp_path/'notices.zip', 'w') as notices:
        result = inspect_source(source, notices, 'source')
    with zipfile.ZipFile(tmp_path/'notices.zip') as notices:
        assert notices.namelist() == ['source/project/licenses/vendor.txt']
        assert notices.read(notices.namelist()[0]) == data
    assert result['notice_count'] == 1
    assert not (tmp_path/'project').exists()


def test_source_notice_rejects_oversized_member_before_reading(tmp_path):
    source = tmp_path/'upstream.tar'
    with tarfile.open(source, 'w') as archive:
        info = tarfile.TarInfo('project/LICENSE')
        info.size = 8*1024*1024+1
        archive.addfile(info, io.BytesIO(b'x'*info.size))
    with zipfile.ZipFile(tmp_path/'notices.zip', 'w') as notices:
        with pytest.raises(ValueError, match='bounded inspection size'):
            inspect_source(source, notices, 'source')
