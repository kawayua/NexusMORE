"""Release candidates must fail closed on archive identity and sensitive members."""
import io
import json
from pathlib import Path
import tarfile
import zipfile
from types import SimpleNamespace

import pytest
from scripts.build_distribution import audit_sdist
from scripts.build_release_candidate import ROOT, POLICY, dependency_inventory, safe_member, scan_archive, scan_text


@pytest.fixture
def policy():
    return json.loads((ROOT/POLICY).read_text(encoding='utf-8'))


def source_tree(root):
    (root/'configs').mkdir()
    (root/'src/modelcrew').mkdir(parents=True)
    (root/'src/modelcrew/__init__.py').write_text('VERSION = 1\n')
    (root/'README.md').write_text('Public synthetic test\n')
    (root/'pyproject.toml').write_text('[project]\nname="nexusmore"\nversion="0.1.0.dev0"\n[tool.setuptools.package-data]\nmodelcrew=[]\n')
    (root/'configs/distribution-files.json').write_text(json.dumps({'schema_version':'1.0.0', 'sdist_files':['README.md','pyproject.toml','configs/distribution-files.json']}))
    return ['README.md','pyproject.toml','configs/distribution-files.json','src/modelcrew/__init__.py']


def archive(root, names, *, altered=None, extra=None):
    target = root/'candidate.tar.gz'
    with tarfile.open(target, 'w:gz') as output:
        for name in names:
            data = b'changed\n' if name == altered else (root/name).read_bytes()
            entry = tarfile.TarInfo('nexusmore-0.1.0.dev0/'+name)
            entry.size = len(data)
            output.addfile(entry, io.BytesIO(data))
        if extra:
            output.addfile(extra)
    return target


def test_sdist_exact_inputs_are_verified(tmp_path):
    names = source_tree(tmp_path)
    assert audit_sdist(archive(tmp_path, names), root=tmp_path)['required_source_files'] == 4


def test_sdist_missing_document_is_rejected(tmp_path):
    names = source_tree(tmp_path)
    with pytest.raises(ValueError, match='missing_sdist_files'):
        audit_sdist(archive(tmp_path, names[1:]), root=tmp_path)


def test_sdist_changed_source_is_rejected(tmp_path):
    names = source_tree(tmp_path)
    with pytest.raises(ValueError, match='identity mismatch'):
        audit_sdist(archive(tmp_path, names, altered=names[-1]), root=tmp_path)


@pytest.mark.parametrize('name', ['nexusmore-0.1.0.dev0/../outside', '/outside', 'nexusmore-0.1.0.dev0/configs/local/secrets.env'])
def test_sdist_unsafe_or_nonallowlisted_member_rejected(tmp_path, name):
    names = source_tree(tmp_path)
    with pytest.raises(ValueError):
        audit_sdist(archive(tmp_path, names, extra=tarfile.TarInfo(name)), root=tmp_path)


def test_sdist_links_cannot_be_extracted(tmp_path):
    names = source_tree(tmp_path)
    link = tarfile.TarInfo('nexusmore-0.1.0.dev0/linked')
    link.type, link.linkname = tarfile.SYMTYPE, '/outside'
    with pytest.raises(ValueError, match='links and special'):
        audit_sdist(archive(tmp_path, names, extra=link), root=tmp_path)


@pytest.mark.parametrize('name', ['.env','configs/local/settings.json','.GIT/config','../outside','C:/private.key'])
def test_scan_rejects_private_or_escape_members(tmp_path, policy, name):
    path = tmp_path/'sample.zip'
    with zipfile.ZipFile(path, 'w') as output:
        output.writestr(name, 'synthetic')
    result = scan_archive(path, policy)
    assert result['status'] == 'blocked'


def test_token_findings_do_not_echo_secret():
    synthetic = 'sk-'+'a'*40
    hits, _ = scan_text('test.txt', ('key='+synthetic).encode())
    assert hits and synthetic not in json.dumps(hits)
    assert hits[0]['line'] == 1 and len(hits[0]['match_sha256']) == 64


def test_machine_paths_require_review_not_false_secret_failure():
    hits, pending = scan_text('example.txt', ('C:'+chr(92)+'Users'+chr(92)+'EXAMPLE'+chr(92)+'file').encode())
    assert not hits and pending[0]['rule'] == 'machine_path_requires_review'


def test_zip_link_disguised_as_directory_is_rejected(tmp_path, policy):
    path = tmp_path/'link.zip'
    with zipfile.ZipFile(path, 'w') as output:
        info = zipfile.ZipInfo('link/')
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        output.writestr(info, '/outside')
    assert scan_archive(path, policy)['status'] == 'blocked'


def test_archive_scan_is_bounded(tmp_path, policy):
    policy['max_member_bytes'] = 2
    path = tmp_path/'large.zip'
    with zipfile.ZipFile(path, 'w') as output:
        output.writestr('public.txt', 'too long')
    with pytest.raises(ValueError, match='byte bound'):
        scan_archive(path, policy)


def test_dependency_snapshot_reports_missing_instead_of_inventing_version(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    def absent(name):
        raise PackageNotFoundError(name)
    monkeypatch.setattr('scripts.build_release_candidate.metadata.distribution', absent)
    result = dependency_inventory({'dependencies':['missing-package==1.0'], 'optional-dependencies':{}}, [])
    assert result['missing'] == ['missing-package']
    assert result['packages'] == [] and not result['reproducible_installation_claimed']


def test_source_policy_preserves_existing_manifest_documents_and_project_licenses():
    import tomllib
    project = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    files = set(json.loads((ROOT/'configs/distribution-files.json').read_text(encoding='utf-8'))['sdist_files'])
    assert set(project['license-files']) <= files
    for line in (ROOT/'MANIFEST.in').read_text(encoding='utf-8').splitlines():
        if line.startswith('include docs/'):
            assert line.split(' ', 1)[1] in files


def test_documented_candidate_checks_include_their_script_helpers():
    import ast
    files = set(json.loads((ROOT/'configs/distribution-files.json').read_text(encoding='utf-8'))['sdist_files'])
    for name in ['test_release_candidate.py', 'test_package_distribution.py', 'test_release_source_evidence.py', 'test_public_documentation.py', 'test_repository_layout.py', 'test_evaluation_data.py']:
        tree = ast.parse((ROOT/'tests'/name).read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('scripts.'):
                assert node.module.replace('.', '/')+'.py' in files
            elif isinstance(node, ast.ImportFrom) and node.module == 'scripts':
                assert all('scripts/'+alias.name+'.py' in files for alias in node.names)


def test_current_figure_policy_origin_is_portable_and_matches_packaged_copy():
    from scripts.build_release_candidate import LOCAL_PATH
    original = ROOT/'docs/scientific-figure-contract.md'
    resource = ROOT/'src/modelcrew/resources/project-policy/scientific-figure-contract.md'
    assert original.read_bytes() == resource.read_bytes()
    assert not LOCAL_PATH.search(resource.read_text(encoding='utf-8'))


def test_source_policy_includes_all_registered_smoke_and_navigation_inputs():
    files = set(json.loads((ROOT/'configs/distribution-files.json').read_text(encoding='utf-8'))['sdist_files'])
    catalog = json.loads((ROOT/'configs/evaluation/data-catalog-1.0.0.json').read_text(encoding='utf-8'))
    assert all(asset['path'] in files for asset in catalog['public_assets'])
    assert all(case.get('path', case.get('source_reference')) in files for case in catalog['cases'])


def test_pytest_default_temp_parent_is_created_for_an_unpopulated_source_tree(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('candidate_conftest', ROOT/'tests/conftest.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = SimpleNamespace(rootpath=tmp_path/'source', option=SimpleNamespace(basetemp=None))
    module.pytest_configure(config)
    assert (config.rootpath/'tmp').is_dir()
    assert Path(config.option.basetemp).parent == config.rootpath/'tmp'


def test_license_inventory_includes_actual_user_site_without_disclosing_location(tmp_path, monkeypatch):
    from scripts import build_release_candidate as candidate
    site = tmp_path/'synthetic-user-site'
    dist = SimpleNamespace(locate_file=lambda name:site)
    monkeypatch.setattr(candidate.metadata, 'distribution', lambda name:dist)
    seen = []
    def inventory(path):
        seen.append(path)
        return {'source_runtime_site_packages':str(path), 'dependencies':[{'name':'synthetic-dependency','version':'1.0'}], 'public_release_cleared':False}
    monkeypatch.setattr(candidate, 'license_inventory', inventory)
    result = candidate.installed_license_inventory({'packages':[{'name':'synthetic-dependency','version':'1.0'}], 'missing':[]})
    assert seen == [site.resolve()]
    assert result['dependency_count'] == 1 and result['missing_selected_license_entries'] == []
    assert str(site) not in json.dumps(result)
    assert not result['public_release_cleared']
