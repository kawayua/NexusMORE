"""Build and audit a private wheel/sdist pair without publishing anything."""
import argparse
import contextlib
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit_wheel(path):
    project = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    resource_root = ROOT/'src/modelcrew/resources'
    manifest = json.loads((resource_root/'resource-manifest.json').read_text(encoding='utf-8'))
    expected = {'modelcrew/'+p for p in project['tool']['setuptools']['package-data']['modelcrew']}
    expected |= {'modelcrew/'+p.name for p in (ROOT/'src/modelcrew').glob('*.py')}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate wheel members')
        actual = {n for n in names if '.dist-info/' not in n}
        if actual != expected:
            raise ValueError({'missing': sorted(expected-actual), 'unexpected': sorted(actual-expected)})
        for item in manifest['files']:
            data = z.read('modelcrew/resources/'+item['path'])
            if hashlib.sha256(data).hexdigest() != item['sha256'] or len(data) != item['bytes']:
                raise ValueError('Resource identity mismatch: '+item['path'])
        for name in actual:
            if z.read(name) != (ROOT/'src'/name).read_bytes():
                raise ValueError('Source identity mismatch: '+name)
        metadata = BytesParser().parsebytes(z.read(next(n for n in names if n.endswith('.dist-info/METADATA'))))
        if metadata['Name'] != 'nexusmore' or metadata['Version'] != project['project']['version']:
            raise ValueError('Unexpected package identity')
        if metadata.get('License-Expression') != 'AGPL-3.0-only':
            raise ValueError('Project license metadata missing or changed')
        license_root = next(n.rsplit('/', 1)[0] for n in names if n.endswith('.dist-info/METADATA')) + '/licenses/'
        for filename in project['project']['license-files']:
            if license_root + filename not in names or z.read(license_root + filename) != (ROOT/filename).read_bytes():
                raise ValueError('Required project license/notice missing or changed: ' + filename)
        if 'Private :: Do Not Upload' not in metadata.get_all('Classifier', []):
            raise ValueError('Private classification missing')
        return {'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size,'members':len(names),
                'resource_files':len(manifest['files']),'module_files':len(list((ROOT/'src/modelcrew').glob('*.py'))),
                'requires_python':metadata['Requires-Python'],'requires_dist':metadata.get_all('Requires-Dist',[]),
                'extras':metadata.get_all('Provides-Extra',[]),'license_expression':metadata['License-Expression'],'license_files':project['project']['license-files'],'status':'passed'}

def build(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    wheel_dir = output/'wheel'; wheel_dir.mkdir()
    sdist_dir = output/'sdist'; sdist_dir.mkdir()
    import setuptools.build_meta as backend
    with (output/'build.log').open('w',encoding='utf-8') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        whl = wheel_dir/backend.build_wheel(str(wheel_dir))
        sdist = sdist_dir/backend.build_sdist(str(sdist_dir))
    wheel_report = audit_wheel(whl)
    with tarfile.open(sdist) as t:
        names = t.getnames(); prefix = names[0].split('/')[0]+'/'
        relative = [n.removeprefix(prefix) for n in names if n != prefix[:-1]]
        forbidden = [n for n in relative if not (n in {'LICENSE','README.md','AGENTS.md','pyproject.toml','MANIFEST.in','THIRD_PARTY_NOTICES.md','PKG-INFO','setup.cfg','src','tests','docs','docs/package-installation.md','docs/user-configuration.md','docs/environment-preparation.md','docs/resource-routing.md','docs/combined-distribution-license.md','docs/licenses','docs/licenses/Apache-2.0.txt','scripts','scripts/build_distribution.py','scripts/build_environment_bundle.py','scripts/build_agpl_source_materials.py','scripts/probe_optional_dependencies.py','scripts/probe_retrieval_paper.py'} or n.startswith(('src/modelcrew/','src/nexusmore.egg-info','tests/')) or n=='src/modelcrew')]
        if forbidden:
            raise ValueError({'unexpected_sdist_members':forbidden})
        extracted=output/'sdist-source';extracted.mkdir()
        t.extractall(extracted, filter='data')
    rebuilt=output/'wheel-from-sdist';rebuilt.mkdir()
    command=[sys.executable,'-c',"import setuptools.build_meta as b,sys; b.build_wheel(sys.argv[1])",str(rebuilt)]
    with (output/'sdist-build.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,cwd=extracted/prefix[:-1],stdout=log,stderr=subprocess.STDOUT,check=True)
    rebuilt_report=audit_wheel(next(rebuilt.glob('*.whl')))
    report={'schema_version':'1.0.0','status':'passed','scope':'private development build; no public upload, full-knowledge or runtime gate acceptance',
            'build_isolation':False,'builder':'setuptools.build_meta; installed build requirements',
            'wheel':wheel_report,'sdist':{'path':str(sdist),'sha256':sha(sdist),'bytes':sdist.stat().st_size,'members':len(names),'status':'passed'},
            'wheel_from_sdist':rebuilt_report}
    with (output/'build-audit.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    os.chdir(ROOT)
    r=build(a.output)
    print(json.dumps({'status':r['status'],'wheel':r['wheel']['path'],'sdist':r['sdist']['path'],'resources':r['wheel']['resource_files']},ensure_ascii=False))
