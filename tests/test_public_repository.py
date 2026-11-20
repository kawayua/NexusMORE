"""Public boundary checks contain no real task, model or database data."""
import json
from pathlib import Path
import pytest
from scripts.check_public_repository import ROOT, check_tree, inspect_text, safe_path


def test_exported_product_tree_is_self_contained():
    report = check_tree(ROOT)
    assert report['status'] == 'passed', report['issues']
    assert report['runtime_resources'] > 0
    assert report['local_document_links'] > 0
    assert not report['private_archive_needed']
    assert not report['model_or_database_called']


@pytest.mark.parametrize('name', ['../outside','/absolute','C:/private','a/../../outside',r'a\private','.git/config','docs/release/receipt.json','docs/history/log.md','configs/local/settings.json','runs/task.json'])
def test_export_rejects_private_or_nonportable_paths(name):
    with pytest.raises(ValueError):
        safe_path(name)


def test_findings_do_not_reveal_the_matched_token():
    synthetic = 'sk-'+'x'*40
    issues=inspect_text('example.txt',synthetic.encode())
    assert issues and synthetic not in json.dumps(issues)


def test_personal_home_paths_require_review():
    synthetic='C:'+chr(92)+'Users'+chr(92)+'EXAMPLE'+chr(92)+'file'
    issues=inspect_text('example.txt',synthetic.encode())
    assert issues[0]['rule']=='personal_home_path'
    assert synthetic not in json.dumps(issues)


def test_development_dependencies_cover_http_contract_validation():
    import tomllib
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    api=[r for r in project['optional-dependencies']['retrieval'] if r.lower().startswith('fastapi==')]
    assert len(api)==1
    assert api[0] in project['optional-dependencies']['dev']


def test_approved_readme_images_are_explicitly_hash_pinned():
    from scripts.check_public_repository import inspect_member
    config=json.loads((ROOT/'configs/public-repository.json').read_text(encoding='utf-8'))
    assets=config['binary_assets']
    assert set(assets)=={'docs/assets/nexusmore-workflow-v1.png','docs/assets/algorithm-library-v1.jpg'}
    for name,spec in assets.items():
        raw=(ROOT/name).read_bytes()
        assert inspect_member(name,raw,assets)==[]
        assert inspect_member(name,raw+b'changed',assets)[0]['rule']=='binary_asset_identity'
        assert inspect_member(name,raw,{})


def test_unrelated_binary_content_is_still_rejected():
    from scripts.check_public_repository import inspect_member
    assert inspect_member('unregistered.dat',bytes([255,0,1]),{})


def test_readme_algorithm_counts_and_links_match_actual_catalog():
    catalog=json.loads((ROOT/'src/modelcrew/resources/algorithms/knowledge/catalog.json').read_text(encoding='utf-8'))
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    assert '113 种去重规范算法' in readme
    assert '123 条分类归属' in readme
    ids={aid for category in catalog['categories'] for aid in category['algorithm_ids']}
    assert len(catalog['categories'])==7 and len(ids)==113
    for algorithm in catalog['algorithms']:
        assert any('src/modelcrew/resources/'+section in readme for section in algorithm['sections'].values())
