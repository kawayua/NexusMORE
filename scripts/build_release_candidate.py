"""Prepare a private content-identified candidate; never publish or clear licenses."""
import argparse
from collections import deque
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import sysconfig
import tarfile
import tomllib
import zipfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from scripts.audit_release_licensing import audit as license_inventory
from scripts.build_distribution import build, audit_sdist

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'configs/release-candidate-policy.json'
SECRET_PATTERNS = {
    'private-key-header': re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'),
    'provider-token': re.compile(r'(?<![A-Za-z0-9])(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})(?![A-Za-z0-9])'),
}
LOCAL_PATH = re.compile(r'(?i)(?:[a-z]:[\\/]+(?:users|big-third-up)[\\/]+[^\s"<>`]+|/(?:Users|home)/[^/\s]+)')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(path):
    path = Path(path)
    return {'filename': path.name, 'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size}


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def safe_member(name):
    if not name or name.startswith('/') or ':' in name or chr(92) in name or any(p in {'', '.', '..'} for p in name.rstrip('/').split('/')):
        raise ValueError('unsafe archive member name')
    return '/'.join(PurePosixPath(name).parts)


def scan_text(name, data):
    hits, review = [], []
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return hits, [{'member': name, 'rule': 'non_utf8_content_requires_review'}]
    for rule, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            hits.append({'member': name, 'rule': rule, 'line': text.count('\n', 0, match.start())+1,
                         'match_sha256': sha(match.group().encode())})
    for match in LOCAL_PATH.finditer(text):
        review.append({'member': name, 'rule': 'machine_path_requires_review',
                       'line': text.count('\n', 0, match.start())+1, 'match_sha256': sha(match.group().encode())})
    return hits, review


def scan_archive(path, policy):
    """Inspect deliverable bytes; findings never contain matched secret text."""
    path = Path(path)
    hard, review, count, total, seen = [], [], 0, 0, set()
    def inspect(name, size, regular, reader, strip_prefix=False, directory=False):
        nonlocal count, total
        count += 1
        if count > policy['max_archive_members']:
            raise ValueError('archive member bound exceeded')
        try:
            canonical = safe_member(name)
        except ValueError:
            hard.append({'member_sha256': sha(name.encode()), 'rule': 'unsafe_member_name'})
            return
        if canonical in seen:
            hard.append({'member': canonical, 'rule': 'duplicate_member'})
            return
        seen.add(canonical)
        relative = canonical.split('/', 1)[1] if strip_prefix and '/' in canonical else canonical
        if directory:
            if not regular:
                hard.append({'member': canonical, 'rule': 'link_or_special_member'})
            return
        if not regular:
            hard.append({'member': canonical, 'rule': 'link_or_special_member'})
            return
        total += size
        if size > policy['max_member_bytes'] or total > policy['max_total_bytes']:
            raise ValueError('archive byte bound exceeded')
        leaf = PurePosixPath(relative).name.lower()
        if (any(relative.lower() == p.lower() or relative.lower().startswith(p.lower()+'/') for p in policy['forbidden_roots'])
                or (leaf.startswith('.env') and leaf != '.env.example') or leaf in {'secrets.env', 'database.env'}
                or PurePosixPath(relative).suffix.lower() in policy['forbidden_suffixes']):
            hard.append({'member': canonical, 'rule': 'private_or_binary_member'})
        hits, pending = scan_text(canonical, reader())
        hard.extend(hits)
        review.extend(pending)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                mode = (entry.external_attr >> 16) & 0o170000
                inspect(entry.filename, entry.file_size, (mode in {0, 0o100000} or (mode == 0o040000 and entry.is_dir())),
                        lambda e=entry: archive.read(e), directory=entry.is_dir())
    else:
        with tarfile.open(path) as archive:
            for entry in archive:
                inspect(entry.name, entry.size, entry.isfile() or entry.isdir(), lambda e=entry: archive.extractfile(e).read(),
                        strip_prefix=True, directory=entry.isdir())
    return {'artifact': identity(path), 'members': count, 'uncompressed_bytes': total,
            'status': 'blocked' if hard else 'review_required' if review else 'no_rule_matches',
            'hard_findings': hard, 'review_findings': review,
            'scope': 'Bounded member/type and heuristic text scan; not exhaustive privacy clearance.'}


def dependency_inventory(project, extras):
    """Read installed metadata closure without importing dependency code."""
    selected = list(project['dependencies'])
    for extra in extras:
        selected += project['optional-dependencies'][extra]
    queue = deque((raw, 'nexusmore', {''}) for raw in selected)
    packages, edges, expanded, missing, mismatches = {}, set(), set(), set(), set()
    environment = default_environment()
    while queue:
        raw, parent, active_extras = queue.popleft()
        requirement = Requirement(raw)
        if requirement.marker and not any(requirement.marker.evaluate({**environment, 'extra': e}) for e in active_extras):
            continue
        name = canonicalize_name(requirement.name)
        edges.add((parent, name, str(requirement)))
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.add(name)
            continue
        if requirement.url or (requirement.specifier and not requirement.specifier.contains(dist.version, prereleases=True)):
            mismatches.add((name, str(requirement), dist.version))
        requested = frozenset(requirement.extras | {''})
        state = (name, requested)
        meta = dist.metadata
        packages[name] = {'name': meta['Name'], 'version': dist.version,
                          'license_expression': meta.get('License-Expression'),
                          'license_classifiers': [v for v in meta.get_all('Classifier', []) if v.startswith('License ::')],
                          'requested_extras': sorted(set(packages.get(name, {}).get('requested_extras', [])) | set(requirement.extras))}
        if state in expanded:
            continue
        expanded.add(state)
        for child in dist.requires or []:
            queue.append((child, name, requested))
    return {'schema_version': '1.0.0', 'scope': 'Installed selected-extra metadata snapshot; not an independent resolution or hash-locked installation.',
            'selected_extras': extras, 'platform': platform.system(), 'machine': platform.machine(), 'python': platform.python_version(),
            'packages': [packages[n] for n in sorted(packages)],
            'edges': [{'parent': p, 'dependency': d, 'requirement': r} for p, d, r in sorted(edges)],
            'missing': sorted(missing), 'version_or_origin_mismatches': [list(x) for x in sorted(mismatches)],
            'status': 'matched_installed_metadata' if not missing and not mismatches else 'missing_or_mismatched',
            'reproducible_installation_claimed': False}



def installed_license_inventory(dependencies):
    """Inventory the actual metadata locations selected by this interpreter, including user-site."""
    active = {}
    for row in dependencies['packages']:
        name = canonicalize_name(row['name'])
        dist = metadata.distribution(name)
        active[name] = {'site': Path(dist.locate_file('')).resolve(), 'version': row['version']}
    sites = sorted({v['site'] for v in active.values()}) or [Path(sysconfig.get_path('purelib')).resolve()]
    selected, first = {}, None
    for site in sites:
        result = license_inventory(site)
        if first is None:
            first = result
        for row in result['dependencies']:
            name = canonicalize_name(row['name'])
            chosen = active.get(name)
            if chosen and chosen['site'] == site and chosen['version'] == row['version']:
                selected[name] = row
    first.pop('source_runtime_site_packages', None)
    first['scope'] = 'License metadata and notice identities for installed members of the selected dependency closure; not legal or native-source clearance.'
    first['source_runtime_sites'] = [{'path_sha256': sha(str(site).encode())} for site in sites]
    first['dependencies'] = [selected[name] for name in sorted(selected)]
    first['dependency_count'] = len(selected)
    first['missing_selected_license_entries'] = sorted(set(active)-set(selected))
    first['declared_but_uninstalled'] = dependencies['missing']
    return first


def prepare(output):
    output = Path(output).resolve()
    allowed = (ROOT/'runs/release-candidates').resolve()
    if output == allowed or not output.is_relative_to(allowed):
        raise ValueError('candidate output must be a new child of runs/release-candidates')
    output.mkdir(parents=True, exist_ok=False)
    policy = json.loads((ROOT/POLICY).read_text(encoding='utf-8'))
    if policy['schema_version'] != '1.0.0' or policy['public_release_approved'] is not False:
        raise ValueError('unsupported or self-authorizing candidate policy')
    for ref in policy['preserved_records']:
        if sha((ROOT/ref['path']).read_bytes()) != ref['sha256']:
            raise ValueError('preserved record identity changed')
    project = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    built = build(output/'distribution')
    audit_sdist(Path(built['sdist']['path']))
    artifacts = [Path(built[key]['path']) for key in ['wheel', 'sdist', 'wheel_from_sdist']]
    scans = [scan_archive(path, policy) for path in artifacts]
    write(output/'archive-scan.json', {'scope': 'Actual wheel, source tar and rebuilt wheel', 'artifacts': scans})
    deps = dependency_inventory(project, policy['dependency_extras'])
    write(output/'dependency-inventory.json', deps)
    with (output/'installed-constraints-win-py313.txt').open('x', encoding='utf-8') as stream:
        stream.write('# Installed metadata snapshot only; not a complete hash-locked installation.\n')
        for row in deps['packages']:
            stream.write(row['name']+'=='+row['version']+'\n')
    license_data = installed_license_inventory(deps)
    write(output/'license-inventory.json', license_data)
    with tarfile.open(artifacts[1]) as archive:
        source_files = [{'member': entry.name.split('/', 1)[1], 'sha256': sha(archive.extractfile(entry).read()), 'bytes': entry.size}
                        for entry in archive if entry.isfile()]
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    canonical = json.dumps(source_files, sort_keys=True, separators=(',', ':')).encode()
    write(output/'source-identity.json', {'git_head': head, 'scope': 'Exact sdist members including generated metadata; editable worktree identity is not git HEAD alone.',
                                        'aggregate_sha256': sha(canonical), 'files': source_files})
    inherited = json.loads((ROOT/policy['open_license_gate_record']).read_text(encoding='utf-8'))
    gates = inherited['deferred_items']
    hard = sum(len(s['hard_findings']) for s in scans)
    review = sum(len(s['review_findings']) for s in scans)
    notes = f'''# 枢模 · NexusMORE 本地首发准备候选

包版本：{project['version']}；候选身份：{output.name}。本地开发候选，尚未公开发布。

wheel、源码sdist及从sdist重建wheel已按当前源码/资源身份核对。源码包携带H4当前使用与贡献入口、必要配置与合成测试源，不包含用户数据库、运行目录、论文成品、模型权重或原生工具二进制。构建使用现有setuptools与依赖，不宣称干净安装或二进制可重现。

G的本地Windows/DSH 0.2.2-rc.1实际通过范围保留；新设备/干净环境由用户在开源后实测，当前未验证。没有新增其他宿主兼容、留出求解率或机制优势结论。

归档扫描：高置信/边界问题{hard}项，人工复核匹配{review}项（各归档分别计数，不是独立缺陷数）。匹配只保存文件/行号/规则与指纹，不回显原文；无匹配也不等于完整隐私审查通过。依赖闭包状态：{deps['status']}，记录{len(deps['packages'])}个已安装发行包。constraints是当前Windows/Python元数据快照，不是带下载哈希的安装锁。

许可与对应源码事项沿用此前F5记录，仍有{len(gates)}类未关闭项目。旧第三方源码材料绑定旧运行候选，不能自动证明新候选的完整对应源码或可公开获取安排。当前保留Private元数据；工程检查不替代这些核对及人工复核。

公开推送/上传/发布需对应明确指示；本工具没有调用远程发布。完整说明见源码包中的docs/release-preparation.md。
'''
    with (output/'RELEASE_NOTES.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(notes)
    report_names = ['archive-scan.json', 'dependency-inventory.json', 'installed-constraints-win-py313.txt',
                    'license-inventory.json', 'source-identity.json', 'RELEASE_NOTES.md']
    payload = {f'artifacts/{artifacts[0].name}': artifacts[0], f'artifacts/{artifacts[1].name}': artifacts[1],
               'reports/build-audit.json': output/'distribution/build-audit.json'}
    payload.update({'reports/'+name: output/name for name in report_names})
    payload.update({'licenses/'+name: ROOT/name for name in ['LICENSE', 'THIRD_PARTY_NOTICES.md']})
    write(output/'BUNDLE_MANIFEST.json', {'files': [{'member': name, **identity(path)} for name, path in sorted(payload.items())],
                                        'public_release_cleared': False})
    bundle = None
    if not hard:
        bundle = output/f'nexusmore-{project["version"]}-{output.name}-private-candidate.zip'
        with zipfile.ZipFile(bundle, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, path in sorted(payload.items()):
                archive.write(path, name)
            archive.write(output/'BUNDLE_MANIFEST.json', 'BUNDLE_MANIFEST.json')
        with zipfile.ZipFile(bundle) as archive:
            if archive.testzip() is not None:
                raise ValueError('candidate ZIP integrity failed')
            for name, path in payload.items():
                if sha(archive.read(name)) != identity(path)['sha256']:
                    raise ValueError('candidate ZIP payload identity changed')
    result = {'schema_version': '1.0.0', 'candidate_id': output.name, 'version': project['version'],
              'status': 'private_candidate_prepared_public_release_blocked' if bundle else 'blocked_sensitive_or_boundary_findings',
              'engineering_build': built['status'], 'declared_version_unchanged': True,
              'dependency_snapshot_status': deps['status'], 'hard_scan_findings': hard, 'manual_review_findings': review,
              'open_license_gates': gates, 'preserved_records': policy['preserved_records'],
              'artifacts': [identity(path) for path in artifacts], 'bundle': identity(bundle) if bundle else None,
              'new_device_test': policy['new_device_test'], 'public_release_cleared': False,
              'public_upload_authorized': False, 'business_database_mutated': False, 'supplier_called': False,
              'matching_complete_corresponding_source_verified': False, 'source_access_url_published': False}
    write(output/'preparation-result.json', result)
    checksum_files = [*artifacts, output/'distribution/build-audit.json', output/'BUNDLE_MANIFEST.json',
                      output/'preparation-result.json', *(output/n for n in report_names)] + ([bundle] if bundle else [])
    with (output/'SHA256SUMS').open('x', encoding='utf-8', newline='\n') as stream:
        for path in sorted(checksum_files):
            stream.write(identity(path)['sha256']+'  '+path.relative_to(output).as_posix()+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.output)
    except Exception as exc:
        print(json.dumps({'status': 'preparation_failed', 'error_type': type(exc).__name__,
                          'note': 'Preserve partial output/build logs; use a new output after diagnosis.'}, ensure_ascii=False))
        raise
    print(json.dumps({k: result[k] for k in ['candidate_id', 'status', 'engineering_build', 'hard_scan_findings', 'manual_review_findings', 'bundle', 'public_release_cleared']}, ensure_ascii=False))
    return 0 if result['bundle'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
