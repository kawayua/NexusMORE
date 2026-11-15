"""Prepare a hash-bound relocation and backup; never move files automatically."""
import argparse
import json
from pathlib import Path
from modelcrew.repository_migration import snapshot, backup, relative_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--purpose', required=True)
    parser.add_argument('--record', required=True)
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    record = relative_path(root, args.record)
    if record.exists():
        raise FileExistsError(record)
    manifest = snapshot(root, args.source, args.target, args.purpose)
    backup(root, manifest, args.backup)
    record.parent.mkdir(parents=True, exist_ok=True)
    with record.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'files': len(manifest['files']), 'record': args.record, 'backup_verified': True}))


if __name__ == '__main__':
    main()
