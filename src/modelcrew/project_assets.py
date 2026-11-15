"""Resolve immutable package resources and registered local historical inputs separately."""
import json
from functools import lru_cache
from pathlib import Path
from .config import ROOT
from .package_resources import resource
from .repository_migration import resolve_repository_location,relative_path


def asset_path(root,name):
    root=Path(root).resolve()
    value=Path(name)
    if value.is_absolute():
        if not value.is_relative_to(root):return value
        name=value.relative_to(root).as_posix()
    else:name=value.as_posix()
    # Explicit synthetic workspaces remain self-contained and do not inherit installed policies.
    original=relative_path(root,name,strict_root=False)
    if root!=Path(ROOT).resolve() and original.exists():return original
    if original.exists() and name.split('/',1)[0] not in {'resources','contracts','migrations','execution','modelcrew'} and not name.startswith('stage-'):
        return original
    policy=root/'configs/repository-layout.json'
    if name.startswith('stage-') and policy.is_file():
        info=policy.stat()
        aliases=_runtime_aliases(str(policy),info.st_mtime_ns,info.st_size)
        for alias in aliases:
            prefix=alias['old_prefix']+'/'
            if name.startswith(prefix):
                suffix=name[len(prefix):];identifier=suffix.split('/')[0]
                if identifier in alias['ids']:
                    return relative_path(root,alias['current_prefix']+'/'+suffix)
    # Only new project-authored reference names bind to the installed bundle.
    # Legacy Chinese names/reference/main.tex retain historical recovery semantics.
    from .paper_layout import REQUIRED
    if name in REQUIRED:return Path(resource(name.removeprefix('resources/')))
    bundled=None
    if name.startswith('resources/') and '/reference/' not in name and not name.endswith('/reference'):
        bundled=name[len('resources/'):]
    elif name.startswith(('contracts/','migrations/')) or name in ['contracts','migrations']:
        bundled=name
    elif name=='execution/sandbox_runner.py':bundled=name
    elif name in ['docs/scientific-figure-contract.md','docs/three-hand-collaboration.md'] and not original.exists():
        bundled='project-policy/'+name.split('/')[-1]
    if bundled is not None:
        try:return Path(resource(bundled))
        except FileNotFoundError:pass
    return resolve_repository_location(root,name)


def local_history(name):
    return asset_path(ROOT,name)


@lru_cache(maxsize=8)
def _runtime_aliases(policy,mtime,size):
    return json.loads(Path(policy).read_text(encoding='utf-8')).get('runtime_aliases',[])


def input_path(path):
    """Hash/read helpers resolve only legacy logical inputs; admission remains at their callers."""
    value=Path(path)
    if value.is_absolute():
        try:name=value.relative_to(ROOT).as_posix()
        except ValueError:return value
    else:name=value.as_posix()
    head=name.split('/',1)[0]
    return asset_path(ROOT,name) if head.startswith('stage-') or head in {'resources','contracts','migrations','execution','modelcrew'} else value
