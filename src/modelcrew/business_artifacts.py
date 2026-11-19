"""Owner-scoped registered artifacts and handle-bound, hash-checked byte reads."""
import base64
import ctypes
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import stat
from psycopg.types.json import Jsonb
from .contracts import digest
from .business_contract import BusinessContractError


def fail(code, message):
    raise BusinessContractError(code, message)


def checked_path(root, name):
    root = Path(root).resolve()
    raw = Path(name)
    raw = raw if raw.is_absolute() else root/raw
    try:
        raw.absolute().relative_to(root)
        for part in (raw, *raw.parents):
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                fail('artifact_access_denied', 'Linked artifact paths are forbidden')
            if part == root:
                break
        path = raw.resolve(strict=True)
        path.relative_to(root)
    except (ValueError, OSError):
        fail('artifact_access_denied', 'Artifact path is not within the registered workspace')
    return path


def read_verified(root, name, expected, *, offset=0, limit=0):
    path = checked_path(root, name)
    try:
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                fail('artifact_access_denied', 'Artifact is not a regular file')
            if os.name == 'nt':
                import msvcrt
                buffer = ctypes.create_unicode_buffer(32768)
                fn = ctypes.windll.kernel32.GetFinalPathNameByHandleW
                fn.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
                fn.restype = ctypes.c_uint32
                length = fn(msvcrt.get_osfhandle(stream.fileno()), buffer, len(buffer), 0)
                if not length or length >= len(buffer):
                    fail('artifact_access_denied', 'Cannot verify opened artifact handle')
                final = buffer.value
                if final.startswith('\\\\?\\UNC\\'):
                    final = '\\\\' + final[8:]
                elif final.startswith('\\\\?\\'):
                    final = final[4:]
                checked_path(root, final)
            elif Path('/proc/self/fd').is_dir():
                checked_path(root, os.readlink('/proc/self/fd/'+str(stream.fileno())))
            else:
                fail('artifact_access_denied', 'Handle path verification is unavailable on this platform')
            if offset > before.st_size:
                fail('invalid_request', 'Artifact offset exceeds its size')
            h = hashlib.sha256(); collected = []; position = 0
            while block := stream.read(1024 * 1024):
                h.update(block)
                left = max(offset-position, 0); right = min(offset+limit-position, len(block))
                if limit and right > left:
                    collected.append(block[left:right])
                position += len(block)
            after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or h.hexdigest() != expected:
                fail('artifact_changed', 'Registered artifact bytes have changed')
            return b''.join(collected), position
    except BusinessContractError:
        raise
    except OSError as exc:
        raise BusinessContractError('artifact_access_denied', 'Registered artifact cannot be read') from exc


class ArtifactRegistry:
    def __init__(self, w, root):
        self.w, self.db, self.root = w, w.db, Path(root).resolve()

    def register(self, owner, name, sha256, role='artifact', *, is_input=False):
        if not re.fullmatch('[0-9a-f]{64}', sha256):
            fail('artifact_changed', 'Artifact registration lacks a valid byte identity')
        path = checked_path(self.root, name)
        _, size = read_verified(self.root, path, sha256)
        relative = path.relative_to(self.root).as_posix()
        identity = {'owner': owner, 'path': relative, 'sha256': sha256}
        artifact_id = 'artifact_' + digest(identity)
        media = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        self.db.execute('INSERT INTO mc_business_artifacts(artifact_id,owner_sha256,owner,path,sha256,media_type,bytes,role,is_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                        (artifact_id, digest(owner), Jsonb(owner), relative, sha256, media, size, role, is_input))
        row = self.db.execute('SELECT * FROM mc_business_artifacts WHERE artifact_id=%s', (artifact_id,)).fetchone()
        if is_input and not row['is_input']:
            fail('artifact_access_denied', 'Output registration cannot grant input privileges')
        return self.describe(row)

    @staticmethod
    def describe(row):
        return {k: row[k] for k in ('artifact_id','owner','sha256','media_type','bytes','role')} | {'readable':True}

    def resolve_input(self, value, owner):
        if not isinstance(value, str):
            fail('artifact_access_denied', 'Expected a registered input reference')
        if value.startswith('artifact:'):
            row = self.db.execute('SELECT * FROM mc_business_artifacts WHERE artifact_id=%s AND is_input=true', (value[9:],)).fetchone()
        else:
            # Existing frozen contracts may keep a physical snapshot path, but
            # it must already have an exact input registration for this owner.
            path = checked_path(self.root, value).relative_to(self.root).as_posix()
            rows = self.db.execute('SELECT * FROM mc_business_artifacts WHERE path=%s AND is_input=true', (path,)).fetchall()
            row = next((r for r in rows if all(owner.get(k)==v for k,v in r['owner'].items())), None)
        if not row or not all(owner.get(k)==v for k,v in row['owner'].items()):
            fail('artifact_access_denied', 'Input belongs to another task, version or project')
        path = checked_path(self.root, row['path'])
        read_verified(self.root, path, row['sha256'])
        return str(path), row['sha256']

    def read(self, arguments):
        owner = arguments['owner']; self.w.require_project(owner['project_id'])
        row = self.db.execute('SELECT * FROM mc_business_artifacts WHERE artifact_id=%s AND owner_sha256=%s',
                              (arguments['artifact_id'], digest(owner))).fetchone()
        if not row:
            fail('artifact_access_denied', 'Artifact is not registered for this exact owner')
        if row['sha256'] != arguments['sha256']:
            fail('artifact_changed', 'Requested artifact identity differs from registration')
        data, total = read_verified(self.root, row['path'], row['sha256'], offset=arguments['offset'], limit=arguments['max_bytes'])
        if total != row['bytes']:
            fail('artifact_changed', 'Artifact size differs from registration')
        return {'artifact_id':row['artifact_id'],'sha256':row['sha256'],'offset':arguments['offset'],
                'bytes_returned':len(data),'total_bytes':total,'encoding':'base64',
                'content':base64.b64encode(data).decode('ascii'),'eof':arguments['offset']+len(data)==total}

    def task(self, task, version=None, run_id=None):
        t = self.w.task(task); version = t['current_version'] if version is None else version
        owner = {'project_id':t['project_id'],'task_id':task,'version':version}
        if not self.db.execute('SELECT 1 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone():
            fail('not_found', 'Unknown task version')
        if run_id:
            owner['run_id'] = run_id
        files = []
        if not run_id:
            for row in self.db.execute('SELECT artifacts FROM mc_executions WHERE task_id=%s AND version=%s',(task,version)).fetchall():
                files += row['artifacts']
            for row in self.db.execute('SELECT body FROM mc_version_entries WHERE task_id=%s AND version=%s',(task,version)).fetchall():
                files += row['body'].get('artifacts',[])
        runs = self.db.execute('SELECT id,payload FROM mc_hand_runs WHERE task_id=%s AND version=%s'+(' AND id::text=%s' if run_id else ''),
                               (task,version,run_id) if run_id else (task,version)).fetchall()
        if run_id and not runs:
            fail('not_found', 'Unknown hand run')
        result = []
        for item in files:
            result.append(self.register(owner,item['path'],item['sha256'],item.get('role','artifact')))
        for row in runs:
            run_owner = {**owner, 'run_id':str(row['id'])}
            for path, sha in row['payload'].get('sealed',{}).items():
                result.append(self.register(run_owner,path,sha))
        if not run_id:
            from .collaboration import CollaborationStore, Snapshot
            for row in self.db.execute('SELECT id,payload FROM mc_modeling_runs WHERE task_id=%s AND version=%s',(task,version)).fetchall():
                payload=row['payload']
                if not payload.get('snapshot_sha256'):
                    continue
                folder=checked_path(self.root,payload['folder'])
                store=CollaborationStore(folder/'records')
                snapshot=store.load(Snapshot,payload['snapshot_sha256'])
                if snapshot.binding.task_id!=task or snapshot.binding.contract_version!=version:
                    fail('artifact_access_denied','Modeling snapshot owner differs')
                run_owner={**owner,'run_id':str(row['id'])}
                for item in snapshot.artifacts:
                    result.append(self.register(run_owner,item.path,item.sha256,item.kind))
        for row in self.db.execute('SELECT * FROM mc_business_artifacts WHERE owner_sha256=%s',(digest(owner),)).fetchall():
            read_verified(self.root,row['path'],row['sha256'])
            result.append(self.describe(row))
        return list({r['artifact_id']:r for r in result}.values())

    def assembly(self, project, build):
        row = self.db.execute('SELECT payload FROM mc_assembly_builds WHERE project_id=%s AND id::text=%s',(project,build)).fetchone()
        if not row:
            fail('not_found', 'Unknown assembly build')
        owner={'project_id':project,'build_id':build}
        return [self.register(owner,path,sha) for path,sha in row['payload'].get('sealed',{}).items()]


def register_input(w, root, owner, source, role='input'):
    """Trusted local command only; never registered as an MCP model tool."""
    from .artifacts import snapshot_artifacts
    from .config import ROOT
    if Path(root).resolve() != ROOT.resolve():
        fail('artifact_access_denied', 'Input snapshots must use the configured workspace')
    w.require_project(owner['project_id'])
    if set(owner) != {'project_id','task_id','version'} or type(owner['version']) is not int or owner['version'] < 1:
        fail('invalid_request', 'Input registration requires a project/task/version owner')
    source = Path(source).resolve(strict=True)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    item = snapshot_artifacts([{'path':str(source),'sha256':sha,'role':role}],retain_input_type=True)[0]
    return ArtifactRegistry(w,root).register(owner,item['path'],sha,role,is_input=True)
