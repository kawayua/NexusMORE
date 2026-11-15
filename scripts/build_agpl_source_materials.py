"""Prepare version-bound AGPL source materials without publishing or claiming complete clearance."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile
from scripts.build_distribution import ROOT,audit_wheel

LOCKS = {
    'pymupdf': ('pymupdf-1.27.2.3.tar.gz', '7a92faa25129e8bbec5e50eeb9214f187665428c31b05c4ef6e36c58c0b1c6d2'),
    'mupdf': ('mupdf-1.27.2-source.tar.gz', '553867b135303dc4c25ab67c5f234d8e900a0e36e66e8484d99adc05fe1e8737'),
}

def identity(path):
    path=Path(path)
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'filename':path.name,'sha256':digest,'bytes':path.stat().st_size}


def prepare(build,pymupdf_source,mupdf_source,output):
    build=Path(build).resolve();output=Path(output).resolve()
    audit=json.loads((build/'build-audit.json').read_text(encoding='utf-8'))
    wheel=Path(audit['wheel']['path']);sdist=Path(audit['sdist']['path'])
    if audit['status']!='passed' or identity(wheel)['sha256']!=audit['wheel']['sha256'] or identity(sdist)['sha256']!=audit['sdist']['sha256']:
        raise ValueError('Frozen build identity mismatch')
    audit_wheel(wheel)
    inputs={'project':sdist,'pymupdf':Path(pymupdf_source),'mupdf':Path(mupdf_source)}
    for kind,(name,digest) in LOCKS.items():
        if inputs[kind].name!=name or identity(inputs[kind])['sha256']!=digest:
            raise ValueError('Fixed source identity mismatch: '+kind)
    # Inspect without extracting or executing any upstream source.
    for kind,path in inputs.items():
        with tarfile.open(path) as archive:
            entries=archive.getmembers()
            for entry in entries:
                name=Path(entry.name.replace('\\','/'))
                if name.is_absolute() or '..' in name.parts or ':' in entry.name:
                    raise ValueError('Unsafe source member')
            if not any(entry.name.endswith('/COPYING' if kind!='project' else '/LICENSE') for entry in entries):
                raise ValueError('Source license absent: '+kind)
    output.mkdir(parents=True,exist_ok=False)
    manifest={'schema_version':'1.0.0','distribution':'nexusmore','version':'0.1.0.dev0',
        'combined_license':'AGPL-3.0-only','runtime_wheel':identity(wheel),
        'source_archives':{kind:identity(path) for kind,path in inputs.items()},
        'origins':{'pymupdf':'PyPI 1.27.2.3 source release; verified PyPI SHA256',
            'mupdf':'https://mupdf.com/downloads/archive/mupdf-1.27.2-source.tar.gz; official HTTPS project hash, separate upstream digest not verified'},
        'native_binary_rebuild_verified':False,'complete_corresponding_source_verified':False,
        'public_release_cleared':False,'source_access_publication':'not published; attach equivalent free source access alongside this exact runtime before public distribution',
        'excluded':'No user data, credentials, native binaries, weights, caches or historical approval archives.'}
    readme='''# AGPL source materials — private review candidate

This bundle is bound to the runtime wheel hash in SOURCE_MANIFEST.json.
It contains the NexusMORE sdist, PyMuPDF 1.27.2.3 source release and MuPDF
1.27.2 official source release, plus complete AGPL/retained Apache notices.
The project sdist contains its pyproject, packaged runtime sources/resources,
MANIFEST.in and the build_distribution/build_environment_bundle scripts.

For the Python package, use the pinned supported CPython 3.13 environment
and the declared setuptools build backend. Building the project sdist does
not build PyMuPDF's native dependencies. See the exact upstream setup.py,
pipcl.py and wdev.py inside the PyMuPDF archive for native build options.
Its default build downloads MuPDF 1.27.2; PYMUPDF_SETUP_MUPDF_BUILD may point
to an explicitly prepared source directory. Preserve upstream Makefile,
Makerules, thirdparty sources and their licenses from the MuPDF archive.
Windows native compilation requires the appropriate MSVC/SWIG and other
upstream build prerequisites; this bundle does not install or claim to have
validated those tools or reproduce the official native wheel.

Do not execute unreviewed upstream scripts merely to inspect this bundle.
No native rebuild, exact upstream-wheel build mapping, all-component license
clearance or remote source endpoint is claimed. Remaining F5 work must be
resolved before calling this complete Corresponding Source. Do not distribute
only a binary with an unsupported claim that this audit has cleared it.

For AGPL 6(d), offer the matching verified complete Corresponding Source
with equivalent free access and clear directions adjacent to the actual
binary download, and preserve availability. For covered remote deployments,
provide the applicable running-version source access notice before deployment.
There is no published URL or written source offer in this private candidate.
User papers, secrets and business data are not software source inputs.
'''
    archive=output/'nexusmore-0.1.0.dev0-agpl-source-materials.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as package:
        for kind,path in inputs.items():package.write(path,'sources/'+path.name)
        for name,path in [('LICENSE',ROOT/'LICENSE'),('Apache-2.0.txt',ROOT/'docs/licenses/Apache-2.0.txt'),('THIRD_PARTY_NOTICES.md',ROOT/'THIRD_PARTY_NOTICES.md'),('combined-distribution-license.md',ROOT/'docs/combined-distribution-license.md')]:
            package.write(path,'licenses/'+name)
        package.writestr('SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        package.writestr('BUILD_AND_SOURCE_ACCESS.md',readme)
    with zipfile.ZipFile(archive) as package:
        for path in inputs.values():
            with package.open('sources/'+path.name) as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=identity(path)['sha256']:
                    raise ValueError('Bundled source changed')
    result={'status':'source_materials_identity_verified_not_complete_clearance','archive':identity(archive),'manifest':manifest}
    (output/'source-materials-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['build','pymupdf-source','mupdf-source','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=prepare(args.build,args.pymupdf_source,args.mupdf_source,args.output)
    print(json.dumps({'status':result['status'],'archive':result['archive']}))
