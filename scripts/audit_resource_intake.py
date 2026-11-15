"""Read-only inventory for resource intake; never grants redistribution rights.

Run with --source LABEL=PATH (repeatable). Keep --output under tmp/ because
source paths and upstream filenames are private intake evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path


def inventory(sources):
    files = []
    for label, root in sources:
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Source must be a directory')
        licenses = {}
        paths = sorted(root.rglob('*'))
        for path in paths:
            if path.is_symlink():
                raise ValueError('Symbolic links require separate review')
            if path.is_file() and path.name.lower().startswith(('license', 'copying', 'notice')):
                licenses[path.parent] = path
        for path in paths:
            if not path.is_file():
                continue
            raw = path.read_bytes()
            applicable = next((licenses[parent] for parent in [path.parent, *path.parents]
                               if parent.is_relative_to(root) and parent in licenses), None)
            license_text = applicable.read_text(encoding='utf-8', errors='replace') if applicable else ''
            restricted = ('users may not' in license_text and
                          'Distribute, sublicense, or transfer' in license_text)
            files.append({'source': label, 'path': path.relative_to(root).as_posix(),
                          'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                          'license_path': applicable.relative_to(root).as_posix() if applicable else None,
                          'status': 'restricted' if restricted else 'review_required'})
    # Identical mirrored files do not escape the original file's restriction.
    restricted_hashes = {f['sha256'] for f in files if f['status'] == 'restricted'}
    for file in files:
        if file['sha256'] in restricted_hashes:
            file['status'] = 'restricted'
    return {'schema_version': '1.0.0', 'scope': 'read_only_inventory_no_copy_no_execution',
            'public_redistribution_approved': False,
            'summary': {label: {'files': sum(f['source'] == label for f in files),
                               'restricted': sum(f['source'] == label and f['status'] == 'restricted' for f in files),
                               'review_required': sum(f['source'] == label and f['status'] == 'review_required' for f in files)}
                        for label, _ in sources},
            'files': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', required=True, metavar='LABEL=PATH')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = []
    for spec in args.source:
        label, separator, path = spec.partition('=')
        if not separator or not label or not path or label in {s[0] for s in sources}:
            parser.error('Each source needs a unique LABEL=PATH')
        sources.append((label, Path(path)))
    report = inventory(sources)
    output = args.output.resolve()
    local_root = (Path(__file__).resolve().parents[1] / 'tmp').resolve()
    if not output.is_relative_to(local_root):
        parser.error('Private inventory output must stay under workspace tmp/')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve earlier evidence; never overwrite an intake report.
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
