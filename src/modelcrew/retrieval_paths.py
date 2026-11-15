"""Legacy vector/paper storage locations; installed algorithm lookup reads package resources.

These path defaults do not select a vector backend. Explicit old paths keep exact mappings.
"""
from .config import configured
import os
from pathlib import Path
from .config import ROOT
from .runtime_paths import data_root
from .repository_migration import relative_path, resolve_repository_path


def _path(root, value, *, external=False):
    root=Path(root).resolve()
    path=Path(value).expanduser()
    if not path.is_absolute():
        path=root/path
    if not path.is_relative_to(root):
        if external:
            return path.resolve()
        raise ValueError('Algorithm catalog must be within workspace')
    name=path.relative_to(root).as_posix()
    relative_path(root,name)
    return resolve_repository_path(root,name)


def algorithm_config_path(root=ROOT, explicit=None):
    value=explicit if explicit is not None else configured('MODELCREW_ALGORITHM_CONFIG', root=root)
    return _path(root,value,external=True) if value is not None else data_root(root)/'algorithm-retrieval/index.json'


def algorithm_catalog_path(root=ROOT, explicit=None):
    return _path(root,explicit) if explicit is not None else data_root(root)/'algorithm-retrieval/catalog.json'


def paper_config_path(root=ROOT, explicit=None):
    value=explicit if explicit is not None else configured('MODELCREW_RETRIEVAL_CONFIG', root=root)
    return _path(root,value,external=True) if value is not None else data_root(root)/'paper-retrieval/index.json'


def reference_directory(root=ROOT, explicit=None):
    """New writes use the purpose directory; an explicit legacy root follows its exact manifest."""
    root=Path(root).resolve()
    if explicit is None:
        return data_root(root)/'references'
    path=_path(root,explicit,external=True)
    legacy=root/'stage-c/runs/references'
    if path != legacy:
        return path
    policy=root/'configs/repository-layout.json'
    import json
    settings=json.loads(policy.read_text(encoding='utf-8')) if policy.is_file() else {}
    matches=[]
    for name in settings.get('relocation_records',[]):
        record=json.loads(relative_path(root,name).read_text(encoding='utf-8'))
        if record.get('source')=='stage-c/runs/references':
            matches.append(record)
    if not matches:
        return path  # Unmigrated workspace: preserve its existing explicit root.
    if len(matches)!=1 or path.exists():
        raise ValueError('Conflicting historical reference directory')
    return relative_path(root,matches[0]['target'])


def mcp_log_directory(root=ROOT):
    return data_root(root)/'logs/mcp'
