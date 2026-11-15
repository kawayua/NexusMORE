import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from modelcrew.package_resources import resource


@pytest.mark.parametrize('name', ['', '../escape', '/absolute', 'C:/absolute', 'a\\b'])
def test_invalid_resource_name(name):
    with pytest.raises(ValueError):
        resource(name)


def test_missing_resource_is_not_loaded_from_repository():
    with pytest.raises(FileNotFoundError):
        resource('missing-resource')


def test_bundle_works_outside_repository_and_from_zip(tmp_path):
    root = Path(__file__).resolve().parents[1]
    package = Path(__import__('modelcrew').__file__).resolve().parent
    archive = tmp_path / 'package.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        for name in ['__init__.py', 'document_tools.py', 'package_resources.py']:
            zipped.write(package/name, 'modelcrew/'+name)
        for path in (package/'resources/document-tools').rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                zipped.write(path, 'modelcrew/'+path.relative_to(package).as_posix())
    # -I prevents a workspace PYTHONPATH or cwd from masking missing package files.
    code = '''import sys, json
sys.path.insert(0, sys.argv[1])
from modelcrew.document_tools import verify_bundle
from modelcrew.package_resources import resource
from importlib.resources import as_file
assert verify_bundle()['files'] == 126
with as_file(resource('document-tools')) as base:
    for kind in ['docx','pdf','xlsx']:
        assert (base/'upstream'/kind/'SKILL.md').is_file()
        assert (base/'upstream'/kind/'LICENSE.txt').is_file()
print(json.dumps({'verified':126,'source':__import__('modelcrew').__file__}))
'''
    completed = subprocess.run([sys.executable, '-I', '-c', code, str(archive)], cwd=tmp_path,
                               capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert '.zip' in result['source']
    assert result['verified'] == 126
