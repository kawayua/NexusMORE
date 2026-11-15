"""Stable workspace data paths with bounded legacy lookup for existing runs."""
from .config import configured as configuration_value
import os
from pathlib import Path
import uuid
from .repository_migration import relative_path
from .project_assets import asset_path

# Compatibility only. New runs never use these research-stage directories.
LEGACY_RUNS = {
    'hands': 'stage-d/runs/runtime',
    'modeling': 'stage-d/runs/modeling',
    'assembly-inputs': 'stage-e/runs/runtime',
    'assembly-builds': 'stage-e/builds',
}


def data_root(root):
    root = Path(root).resolve()
    configured = configuration_value('MODELCREW_DATA_DIR', root=root)
    path = Path(configured) if configured else root/'runs'
    if not path.is_absolute():
        path = root/path
    if path == root or not path.is_relative_to(root):
        raise ValueError('Data directory must stay inside the workspace')
    path = relative_path(root,path.relative_to(root).as_posix(), strict_root=False)
    # Artifacts retain workspace-relative identities. Select a different workspace
    # to place all user data on another drive; data_dir stays inside it.
    if path == root or not path.is_relative_to(root):
        raise ValueError('Data directory must be a dedicated directory inside the current workspace')
    top = path.relative_to(root).parts[0]
    if top in {'modelcrew','src','docs','configs','resources','contracts','migrations','scripts','tests','archive','execution'} or top.startswith('stage-'):
        raise ValueError('Data directory must not be inside code, resources, or historical evidence')
    return path


def run_directory(root, kind, run_id, *, new=False):
    if kind not in LEGACY_RUNS:
        raise ValueError('Unknown runtime directory kind')
    identifier = str(uuid.UUID(str(run_id)))
    root = Path(root).resolve()
    current = data_root(root)/kind/identifier
    legacy = asset_path(root,LEGACY_RUNS[kind]+'/'+identifier)
    for path in (current, legacy):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Runtime directory must not be a link')
        if not path.resolve().is_relative_to(root):
            raise ValueError('Runtime directory escapes workspace')
    if current != legacy and current.exists() and legacy.exists():
        raise ValueError('Conflicting current and historical runtime directories')
    if new:
        if current.exists() or legacy.exists():
            raise FileExistsError('Runtime identity already has a directory')
        return current
    return legacy if legacy.exists() else current
