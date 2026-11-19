"""Install the version-specific local DSH adapter without rewriting user settings.

Uses a marked, append-only Cordis insertion and hash-checked rollback. This is
operator configuration, never an MCP tool or a source of user decisions.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

BEGIN = b'# BEGIN NEXUSMORE WORKFLOW MCP v1'
END = b'# END NEXUSMORE WORKFLOW MCP v1'
PLUGIN_ID = 'nexusmore-workflow'
SERVER_NAME = 'nexusmore'
HOST_FILES = ('package.json', 'nexusmore-dsh.mjs', 'nexusmore-dsh-decisions.mjs', 'nexusmore-dsh-conversation.mjs', 'nexusmore-dsh-client.js')

def host_resource_hashes():
    root = Path(__file__).parent/'resources/harness'
    return {name: sha256((root/name).read_bytes()) for name in HOST_FILES}



class DshConfigurationError(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _plain_file(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise DshConfigurationError('Configuration paths must not traverse links')
    return path


def _parse(raw):
    import yaml  # Optional operator-only `dsh` extra; never evaluate !!js.
    class UniqueLoader(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if isinstance(key, bool):
                key = 'true' if key else 'false'
            elif isinstance(key, int):
                key = str(key)
            if not isinstance(key, str) or key in result:
                raise DshConfigurationError('Duplicate or unsupported YAML key')
            result[key] = loader.construct_object(value_node, deep=deep)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        if len(raw) > 4 * 1024 * 1024:
            raise DshConfigurationError('DSH patch exceeds supported size')
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(raw)):
            raise DshConfigurationError('YAML aliases require manual configuration')
        rows = yaml.load(raw.decode('utf-8-sig'), Loader=UniqueLoader)
    except (UnicodeError, yaml.YAMLError) as exc:
        raise DshConfigurationError('Unsupported or malformed patch YAML; no configuration written') from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise DshConfigurationError('DSH patch must be a list of literal mappings')
    return rows


def configuration(python, workspace):
    from .config import workspace_path
    root = workspace_path(workspace)
    executable = _plain_file(python).resolve()
    if not executable.is_file() or not root.is_dir():
        raise DshConfigurationError('Python executable and existing workspace are required')
    dashboard = Path(__file__).parent/'resources/harness/nexusmore-dsh.mjs'
    if any(not dashboard.with_name(name).is_file() for name in HOST_FILES):
        raise DshConfigurationError('Packaged DSH host resources are missing')
    entry = {'id': PLUGIN_ID, 'name': '@deepseek-ai/dsh-mcp-client', 'config': {
        'transport': 'stdio', 'serverName': SERVER_NAME,
        'command': str(executable), 'args': ['-m', 'modelcrew.workflow_mcp'],
        'cwd': str(root), 'env': {'MODELCREW_WORKSPACE': str(root), 'PYTHONIOENCODING': 'utf-8'},
        'toolCallTimeoutMs': 900000, 'failOnStartupError': False}}
    panel = {'id': 'nexusmore-connection-panel', 'name': dashboard.resolve().as_uri()}
    return {'insert': [entry, panel]}


def render_block(config):
    return BEGIN + b'\n- ' + json.dumps(config, ensure_ascii=True, separators=(',', ':')).encode('utf-8') + b'\n' + END + b'\n'


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def merge_patch(original, config):
    rows = _parse(original)
    block = render_block(config)
    if BEGIN in original or END in original:
        if original.count(BEGIN) != 1 or original.count(END) != 1 or block not in original:
            raise DshConfigurationError('Managed DSH block differs; inspect before changing it')
        remainder = original.replace(block, b'', 1)
        # Keep an otherwise empty patch a valid YAML list for the ownership check.
        candidates = _parse(remainder) if _has_content(remainder) else []
        _reject_conflicts(candidates)
        return original
    _reject_conflicts(rows)
    text = original.decode('utf-8-sig')
    content = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not rows:
        if content != ['[]']:
            raise DshConfigurationError('Unsupported empty YAML layout')
        # Preserve comments and surrounding bytes; only remove the literal [] line.
        lines = original.splitlines(keepends=True)
        prefix = b''.join(line for line in lines if line.strip() != b'[]')
    else:
        if not content or not content[0].startswith('- '):
            raise DshConfigurationError('Existing patch must use a block list; convert manually')
        prefix = original
    result = prefix + (b'' if not prefix or prefix.endswith(b'\n') else b'\n') + block
    parsed = _parse(result)
    if parsed != rows + [config]:
        raise DshConfigurationError('Appending would alter existing YAML semantics')
    return result


def _has_content(raw):
    return any(line.strip() and not line.lstrip().startswith(b'#') for line in raw.splitlines())


def _reject_conflicts(rows):
    for value in _walk(rows):
        if value.get('id') in (PLUGIN_ID, 'nexusmore-connection-panel') or value.get('serverName') == SERVER_NAME:
            raise DshConfigurationError('An existing NexusMORE registration conflicts with this adapter')


def _atomic(path, data):
    fd, name = tempfile.mkstemp(prefix='.nexusmore-', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def _profile_lock(profile):
    # DSH 0.2.2-rc.1 coordinates through exclusive creation of this PID file,
    # not an OS advisory lock. Do not steal or truncate an existing lock.
    path = _plain_file(profile/'package.json.lock')
    record = (str(os.getpid())+'\n').encode('ascii')
    try:
        stream = path.open('xb')
    except FileExistsError as exc:
        raise DshConfigurationError('DSH profile is busy; existing writer lock retained') from exc
    try:
        with stream:
            stream.write(record)
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        if path.exists() and path.read_bytes() == record:
            path.unlink()


def install(profile, python, workspace):
    profile = _plain_file(profile)
    patch = _plain_file(profile/'cordis.patch.yml')
    if not profile.is_dir() or not (profile/'package.json').is_file():
        raise DshConfigurationError('An existing DSH profile is required')
    config = configuration(python, workspace)
    # Probe only imports/version, without a model call, service setup or secret output.
    probe = subprocess.run([str(Path(python).resolve()), '-c',
        'import sys,json,modelcrew.workflow_mcp; from modelcrew.dsh_decisions import adapter_sha256; from modelcrew.dsh_integration import host_resource_hashes; assert sys.version_info[:2] == (3,13); print(json.dumps({"adapter_sha256":adapter_sha256(),"host_resources":host_resource_hashes()}))'],
        cwd=workspace, env={**os.environ, 'MODELCREW_WORKSPACE': str(Path(workspace).resolve())},
        capture_output=True, timeout=30, check=False)
    if probe.returncode:
        raise DshConfigurationError('Selected Python cannot import the workflow MCP on Python 3.13')
    try:
        identity = json.loads(probe.stdout)
        expected = sha256((Path(__file__).parent/'resources/harness/nexusmore-dsh-decisions.mjs').read_bytes())
        if identity.get('adapter_sha256') != expected or identity.get('host_resources') != host_resource_hashes(): raise ValueError('mismatch')
    except (ValueError, TypeError, AttributeError):
        raise DshConfigurationError('Selected Python and host resources differ; install the same package version') from None
    with _profile_lock(profile):
        existed = patch.exists()
        original = patch.read_bytes() if existed else b'[]\n'
        updated = merge_patch(original, config)
        if updated == original:
            return {'status': 'already_configured', 'patch_sha256': sha256(original), 'restart_required': False,
                    'host_connection_verified': False}
        backup_dir = _plain_file(profile/'nexusmore-backups')
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        backup = backup_dir/(stamp+'.patch.bak')
        receipt = backup_dir/(stamp+'.json')
        with backup.open('xb') as stream:
            stream.write(original)
        record = {'schema_version': '1.0.0', 'patch': str(patch), 'backup': str(backup),
                  'existed': existed, 'before_sha256': sha256(original), 'after_sha256': sha256(updated)}
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2)
        if (patch.read_bytes() if patch.exists() else b'[]\n') != original:
            raise DshConfigurationError('DSH configuration changed during installation')
        _atomic(patch, updated)
        if patch.read_bytes() != updated:
            raise DshConfigurationError('DSH patch read-back did not match')
    return {'status': 'configured', 'patch': str(patch), 'receipt': str(receipt),
            'patch_sha256': sha256(updated), 'existing_prefix_unchanged': updated.startswith(original),
            'restart_required': True, 'host_connection_verified': False}


def rollback(receipt_path):
    receipt_path = _plain_file(receipt_path)
    record = json.loads(receipt_path.read_text(encoding='utf-8'))
    patch, backup = _plain_file(record['patch']), _plain_file(record['backup'])
    if patch.name != 'cordis.patch.yml' or backup.parent != patch.parent/'nexusmore-backups' or receipt_path.parent != backup.parent:
        raise DshConfigurationError('Rollback receipt is outside its profile')
    with _profile_lock(patch.parent):
        original = backup.read_bytes()
        current = patch.read_bytes()
        if sha256(original) != record['before_sha256'] or sha256(current) != record['after_sha256']:
            raise DshConfigurationError('Configuration or backup changed; automatic rollback refused')
        if record['existed']:
            _atomic(patch, original)
            if patch.read_bytes() != original:
                raise DshConfigurationError('Rollback verification failed')
        else:
            patch.unlink()
    return {'status': 'rolled_back', 'restart_required': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('render', 'install'):
        item = sub.add_parser(command)
        item.add_argument('--python', default=sys.executable, type=Path)
        item.add_argument('--workspace', required=True, type=Path)
        if command == 'install':
            item.add_argument('--profile', required=True, type=Path)
    item = sub.add_parser('rollback')
    item.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'render':
            print(render_block(configuration(args.python, args.workspace)).decode('utf-8'), end='')
            return
        result = rollback(args.receipt) if args.command == 'rollback' else install(args.profile, args.python, args.workspace)
        print(json.dumps(result, ensure_ascii=False))
    except (DshConfigurationError, OSError, ValueError, ImportError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'error', 'type': type(exc).__name__,
                          'message': str(exc) if isinstance(exc, DshConfigurationError) else 'Local DSH configuration failed; no credentials logged'}), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
