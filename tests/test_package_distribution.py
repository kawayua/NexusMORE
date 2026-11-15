"""Private distribution boundaries and source-independent CLI regression tests."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

import pytest
from scripts.build_distribution import audit_wheel

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('source,destination',[
    ('src/harness/nexusmore-workflow.js','harness/nexusmore-workflow.js'),
    ('src/harness/package.json','harness/package.json'),
    ('scripts/render_assembly_word.ps1','rendering/render-word.ps1'),
    ('configs/executor/Dockerfile.runtime','deployment/Dockerfile.runtime'),
    ('configs/services/postgres.yaml','deployment/postgres.yaml'),
    ('configs/services/qdrant.yaml','deployment/qdrant.yaml'),
])
def test_distributed_adapter_copies_match_authoritative_sources(source,destination):
    assert (ROOT/source).read_bytes() == (ROOT/'src/modelcrew/resources'/destination).read_bytes()

def test_packaged_export_rejects_incomplete_source_even_with_complete_writing_context(tmp_path,monkeypatch):
    from modelcrew import paper_export
    source=tmp_path/'source';source.mkdir()
    (source/'单题论文-中文审阅稿.md').write_text('# 测试稿\n\n## 摘要\n工程测试。\n\n## 关键词\n测试\n\n## 问题重述\n未完成稿。',encoding='utf-8')
    (source/'user-review-confirmed.json').write_text('{}',encoding='utf-8')
    (source/'figure-catalog.json').write_text('{"question_ids":["q1"],"figures":[]}',encoding='utf-8')
    monkeypatch.setattr(paper_export,'discover_tool',lambda *args:Path(sys.executable))
    with pytest.raises(ValueError,match='Paper checks failed'):
        paper_export.build(source,tmp_path/'attempt')
    assert not (tmp_path/'attempt/paper.pdf').exists()
    assert json.loads((tmp_path/'attempt/build-error.json').read_text(encoding='utf-8'))['W2']=='NOT_RUN'

def test_cli_readonly_commands_need_no_database(monkeypatch):
    monkeypatch.delenv('MODELCREW_DATABASE_URL',raising=False)
    version=subprocess.run([sys.executable,'-m','modelcrew','--version'],capture_output=True,text=True,check=True)
    from modelcrew import __version__
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert version.stdout.strip() == 'nexusmore '+__version__ == 'nexusmore '+project['version']
    result=subprocess.run([sys.executable,'-m','modelcrew','resources-check'],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['status']=='passed'

def test_runtime_extras_do_not_require_pytest_and_declare_direct_workflow_imports():
    extras=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['optional-dependencies']
    assert all(not any(d.startswith('pytest') for d in deps) for name,deps in extras.items() if name!='dev')
    required={'pydantic','portalocker','qdrant-client','mcp','anyio','scipy','sympy','beautifulsoup4'}
    assert required <= {d.split('==')[0] for d in extras['workflow']}

@pytest.fixture
def package_wheel(tmp_path):
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    names=['modelcrew/'+p for p in project['tool']['setuptools']['package-data']['modelcrew']]
    names += ['modelcrew/'+p.name for p in (ROOT/'src/modelcrew').glob('*.py')]
    path=tmp_path/'test.whl'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n in names:z.writestr(n,(ROOT/'src'/n).read_bytes())
        metadata=chr(10).join(['Metadata-Version: 2.4','License-Expression: AGPL-3.0-only','Name: nexusmore','Version: '+project['project']['version'],'Classifier: Private :: Do Not Upload','Requires-Python: >=3.13,<3.14','',''])
        z.writestr('nexusmore-0.1.0.dev0.dist-info/METADATA',metadata)
        for filename in project['project']['license-files']:
            z.writestr('nexusmore-0.1.0.dev0.dist-info/licenses/'+filename,(ROOT/filename).read_bytes())
    return path

def test_wheel_audit_accepts_exact_runtime_allowlist(package_wheel):
    assert audit_wheel(package_wheel)['status']=='passed'

def test_wheel_audit_rejects_private_file_leak(package_wheel):
    with zipfile.ZipFile(package_wheel,'a') as z:z.writestr('configs/local/database.env','TEST_ONLY')
    with pytest.raises(ValueError,match='unexpected'):audit_wheel(package_wheel)

def test_wheel_audit_rejects_duplicate_members(package_wheel):
    with pytest.warns(UserWarning,match='Duplicate'):
        with zipfile.ZipFile(package_wheel,'a') as z:z.writestr('modelcrew/__init__.py','tampered')
    with pytest.raises(ValueError,match='Duplicate'):audit_wheel(package_wheel)

@pytest.mark.parametrize('group,required',[
    ('documents',{'python-docx','PyMuPDF','lxml','defusedxml','openpyxl','pdfplumber','pypdf'}),
    ('figures',{'matplotlib','numpy','openpyxl','Pillow','PyMuPDF','pypdf'}),
    ('evidence',{'numpy','scipy','sympy','openpyxl','pydantic'}),
    ('retrieval',{'sentence-transformers','qdrant-client','numpy','mcp','pydantic'}),
    ('paper',{'sentence-transformers','python-docx','PyMuPDF','matplotlib','pypdf'}),
])
def test_optional_group_runtime_requirements_match_install_instructions(group,required):
    deps=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['optional-dependencies'][group]
    instructions={line.strip() for line in (ROOT/'configs/dependencies'/('paper-export.txt' if group=='paper' else f'{group}.txt')).read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#')}
    assert set(deps)==instructions
    assert required <= {line.split('==')[0] for line in deps}
    assert not any(line.startswith('pytest') for line in instructions)


def test_wheel_audit_rejects_missing_project_license(package_wheel,tmp_path):
    changed=tmp_path/'no-license.whl'
    with zipfile.ZipFile(package_wheel) as source,zipfile.ZipFile(changed,'w') as output:
        for name in source.namelist():
            if not name.endswith('/licenses/LICENSE'):output.writestr(name,source.read(name))
    with pytest.raises(ValueError,match='license/notice missing'):audit_wheel(changed)


def test_offline_license_cli_without_configuration_or_services(tmp_path):
    import os
    environment={k:v for k,v in os.environ.items() if not k.startswith('MODELCREW_')}
    environment.update(MODELCREW_WORKSPACE=str(tmp_path/'absent-workspace'),PYTHONIOENCODING='utf-8')
    response=subprocess.run([sys.executable,'-m','modelcrew','license-info'],env=environment,capture_output=True,text=True,encoding='utf-8')
    assert response.returncode==0,response.stderr
    value=json.loads(response.stdout)
    assert value['distribution_license']=='AGPL-3.0-only'
    assert value['source_materials']['published_url'] is None
    assert value['public_release_cleared'] is False
    assert not (tmp_path/'absent-workspace').exists()


def test_license_text_retains_prior_apache_grant():
    from modelcrew.licensing import license_text
    assert license_text('agpl')==(ROOT/'LICENSE').read_text(encoding='utf-8')
    assert license_text('apache')==(ROOT/'docs/licenses/Apache-2.0.txt').read_text(encoding='utf-8')
