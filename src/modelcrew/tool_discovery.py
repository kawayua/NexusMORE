"""Find host-installed export tools explicitly; never download or ship local binaries."""
from .config import configured as configuration_value
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from .config import ROOT
from .repository_migration import resolve_repository_path


class ToolUnavailable(RuntimeError):pass


def discover_tool(name, explicit=None, *, root=ROOT):
    if name not in {'pandoc','tectonic'}:raise ValueError('Unsupported export tool')
    root=Path(root).resolve()
    configured=explicit if explicit is not None else configuration_value('MODELCREW_'+name.upper(), root=root)
    if configured is not None:
        path=Path(configured).expanduser()
        if not path.is_absolute():path=root/path
        if path.is_relative_to(root):path=resolve_repository_path(root,path.relative_to(root).as_posix())
    else:
        found=shutil.which(name)
        path=Path(found) if found else root/'configs/local/tools'/('pandoc/pandoc.exe' if name=='pandoc' else 'tectonic.exe')
    if not path.is_file():
        raise ToolUnavailable(f'{name} executable missing; install it on PATH or set MODELCREW_{name.upper()} to its file path')
    return path.resolve()


def tex_cache_directory(root=ROOT):
    path=Path(configuration_value('TECTONIC_CACHE_DIR',Path(root)/'configs/local/tex-cache', root=root)).expanduser()
    return path if path.is_absolute() else Path(root)/path


def diagnostics():
    result=[]
    for name in ['pandoc','tectonic']:
        try:
            path=discover_tool(name)
            version=subprocess.run([str(path),'--version'],capture_output=True,text=True,encoding='utf-8',timeout=15,check=True)
            with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
            result.append({'name':name,'status':'available','path':str(path),'version':version.stdout.splitlines()[0],'sha256':sha})
        except (ToolUnavailable,OSError,subprocess.SubprocessError) as exc:
            result.append({'name':name,'status':'unavailable','error':str(exc)})
    return {'status':'passed' if all(item['status']=='available' for item in result) else 'failed','tools':result,'downloaded':False}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=diagnostics();print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
