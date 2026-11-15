"""Guarded, hash-bound repository relocation records (no approval rewriting)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil


def relative_path(root, name, *, strict_root=True):
    root = Path(root).resolve(strict=strict_root)
    parts = PurePosixPath(name)
    if not name or parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name:
        raise ValueError('Expected repository-relative POSIX path')
    candidate = root.joinpath(*parts.parts)
    if candidate == root:
        raise ValueError('Repository root is not a migration target')
    for part in [candidate, *candidate.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Migration paths must not traverse links')
    if not candidate.resolve().is_relative_to(root):
        raise ValueError('Path escapes repository')
    return candidate


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(root, source, target, purpose):
    """Prepare exact per-file identities before any filesystem mutation."""
    original = relative_path(root, source)
    destination = relative_path(root, target)
    if original == destination or original in destination.parents or destination in original.parents:
        raise ValueError('Overlapping migration paths')
    if destination.exists():
        raise FileExistsError(destination)
    paths = sorted(original.rglob('*')) if original.is_dir() else [original]
    files = []
    for path in paths:
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        relative_path(root, path.relative_to(root).as_posix())
        if not path.is_file():
            continue
        suffix = path.relative_to(original) if original.is_dir() else Path()
        files.append({'old_path': path.relative_to(root).as_posix(),
                      'new_path': (destination / suffix).relative_to(root).as_posix(),
                      'sha256': sha256(path), 'bytes': path.stat().st_size})
    if not files:
        raise ValueError('Missing or empty migration source')
    return {'schema_version': '1.0.0', 'source': source, 'target': target,
            'purpose': purpose, 'files': files, 'approval_rewritten': False}


def verify(root, manifest, location):
    if location not in {'old_path', 'new_path'}:
        raise ValueError('Unknown migration location')
    seen = set()
    for item in manifest['files']:
        if item[location].casefold() in seen:
            raise ValueError('Duplicate migration path')
        seen.add(item[location].casefold())
        path = relative_path(root, item[location])
        if sha256(path) != item['sha256'] or path.stat().st_size != item['bytes']:
            raise ValueError('Migration file identity changed: ' + item[location])
    return len(seen)


def backup(root, manifest, directory):
    """Make immutable byte copies first. Callers perform moves with native shell tools."""
    verify(root, manifest, 'old_path')
    base = relative_path(root, directory)
    if base.exists():
        raise FileExistsError(base)
    base.mkdir(parents=True)
    for item in manifest['files']:
        source = relative_path(root, item['old_path'])
        target = relative_path(root, directory + '/' + item['old_path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        if sha256(target) != item['sha256']:
            raise ValueError('Backup verification failed')
    with (base / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return base


def resolve_historical(root, name, manifests, *, file_index=None, path_resolver=None):
    """Resolve exact, hash-consistent migration chains; reject conflicts and cycles."""
    locate=path_resolver if path_resolver is not None else lambda name:relative_path(root,name)
    seen = set()
    expected = None
    current = name
    while True:
        if current in seen:
            raise ValueError('Cyclic historical path mapping')
        seen.add(current)
        original = locate(current)
        matches = file_index.get(current,[]) if file_index is not None else [item for manifest in manifests for item in manifest['files'] if item['old_path'] == current]
        if not matches:
            if expected is not None and (not original.is_file() or sha256(original) != expected):
                # A declared source revision preserves the old object separately;
                # it does not freeze or silently substitute the current source.
                policy = locate('configs/repository-layout.json')
                records = json.loads(policy.read_text(encoding='utf-8')).get('revision_records',[]) if policy.is_file() else []
                versions = [item for record in records
                            for item in json.loads(locate(record).read_text(encoding='utf-8'))['files']
                            if item['path'] == current and item['sha256'] == expected]
                if len(versions) != 1:
                    raise ValueError('Historical destination bytes changed')
                snapshot = locate(versions[0]['snapshot'])
                if sha256(snapshot) != expected or snapshot.stat().st_size != versions[0]['bytes']:
                    raise ValueError('Historical source revision snapshot changed')
                return snapshot
            return original
        if len(matches) != 1:
            raise ValueError('Conflicting historical path mappings')
        item = matches[0]
        if expected is not None and item['sha256'] != expected:
            raise ValueError('Historical mapping chain changes file identity')
        if original.exists():
            raise ValueError('Historical source and mapping coexist; explicit review required')
        expected = item['sha256']
        current = item['new_path']


def registered_records(root):
    """Load policy once per filesystem revision; mapped bytes are always rechecked."""
    root=Path(root).resolve()
    policy=relative_path(root,'configs/repository-layout.json')
    if not policy.is_file():return [],{}
    metadata=policy.stat()
    return _policy_records_cached(str(root),metadata.st_mtime_ns,metadata.st_size)


from functools import lru_cache


@lru_cache(maxsize=8)
def _policy_records_cached(root,mtime,size):
    policy=relative_path(root,'configs/repository-layout.json')
    config=json.loads(policy.read_text(encoding='utf-8'))
    signature=tuple((name,relative_path(root,name).stat().st_mtime_ns,relative_path(root,name).stat().st_size) for name in config['relocation_records'])
    return _records_cached(root,signature)


@lru_cache(maxsize=8)
def _records_cached(root,signature):
    records=[json.loads(relative_path(root,name).read_text(encoding='utf-8')) for name,_,_ in signature]
    index={}
    for record in records:
        for item in record['files']:index.setdefault(item['old_path'],[]).append(item)
    return records,index


def resolve_repository_path(root, name):
    """Resolve registered exact old file identities; never rewrite the caller's logical key."""
    records,index=registered_records(root)
    return resolve_historical(root,name,records,file_index=index)


def resolve_repository_location(root,name):
    """Resolve a directory using the longest explicitly registered source root."""
    records,index=registered_records(root)
    if name in index:return resolve_historical(root,name,records,file_index=index)
    original=relative_path(root,name)
    matches=[record for record in records if record.get('source') and
             (name==record['source'] or name.startswith(record['source']+'/'))]
    if not matches:return original
    longest=max(len(record['source']) for record in matches)
    matches=[record for record in matches if len(record['source'])==longest]
    if len(matches)!=1:raise ValueError('Conflicting historical directory mappings')
    record=matches[0]
    if relative_path(root,record['source']).exists():raise ValueError('Historical source and mapping coexist')
    suffix=name[len(record['source']):].lstrip('/')
    target=record['target']+('/'+suffix if suffix else '')
    return relative_path(root,target)
