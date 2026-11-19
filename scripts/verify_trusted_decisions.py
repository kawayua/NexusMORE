"""Run G3 trust probes in a disposable database, with simulated terminal evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]


def verify(output, *, keep_database=False, focused=False):
    from modelcrew.config import database_url
    from modelcrew.package_resources import verify_resources
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    protected = [ROOT/'docs/release/business-tool-contract-freeze-20261115.json',
                 ROOT/'docs/release/business-workflow-mcp-20261115.json', ROOT/'src/modelcrew/business_contract.py']
    protected += list((ROOT/'src/modelcrew/resources/contracts').glob('business-*-1.0.0*json'))
    baseline = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    database = 'nexusmore_g3_probe_' + uuid.uuid4().hex[:16]; original = database_url()
    with psycopg.connect(original, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    success = False
    try:
        url = make_conninfo(original, dbname=database)
        env = {**os.environ, 'MODELCREW_USER_EVENTS_TEST_URL': url, 'PYTHONIOENCODING': 'utf-8'}
        tests = ['tests/test_trusted_decisions.py', 'tests/test_business_contract.py',
                 'tests/test_writing_reviews.py', 'tests/test_writing_hand.py', 'tests/test_assembly_builds.py',
                 'tests/test_package_distribution.py', 'tests/test_package_resources.py', 'tests/test_packaged_assets.py',
                 'tests/test_repository_layout.py', 'tests/test_release_source_evidence.py']
        if focused:
            tests = [t for t in tests if t not in ('tests/test_writing_reviews.py', 'tests/test_writing_hand.py', 'tests/test_assembly_builds.py')]
        with (output/'pytest.log').open('w', encoding='utf-8') as log:
            run = subprocess.run([sys.executable, '-u', '-m', 'pytest', *tests, '-vv', '--tb=short', '--junitxml='+str(output/'pytest-results.xml')],
                                 cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        run.check_returncode()
        with psycopg.connect(url, row_factory=dict_row) as db:
            captures = db.execute('SELECT count(*)::int AS n FROM mc_trusted_user_events').fetchone()['n']
            claims = db.execute('SELECT count(*)::int AS n FROM mc_trusted_user_event_claims').fetchone()['n']
            assert not db.execute("SELECT 1 FROM mc_trusted_user_events WHERE principal->>'kind' <> 'test_simulated_terminal' OR statement NOT LIKE 'TEST_SIMULATED_USER:%'").fetchone()
            approvals = db.execute("SELECT count(*)::int AS n FROM mc_events WHERE kind IN ('model_approve','result_approve')").fetchone()['n']
            decisions = db.execute("SELECT kind,count(*)::int AS n FROM mc_events WHERE kind IN ('model_approve','model_reject','result_approve','result_reject') GROUP BY kind ORDER BY kind").fetchall()
            migrations = [r['version'] for r in db.execute('SELECT version FROM mc_migrations ORDER BY version').fetchall()]
            assert migrations == list(range(1, 16))
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in baseline.items())
        cases = list(ET.parse(output/'pytest-results.xml').getroot().iter('testcase'))
        skipped = [{'test': c.attrib['classname']+'.'+c.attrib['name'], 'reason': c.find('skipped').attrib.get('message', '')} for c in cases if c.find('skipped') is not None]
        report = {'schema_version': '1.0.0', 'status': 'passed',
                  'scope': 'Synthetic local terminal/identity/expiry/replay/crash boundaries; no real user or DSH capture',
                  'focused': focused,
                  'test_database': database, 'test_database_kept': keep_database,
                  'python': {'passed': len(cases)-len(skipped), 'skipped': skipped,
                             'trusted_decision_cases': sum(c.attrib['classname']=='tests.test_trusted_decisions' for c in cases)},
                  'database': {'migrations': migrations, 'simulated_captures': captures, 'simulated_claims': claims,
                               'simulated_core_approvals': approvals, 'simulated_core_decisions': decisions},
                  'resources': verify_resources(), 'protected_identities_unchanged': baseline,
                  'real_user_approval_created': False, 'model_or_solver_requests': 0,
                  'quality_gate_test_doubles_are_not_independent_acceptance': True,
                  'evidence': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in [output/'pytest-results.xml', output/'pytest.log']]}
        (output/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        success = True; return report
    finally:
        if not keep_database:
            with psycopg.connect(original, autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
        if not success:
            (output/'verification-failed.json').write_text(json.dumps({'status': 'failed', 'database': database, 'database_kept': keep_database, 'details': 'Read local logs; credentials omitted'})+'\n', encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True); p.add_argument('--keep-database', action='store_true'); p.add_argument('--focused', action='store_true', help='Run trust/contract/package regressions; omit existing slow writing/build suites')
    args = p.parse_args()
    try: report = verify(args.output, keep_database=args.keep_database, focused=args.focused)
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'output': str(args.output)})); raise SystemExit(1) from None
    print(json.dumps({'status': report['status'], 'python': report['python'], 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__': main()
