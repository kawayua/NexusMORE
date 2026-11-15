from pathlib import Path

import pytest

from scripts.inventory_repository import inventory, safe_file


def test_inventory_preserves_bytes_and_records_runtime_references(tmp_path):
    source = tmp_path / 'modelcrew' / 'sample.py'
    source.parent.mkdir()
    raw = b"path = ROOT/'stage-d/runs/runtime'\r\n"
    source.write_bytes(raw)
    historical = tmp_path / 'stage-e' / 'approval.json'
    historical.parent.mkdir()
    historical.write_text('{"approved": true}', encoding='utf-8')
    result = inventory(tmp_path, ['modelcrew/sample.py', 'stage-e/approval.json'])
    assert source.read_bytes() == raw
    assert result['summary']['runtime_reference_occurrences'] == 1
    assert result['references'][0]['reference'] == 'stage-d/runs/runtime'
    assert result['files'][0]['proposed_path'] == 'src/modelcrew/sample.py'
    assert result['files'][1]['proposed_path'] is None
    assert all(f['release_decision'] == 'pending_review' for f in result['files'])
    assert not result['migration_executed']


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'D:/outside', 'a/../../outside', 'a\\file'])
def test_inventory_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        safe_file(tmp_path, name)


def test_missing_file_is_explicit(tmp_path):
    report = inventory(tmp_path, ['removed.py'])
    assert report['missing_worktree_files'] == ['removed.py']
    assert report['files'] == []


def test_package_resources_are_not_classified_as_source_code():
    from scripts.inventory_repository import classify
    role, target, required=classify('modelcrew/resources/document-tools/upstream/pdf/SKILL.md')
    assert role == 'bundled_resource_requires_manifest_review'
    assert target == 'src/modelcrew/resources/document-tools/upstream/pdf/SKILL.md'
    assert required is None


def test_src_package_resources_keep_resource_classification():
    from scripts.inventory_repository import classify
    role,target,required=classify('src/modelcrew/resources/document-tools/manifest.json')
    assert role == 'bundled_resource_requires_manifest_review'
    assert target == 'src/modelcrew/resources/document-tools/manifest.json'
