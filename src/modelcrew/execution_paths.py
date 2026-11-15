"""Stable executor data root with explicit registered historical-directory compatibility."""
from .config import configured
import json
import os
from pathlib import Path
from .config import ROOT
from .repository_migration import relative_path
from .runtime_paths import data_root


def execution_directory(root=ROOT, explicit=None):
    root=Path(root).resolve()
    value=explicit if explicit is not None else configured('MODELCREW_EXECUTION_ROOT', root=root)
    if value is None:
        return data_root(root)/'execution'
    path=Path(value).expanduser()
    if not path.is_absolute():path=root/path
    if path.is_relative_to(root):path=relative_path(root,path.relative_to(root).as_posix())
    else:return path.resolve()  # Preserve supported explicit external executor roots.
    if path != root/'stage-c/execution':return path
    policy=root/'configs/repository-layout.json'
    settings=json.loads(policy.read_text(encoding='utf-8')) if policy.is_file() else {}
    records=[json.loads(relative_path(root,name).read_text(encoding='utf-8')) for name in settings.get('relocation_records',[])]
    matches=[record for record in records if record.get('source')=='stage-c/execution']
    if not matches:return path
    if len(matches)!=1 or path.exists():raise ValueError('Conflicting historical executor directory')
    return relative_path(root,matches[0]['target'])
