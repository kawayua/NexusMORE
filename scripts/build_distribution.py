"""Build and audit a private wheel/sdist pair without publishing anything."""
import argparse
import contextlib
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
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

def audit_sdist(path, *, root=None):
    """Validate exact source inputs before extraction; no private paths or links."""
    root = Path(root or ROOT).resolve()
    project = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))
    extra = json.loads((root/'configs/distribution-files.json').read_text(encoding='utf-8'))
    if extra['schema_version'] != '1.0.0':
        raise ValueError('Unknown source distribution policy')
    required = set(extra['sdist_files'])
    required |= {'src/modelcrew/'+p for p in project['tool']['setuptools']['package-data']['modelcrew']}
    required |= {p.relative_to(root).as_posix() for p in (root/'src/modelcrew').glob('*.py')}
    required |= {p.relative_to(root).as_posix() for p in (root/'tests').rglob('*')
                 if p.is_file() and p.suffix in {'.py', '.mjs'} and '__pycache__' not in p.parts}
    prefix = project['project']['name'].replace('-', '_')+'-'+project['project']['version']
    generated = {'PKG-INFO', 'setup.cfg'}
    generated |= {'src/nexusmore.egg-info/'+n for n in ('PKG-INFO', 'SOURCES.txt', 'dependency_links.txt',
                  'entry_points.txt', 'requires.txt', 'top_level.txt')}
    allowed_dirs = {prefix}
    for relative in required | generated:
        allowed_dirs.update(str(p) for p in PurePosixPath(prefix+'/'+relative).parents if str(p) != '.')
    found, names, total = set(), set(), 0
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        if len(members) > 10000:
            raise ValueError('Source archive exceeds member bound')
        for member in members:
            name = member.name
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != prefix or name in names or any(x in {'.', '..'} for x in name.split('/')) or ':' in name or chr(92) in name or name.startswith('/'):
                raise ValueError('Unsafe or duplicate source archive member')
            names.add(name)
            if member.isdir():
                if name.rstrip('/') not in allowed_dirs:
                    raise ValueError('Unexpected source directory: '+name)
                continue
            if not member.isfile():
                raise ValueError('Source archive links and special members are forbidden')
            relative = '/'.join(parts[1:])
            if relative not in required | generated:
                raise ValueError('Unexpected source member: '+relative)
            total += member.size
            if member.size > 16*1024*1024 or total > 128*1024*1024:
                raise ValueError('Source archive exceeds byte bound')
            if relative in required:
                source = root/relative
                resolved = source.resolve()
                if not resolved.is_relative_to(root) or source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
                    raise ValueError('Source input escapes repository')
                if archive.extractfile(member).read() != source.read_bytes():
                    raise ValueError('Source member identity mismatch: '+relative)
            found.add(relative)
    missing = sorted(required-found)
    if missing:
        raise ValueError({'missing_sdist_files': missing})
    return {'path': str(path), 'sha256': sha(Path(path)), 'bytes': Path(path).stat().st_size,
            'members': len(members), 'required_source_files': len(required), 'status': 'passed',
            'prefix': prefix, 'symlinks_or_special_members_allowed': False}


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
    sdist_report = audit_sdist(sdist)
    with tarfile.open(sdist) as t:
        prefix = sdist_report['prefix']+'/'
        extracted=output/'sdist-source';extracted.mkdir()
        t.extractall(extracted, filter='data')
    rebuilt=output/'wheel-from-sdist';rebuilt.mkdir()
    command=[sys.executable,'-c',"import setuptools.build_meta as b,sys; b.build_wheel(sys.argv[1])",str(rebuilt)]
    with (output/'sdist-build.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,cwd=extracted/prefix[:-1],stdout=log,stderr=subprocess.STDOUT,check=True)
    rebuilt_report=audit_wheel(next(rebuilt.glob('*.whl')))
    report={'schema_version':'1.0.0','status':'passed','scope':'private development build; no public upload, full-knowledge or runtime gate acceptance',
            'build_isolation':False,'builder':'setuptools.build_meta; installed build requirements',
            'wheel':wheel_report,'sdist':sdist_report,
            'wheel_from_sdist':rebuilt_report}
    with (output/'build-audit.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    os.chdir(ROOT)
    r=build(a.output)
    print(json.dumps({'status':r['status'],'wheel':r['wheel']['path'],'sdist':r['sdist']['path'],'resources':r['wheel']['resource_files']},ensure_ascii=False))
