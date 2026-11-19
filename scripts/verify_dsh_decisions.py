"""Verify the private native DSH/G3 bridge in an isolated PostgreSQL database."""
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

ROOT=Path(__file__).resolve().parents[1]


def verify(output):
    from modelcrew.config import database_url
    from modelcrew.package_resources import verify_resources
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    protected=list((ROOT/'docs/release').glob('*20261115.json'))+list((ROOT/'src/modelcrew/resources/contracts').glob('business-*1.0.0*json'))
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    name='nexusmore_dsh_decision_probe_'+uuid.uuid4().hex[:12];original=database_url()
    with psycopg.connect(original,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        url=make_conninfo(original,dbname=name)
        env={**os.environ,'MODELCREW_DSH_DECISIONS_TEST_URL':url,'PYTHONIOENCODING':'utf-8'}
        with (output/'pytest.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-u','-m','pytest','tests/test_dsh_decisions.py','-vv','--tb=short','--junitxml='+str(output/'pytest.xml')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        with psycopg.connect(url) as db:
            migrations=[r[0] for r in db.execute('SELECT version FROM mc_migrations ORDER BY version')];assert migrations==list(range(1,16))
            assert not db.execute("SELECT 1 FROM mc_trusted_user_events e JOIN mc_trusted_host_captures h USING(event_id) WHERE e.principal->>'kind'<>'test_simulated_dsh' OR (e.statement NOT LIKE 'TEST_SIMULATED_USER:%' AND h.capture->>'source'<>'dsh_native_chat')").fetchone()
            assert not db.execute("SELECT 1 FROM mc_trusted_host_captures WHERE capture->'host'->>'engineering_only'<>'true'").fetchone()
            captures=db.execute('SELECT count(*) FROM mc_trusted_host_captures').fetchone()[0]
            claims=db.execute('SELECT count(*) FROM mc_trusted_user_event_claims').fetchone()[0]
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items())
        cases=list(ET.parse(output/'pytest.xml').getroot().iter('testcase'));assert not any(c.find('skipped') is not None for c in cases)
        report={'status':'passed','scope':'Synthetic native conversation and independent capture evidence; not a real host UI or user acceptance',
                'python_passed':len(cases),'simulated_host_captures':captures,'simulated_claims':claims,'migrations':migrations,
                'resources':verify_resources(),'real_user_approval':False,'model_or_solver_requests':0,'database_kept':False,
                'protected_historical_reports_and_contracts_unchanged':before}
        (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return report
    finally:
        with psycopg.connect(original,autocommit=True) as db:db.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    try:r=verify(args.output)
    except Exception as exc:
        print(json.dumps({'status':'failed','error_type':type(exc).__name__,'output':str(args.output)}));raise SystemExit(1) from None
    print(json.dumps({'status':r['status'],'python_passed':r['python_passed'],'output':str(args.output)}))
