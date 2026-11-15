"""Package resource locations, independent of repository parent directories."""
from importlib.resources import files
from pathlib import PurePosixPath


def resource(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Expected package-relative resource name')
    result = files('modelcrew').joinpath('resources', *path.parts)
    if not result.is_file() and not result.is_dir():
        raise FileNotFoundError('Missing bundled resource: ' + name)
    return result


def verify_resources():
    import hashlib,json
    manifest=json.loads(resource('resource-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        data=resource(item['path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=item['sha256'] or len(data)!=item['bytes']:
            raise ValueError('Bundled resource identity changed: '+item['path'])
    return {'status':'passed','files':len(manifest['files']),'scope':'declared runtime resources; full knowledge intake and release licensing remain separate'}


if __name__=='__main__':
    import json
    print(json.dumps(verify_resources(),ensure_ascii=False))
