"""Verified local native-tool preparation; never replace a configured tool silently."""
import hashlib
import json
import os
import re
from pathlib import Path,PurePosixPath
import subprocess
import urllib.request
import zipfile
from . import config
from .package_resources import resource
from .service_environment import _root,_path,_write,_sha,_lock,EnvironmentError


def _download(item,folder,*,offline=False,archives=None):
    target=folder/item['filename']
    if not target.exists():
        if archives is not None:
            source=Path(archives)/item['filename']
            if not source.is_file():raise EnvironmentError('Required verified archive is missing from the supplied directory')
            if source.stat().st_size!=item['bytes']:raise EnvironmentError('Tool archive size or SHA256 mismatch')
            data=source.read_bytes()
        elif offline:raise EnvironmentError('Required archive unavailable offline; prepare it on a connected machine')
        else:
            request=urllib.request.Request(item['url'],headers={'User-Agent':'NexusMORE/0.1 environment preparation'})
            try:
                with urllib.request.urlopen(request,timeout=120) as response:data=response.read(item['bytes']+1)
            except Exception:raise EnvironmentError('Official tool download failed; keep configuration and supply a verified archive or retry explicitly') from None
        if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise EnvironmentError('Tool archive size or SHA256 mismatch; refusing to extract or execute')
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    if target.stat().st_size!=item['bytes'] or _sha(target)!=item['sha256']:
        raise EnvironmentError('Cached tool archive identity changed')
    return target


def _extract(archive,destination):
    with zipfile.ZipFile(archive) as package:
        members=package.infolist()
        if sum(item.file_size for item in members)>450*1024*1024:raise EnvironmentError('Tool archive exceeds expanded-size limit')
        seen=set()
        for item in members:
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or ':' in item.filename or (item.external_attr>>16)&0o170000==0o120000:
                raise EnvironmentError('Unsafe archive member')
            if item.filename.casefold() in seen:raise EnvironmentError('Duplicate archive member')
            seen.add(item.filename.casefold())
        destination.mkdir(parents=True,exist_ok=False)
        package.extractall(destination)


def _version(path,name,expected):
    try:response=subprocess.run([str(path),'--version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.SubprocessError):raise EnvironmentError('Native tool version probe unavailable: '+name) from None
    line=response.stdout.splitlines()[0] if response.stdout.splitlines() else ''
    if response.returncode or not re.match(r'^'+re.escape(name)+r'(?:\.exe)? '+re.escape(expected)+r'(?: |$)',line,re.IGNORECASE):
        raise EnvironmentError('Unsupported native tool version: '+name+'; expected '+expected)
    return line


def prepare(root=None,*,offline=False,archives=None):
    from .user_workspace import initialize
    root=_root(root);initialize(root)
    if os.name!='nt':raise EnvironmentError('Native preparation currently supports Windows x86_64 only')
    spec=json.loads(resource('environment/native-tools.json').read_text(encoding='utf-8'))
    with _lock(root):
        settings_path=config.settings_path(root)
        if settings_path!=root/'configs/local/settings.json':raise EnvironmentError('Native preparation requires workspace-local settings')
        settings=config.load_settings(root);receipt_path=_path(root,'native-tools.json');existing={}
        if receipt_path.exists():existing=json.loads(receipt_path.read_text(encoding='utf-8')).get('tools',{})
        downloads=_path(root,'downloads');downloads.mkdir(exist_ok=True)
        tools={}
        for name in ['pandoc','tectonic']:
            item=spec['downloads'][name]
            installed_archive=False
            selected=config.configured('MODELCREW_'+name.upper(),root=root)
            if selected:
                executable=(root/Path(selected).expanduser()).resolve()
                previous=existing.get(name)
                if previous and str(executable)==previous['path'] and _sha(executable)!=previous['sha256']:
                    raise EnvironmentError('Previously prepared native executable changed')
            else:
                installed_archive=True
                archive=_download(item,downloads,offline=offline,archives=archives)
                destination=_path(root,'tools/'+name+'-'+item['version'])
                if destination.exists():
                    with zipfile.ZipFile(archive) as package:
                        expected={entry.filename for entry in package.infolist() if not entry.is_dir()}
                        actual={path.relative_to(destination).as_posix() for path in destination.rglob('*') if path.is_file()}
                        if actual!=expected:raise EnvironmentError('Partial tool extraction differs from the verified archive; use a new workspace or recover its original files')
                        for name_in_archive in expected:
                            from .repository_migration import relative_path
                            selected_file=relative_path(destination,name_in_archive)
                            if hashlib.sha256(package.read(name_in_archive)).hexdigest()!=_sha(selected_file):raise EnvironmentError('Extracted tool file changed; refusing to overwrite')
                else:_extract(archive,destination)
                matches=list(destination.rglob(item['executable']))
                if len(matches)!=1:raise EnvironmentError('Expected one executable in the verified archive')
                executable=matches[0].resolve()
            version=_version(executable,name,item['version'])
            tools[name]={'path':str(executable),'sha256':_sha(executable),'version':version,
                'archive_sha256':item['sha256'] if installed_archive else existing.get(name,{}).get('archive_sha256'),
                'source_url':item['url'] if installed_archive else existing.get(name,{}).get('source_url'),
                'source_kind':'verified_official_archive' if installed_archive else existing.get(name,{}).get('source_kind','configured_user_executable')}
            settings['export'][name]=str(executable)
        if not settings['export']['tex_cache']:settings['export']['tex_cache']='configs/local/tex-cache'
        if not receipt_path.exists():
            _write(_path(root,'settings.before-native-tools.json'),settings_path.read_text(encoding='utf-8'))
            temporary=_path(root,'settings.native-tools.tmp');_write(temporary,settings);os.replace(temporary,settings_path)
            _write(receipt_path,{'schema_version':'1.0.0','tools':tools,'platform':'Windows x86_64','rendering_verified':False})
    return {'status':'prepared','tools':tools,'rendering_verified':False,'download_mode':'offline_verified_archives' if offline else 'official_https_or_cache'}
