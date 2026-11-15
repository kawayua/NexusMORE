"""Check Git-visible root entries and prevent new stage paths during F0 migration."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def check_layout(names, policy, *, final=False):
    issues = []
    allowed = set(policy['allowed_roots'])
    legacy = set(policy['legacy_stage_path_sha256'])
    for name in sorted(set(names)):
        top = name.split('/')[0]
        if top.startswith('stage-'):
            if final or hashlib.sha256(name.encode('utf-8')).hexdigest() not in legacy:
                issues.append({'path': name, 'reason': 'stage_path_requires_migration'})
        elif top not in allowed:
            issues.append({'path': name, 'reason': 'unexpected_root_entry'})
        elif final and (top in policy['transitional_roots'] or top.startswith('requirements-')):
            issues.append({'path': name, 'reason': 'transitional_layout_not_final'})
    return {'status': 'failed' if issues else 'passed', 'mode': 'final' if final else 'migration_guard',
            'issues': issues, 'final_layout_accepted': final and not issues, 'final_f0_accepted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final', action='store_true', help='Require final layout; no legacy exemptions')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root/'configs/repository-layout.json').read_text(encoding='utf-8'))
    output = subprocess.check_output(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z'])
    names = [n for n in output.decode('utf-8').rstrip('\0').split('\0') if n and (root/n).exists()]
    # Final inspection includes ignored or empty physical stage/transitional roots.
    if args.final:
        names += [p.name+'/' for p in root.iterdir() if p.is_dir() and (p.name.startswith('stage-') or p.name in policy['transitional_roots'])]
    result = check_layout(names, policy, final=args.final)
    print(json.dumps({'status':result['status'], 'mode':result['mode'], 'issues':len(result['issues']),
                      'final_layout_accepted':result['final_layout_accepted'], 'final_f0_accepted':result['final_f0_accepted']},ensure_ascii=False))
    if result['issues']:
        for item in result['issues'][:20]:
            print(json.dumps(item,ensure_ascii=False))
    return 1 if result['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
