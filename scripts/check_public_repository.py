"""Validate the public product view without private records, credentials or services."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'configs/public-repository.json'
FORBIDDEN = ('archive', 'runs', 'output', 'artifacts', 'tmp', 'configs/local',
             'docs/history', 'docs/release', 'docs/validation', 'docs/migrations')
SECRET = re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|(?<![A-Za-z0-9])(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})(?![A-Za-z0-9])')
HOME_PATH = re.compile(r'(?i)(?:[a-z]:[\\/]+users[\\/]+[^\s"<>`]+|/(?:Users|home)/[^/\s]+)')
LINK = re.compile(r'!?\[[^\]\n]+\]\(([^)\n]+)\)')
FENCE = re.compile(r'(?ms)^```[^\n]*\n.*?^```[^\n]*$')


def safe_path(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or name.startswith('/') or PureWindowsPath(name).drive:
        raise ValueError('Expected portable repository-relative path')
    parts = name.split('/')
    if any(p in {'', '.', '..', '.git'} for p in parts):
        raise ValueError('Path escape or Git internals are not public inputs')
    if any(name.lower() == p or name.lower().startswith(p+'/') for p in FORBIDDEN):
        raise ValueError('Private development/process path')
    if parts[0].startswith('stage-') or (parts[-1].lower().startswith('.env') and parts[-1] != '.env.example'):
        raise ValueError('Private or historical root path')
    return PurePosixPath(name)


def inspect_text(name, raw):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return [{'file': name, 'rule': 'non_text_file_requires_review'}]
    issues = []
    for label, pattern in [('credential_pattern', SECRET), ('personal_home_path', HOME_PATH)]:
        for match in pattern.finditer(text):
            issues.append({'file': name, 'rule': label, 'line': text.count('\n',0,match.start())+1,
                           'match_sha256': hashlib.sha256(match.group().encode()).hexdigest()})
    if any(ord(c) < 32 and c not in '\n\r\t' for c in text):
        issues.append({'file': name, 'rule': 'unexpected_control_character'})
    return issues


def visible_files(root):
    """Use Git visibility in an actual checkout; otherwise inspect a fresh export."""
    try:
        top = Path(subprocess.check_output(['git','-C',str(root),'rev-parse','--show-toplevel'],stderr=subprocess.DEVNULL,text=True).strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        top = None
    if top == root:
        raw = subprocess.check_output(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z'])
        return {p for p in raw.decode('utf-8').split('\0') if p and (root/p).is_file()}
    ignored = {'.git','__pycache__','.pytest_cache','.venv','venv','build','dist','tmp'}
    return {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
            and not any(part in ignored or part.endswith('.egg-info') for part in p.relative_to(root).parts)}


def check_tree(root=ROOT):
    root = Path(root).resolve()
    config = json.loads((root/MARKER).read_text(encoding='utf-8'))
    if config['schema_version'] != '1.0.0' or config['profile'] != 'public_product':
        raise ValueError('Unknown public view profile')
    expected = set(config['files']) | {MARKER}
    actual = visible_files(root)
    issues = [{'file':n,'rule':'unexpected_file'} for n in sorted(actual-expected)]
    issues += [{'file':n,'rule':'missing_file'} for n in sorted(expected-actual)]
    links = 0
    for name in sorted(expected & actual):
        try:
            safe_path(name)
            path=root/name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Symlink or path escape')
        except ValueError:
            issues.append({'file':name,'rule':'forbidden_path'})
            continue
        raw=path.read_bytes()
        issues.extend(inspect_text(name,raw))
        if name == 'README.md' or name.startswith('docs/') or name.startswith('.github/') or name.endswith('/README.md'):
            if not name.endswith('.md'):
                continue
            text=FENCE.sub('',raw.decode('utf-8-sig'))
            for match in LINK.finditer(text):
                target=match.group(1).strip().removeprefix('<').removesuffix('>')
                url=urlsplit(target)
                if url.scheme in {'https','http','mailto'}:
                    continue
                if url.scheme or url.netloc or url.path.startswith('/') or PureWindowsPath(url.path).drive:
                    issues.append({'file':name,'rule':'nonportable_link'})
                    continue
                destination=(path.parent/unquote(url.path)).resolve() if url.path else path.resolve()
                links += 1
                if not destination.is_relative_to(root) or destination.relative_to(root).as_posix() not in expected:
                    issues.append({'file':name,'rule':'link_outside_public_view','target':target})
    manifest=json.loads((root/'src/modelcrew/resources/resource-manifest.json').read_text(encoding='utf-8'))
    resources=0
    for item in manifest['files']:
        path=root/'src/modelcrew/resources'/item['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256'] or path.stat().st_size!=item['bytes']:
            issues.append({'file':item['path'],'rule':'runtime_resource_identity'})
        resources+=1
    return {'status':'passed' if not issues else 'failed','profile':'public_product', 'files':len(actual),
            'local_document_links':links,'runtime_resources':resources,'issues':issues,
            'private_archive_needed':False,'model_or_database_called':False,'history_rewritten':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=check_tree(args.root)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
