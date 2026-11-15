"""Read-only F0 inventory of Git-visible files; no migration or license approval."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

STAGE_REFERENCE = re.compile(r"stage-[a-z][a-z0-9+-]*(?:/[^\s\"'`<>)}\],;]*)?")
TEXT_SUFFIXES = {'.py', '.md', '.json', '.toml', '.txt', '.yml', '.yaml', '.sql', '.sh', '.ps1'}


def safe_file(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise ValueError(f'Unsafe repository path: {name}')
    candidate = root.joinpath(*relative.parts)
    for part in [candidate, *candidate.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError(f'Link requires manual review: {name}')
    if not candidate.resolve().is_relative_to(root):
        raise ValueError(f'Path escapes repository: {name}')
    return candidate


def classify(name):
    head = name.split('/')[0]
    logical = name[4:] if name.startswith('src/') else name
    if logical.startswith('modelcrew/resources/'):
        return 'bundled_resource_requires_manifest_review', 'src/' + logical, None
    if head.startswith('stage-'):
        return 'mixed_research_requires_review', None, False
    targets = {
        'modelcrew': ('runtime_code', 'src/' + name, True),
        'src': ('runtime_code', name, True),
        'configs': ('deployment_or_repository_configuration', name, False),
        'resources': ('resource_requires_license_review', 'src/modelcrew/' + name, None),
        'contracts': ('contract_requires_fixture_review', 'src/modelcrew/resources/' + name, None),
        'migrations': ('database_migration', 'src/modelcrew/resources/' + name, True),
        'integrations': ('third_party_requires_manifest_review', None, None),
        'tests': ('test', name, False),
        'scripts': ('maintenance_entry', name, False),
        'docs': ('documentation', name, False),
        'execution': ('execution_configuration', 'configs/' + name, None),
    }
    return targets.get(head, ('root_requires_review', None, None))


def inventory(root, names):
    root = Path(root).resolve(strict=True)
    files, references, missing = [], [], []
    for name in sorted(set(names)):
        path = safe_file(root, name)
        if not path.exists():
            missing.append(name)
            continue
        if not path.is_file():
            raise ValueError(f'Not a regular file: {name}')
        raw = path.read_bytes()
        role, target, required = classify(name)
        files.append({'old_path': name, 'proposed_path': target, 'sha256': hashlib.sha256(raw).hexdigest(),
                      'bytes': len(raw), 'role': role, 'required_in_wheel': required,
                      'license_status': 'not_determined', 'migration_status': 'not_moved',
                      'release_decision': 'pending_review'})
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                # Only record path tokens, never entire source lines (which may contain secrets).
                for match in STAGE_REFERENCE.finditer(line.replace('\\', '/')):
                    references.append({'caller': name, 'line': number, 'reference': match.group(),
                                       'runtime_candidate': name.startswith('modelcrew/')})
    return {'schema_version': '1.0.0', 'scope': 'git_visible_worktree_files_including_untracked',
            'limitations': ['Ignored local files are excluded; database references have not been queried.',
                            'Text matches are candidates, not proof of runtime dependency.',
                            'Proposed destinations are not approved migrations or redistribution permission.'],
            'migration_executed': False, 'files': files, 'references': references,
            'missing_worktree_files': missing,
            'summary': {'files': len(files), 'roles': dict(sorted(Counter(f['role'] for f in files).items())),
                        'stage_reference_occurrences': len(references),
                        'runtime_reference_occurrences': sum(r['runtime_candidate'] for r in references)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    output = args.output.resolve()
    if not output.is_relative_to(root / 'tmp'):
        parser.error('Inventory contains local filenames; output must stay under repository tmp/')
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            check=True, capture_output=True)
    names = result.stdout.decode('utf-8').rstrip('\0').split('\0') if result.stdout else []
    report = inventory(root, names)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
