"""Package fixed private source/notice evidence; never grant release clearance."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def identity(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'filename': path.name, 'sha256': digest, 'bytes': path.stat().st_size}


def safe_name(name):
    name = name.replace('\\', '/')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name:
        raise ValueError('Unsafe archive member: ' + name)
    return name


def is_notice(name):
    parts = PurePosixPath(name).parts
    leaf = parts[-1].lower()
    return (any(term in leaf for term in ('license', 'licence', 'copying', 'copyright', 'notice'))
            or any(p.lower() in {'licenses', 'licences', 'build_licenses'} for p in parts))


def inspect_source(path, notices, destination):
    """Read regular members only; never extract or follow archive links."""
    rows = []
    indicators = set()
    total = 0
    with tarfile.open(path, 'r:*') as source:
        for member in source:
            name = safe_name(member.name)
            if not member.isfile():
                continue
            leaf = PurePosixPath(name).name
            if leaf in {'Cargo.lock', 'Cargo.toml', '.gitmodules', 'CMakeLists.txt', 'pyproject.toml'}:
                indicators.add(leaf)
            if not is_notice(name):
                continue
            if member.size > 8 * 1024 * 1024:
                raise ValueError('Notice exceeds bounded inspection size: ' + name)
            total += member.size
            if total > 64 * 1024 * 1024:
                raise ValueError('Archive notice inventory exceeds 64 MiB')
            stream = source.extractfile(member)
            data = stream.read()
            target = destination + '/' + name
            notices.writestr(target, data)
            rows.append({'member': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    return {'notice_count': len(rows), 'notices': rows, 'build_indicators': sorted(indicators),
            'scope': 'Filename-based notice inventory; not a determination of compiled-in components or source completeness.'}


def prepare(evidence, frozen_build, mupdf, output, frozen_inputs=None):
    evidence = Path(evidence).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    audit = json.loads((Path(frozen_build)/'build-audit.json').read_text(encoding='utf-8'))
    if audit['status'] != 'passed':
        raise ValueError('Frozen project build did not pass')
    project_source = Path(audit['sdist']['path'])
    project_wheel = Path(audit['wheel']['path'])
    if frozen_inputs is not None:
        project_source = Path(frozen_inputs)/project_source.name
        project_wheel = Path(frozen_inputs)/project_wheel.name
    for key, path in [('sdist', project_source), ('wheel', project_wheel)]:
        if identity(path)['sha256'] != audit[key]['sha256']:
            raise ValueError('Frozen project identity changed')
    collected = json.loads((evidence/'collection/collection.json').read_text(encoding='utf-8'))
    graph = json.loads((evidence/'torch-build-source/collection-v3.json').read_text(encoding='utf-8'))
    inputs = []
    def add(path, expected, kind, **extra):
        path = Path(path)
        actual = identity(path)
        if expected and actual['sha256'] != expected:
            raise ValueError('Input hash mismatch: ' + path.name)
        inputs.append((path, {'kind': kind, **actual, **extra}))
    add(project_source, audit['sdist']['sha256'], 'project_source')
    for row in collected['packages']:
        if row['source_downloaded']:
            src = row['source']
            add(evidence/'collection/sources'/src['filename'], src['sha256'], 'python_sdist', package=row['name'], version=row['version'], url=src['url'])
    for row in json.loads((evidence/'native-build-inputs/sources.json').read_text(encoding='utf-8')):
        if row['name'] in {'psycopg-binary', 'pywin32'}:
            add(evidence/'native-build-inputs'/row['filename'], row['sha256'], 'fixed_repository_source', **{k:row[k] for k in ['name','repository','commit']})
    for row in graph['records']:
        add(evidence/'torch-build-source'/row['filename'], row['sha256'], 'torch_fixed_source_graph', repository=row['repository'], commit=row['commit'])
    for row in json.loads((evidence/'binary-component-sources/sources.json').read_text(encoding='utf-8')):
        if row['filename'].endswith(('.tar.gz', '.tar.bz2')):
            add(evidence/'binary-component-sources'/row['filename'], row['sha256'], 'binary_component_source', url=row['url'])
    add(mupdf, '553867b135303dc4c25ab67c5f234d8e900a0e36e66e8484d99adc05fe1e8737', 'mupdf_source')
    archive = output/'nexusmore-0.1.0.dev0-source-notice-evidence.zip'
    notice_archive = output/'component-notices.zip'
    with zipfile.ZipFile(notice_archive, 'x', compression=zipfile.ZIP_DEFLATED) as notices:
        for number, (path, row) in enumerate(inputs):
            row['archive_inspection'] = inspect_source(path, notices, f'{number:03d}-{path.name}')
    # Strict explicit evidence list: full native build logs can expose process
    # environment variables and MUST NOT be copied into a distributable packet.
    selected = ['runtime-license-inventory.json','runtime-native-config.json','wheelhouse-native-inventory.json',
        'collection/collection.json','native-build-inputs/sources.json','binary-component-sources/sources.json',
        'external-notices/sources.json','torch-build-source/collection-v3.json',
        'native-build-link-adapter.json','native-build-v10-result.json','pymupdf-build-compatibility.json',
        'pymupdf-build-compatibility.patch','native-functional-validation.json','torch-wheel-runtime-identity.json','native-build-inputs/libclang-source-metadata.json',
        'verify_native_build_v10.py','collect_torch_build_source_v3.py','validate_native_wheel.py',
        'regression-validation.json','protected-history-verification.json','frozen-inputs/recovery.json']
    evidence_files = [(evidence/name, 'evidence/'+name) for name in selected]
    for folder in ['collection/metadata', 'collection/licenses', 'external-notices']:
        evidence_files += [(p, 'evidence/'+p.relative_to(evidence).as_posix()) for p in (evidence/folder).rglob('*') if p.is_file()]
    # Include full LGPL/GPL supplemental texts fetched for binary components.
    evidence_files += [(p,'licenses/'+p.name) for p in (evidence/'binary-component-sources').iterdir() if p.is_file() and not p.name.endswith(('.json','.tar.gz','.tar.bz2'))]
    tools = ['audit_release_licensing.py','collect_release_sources.py','prepare_release_source_evidence.py']
    evidence_files += [(ROOT/'scripts'/name, 'maintenance-sources/'+name) for name in tools]
    evidence_files += [(ROOT/name,'licenses/'+name.replace('/','__')) for name in ['LICENSE','THIRD_PARTY_NOTICES.md','docs/licenses/Apache-2.0.txt','docs/combined-distribution-license.md']]
    evidence_files += [(evidence/'NATIVE_BUILD_RECIPE.md','NATIVE_BUILD_RECIPE.md'),(evidence/'SOURCE_SCOPE.md','SOURCE_SCOPE.md')]
    unique = {}
    for path, name in evidence_files:
        safe_name(name)
        if name in unique and unique[name] != path:
            raise ValueError('Archive destination collision')
        unique[name] = path
    manifest = {'schema_version':'1.0.0','status':'private_source_notice_evidence_not_complete_corresponding_source',
        'runtime_wheel': identity(project_wheel), 'source_archives':[row for _,row in inputs],
        'counts':dict(Counter(row['kind'] for _,row in inputs)),
        'torch_source_graph_complete':graph['all_discovered_submodules_acquired'],
        'notices_archive':identity(notice_archive),
        'evidence_files':[{'path':name,**identity(path)} for name,path in sorted(unique.items())],
        'all_component_rights_cleared':False,'complete_corresponding_source_verified':False,'public_release_cleared':False,
        'excluded':['raw subprocess logs and environment dumps','credentials','papers and user data','weights','fonts','native wheels and binaries','unreviewed historical archives'],
        'source_access':'Private local packet only; no public endpoint or written source offer has been published.'}
    (output/'SOURCE_EVIDENCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as bundle:
        for path,row in inputs:
            bundle.write(path,'sources/'+row['filename'],compress_type=zipfile.ZIP_STORED)
        bundle.write(notice_archive,'component-notices.zip',compress_type=zipfile.ZIP_STORED)
        bundle.write(output/'SOURCE_EVIDENCE_MANIFEST.json','SOURCE_EVIDENCE_MANIFEST.json')
        for name,path in sorted(unique.items()):
            bundle.write(path,name)
    with zipfile.ZipFile(archive) as bundle:
        for path,row in inputs:
            with bundle.open('sources/'+row['filename']) as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=row['sha256']:
                    raise ValueError('Packaged source changed')
        bad = bundle.testzip()
        if bad:
            raise ValueError('Archive integrity failure: '+bad)
    result = {'status':'private_evidence_pack_and_source_hash_verification_passed','archive':identity(archive),
        'counts':manifest['counts'],'source_archives':len(inputs),'source_notice_files':sum(row['archive_inspection']['notice_count'] for _,row in inputs),
        'complete_corresponding_source_verified':False,'public_release_cleared':False}
    (output/'source-evidence-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['evidence','frozen-build','mupdf','output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--frozen-inputs',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.evidence,args.frozen_build,args.mupdf,args.output,args.frozen_inputs)))
