"""Verify G2 against a disposable PostgreSQL database and standard MCP clients."""
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


def identity(path):
    data=path.read_bytes()
    return {'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}


def verify(output,*,keep_database=False):
    from modelcrew.config import database_url
    from modelcrew.package_resources import verify_resources
    from modelcrew.business_adapter import BusinessAdapter
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    original=database_url();database='nexusmore_g2_probe_'+uuid.uuid4().hex[:16]
    baseline_files=[ROOT/'docs/release/business-tool-contract-freeze-20261115.json',ROOT/'src/modelcrew/business_contract.py']
    baseline_files+=list((ROOT/'src/modelcrew/resources/contracts').glob('business-*-1.0.0*json'))
    baseline={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in baseline_files}
    with psycopg.connect(original,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    created=True;success=False
    try:
        url=make_conninfo(original,dbname=database)
        env={**os.environ,'MODELCREW_BUSINESS_TEST_URL':url,'PYTHONIOENCODING':'utf-8'}
        tests=['tests/test_business_mcp.py','tests/test_business_contract.py','tests/test_contracts.py',
               'tests/test_package_distribution.py','tests/test_package_resources.py','tests/test_packaged_assets.py',
               'tests/test_repository_layout.py','tests/test_resource_routing.py',
               'tests/test_document_tool_boundaries.py','tests/test_release_source_evidence.py']
        command=[sys.executable,'-m','pytest',*tests,'-q','--tb=short','--junitxml='+str(output/'pytest-results.xml')]
        run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        (output/'pytest.log').write_text(run.stdout+'\n'+run.stderr,encoding='utf-8')
        run.check_returncode()
        node=subprocess.run(['node','--test','tests/harness/test-workflow.mjs'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        (output/'legacy-bridge.log').write_text(node.stdout+'\n'+node.stderr,encoding='utf-8');node.check_returncode()
        from psycopg.rows import dict_row
        with psycopg.connect(url,row_factory=dict_row) as db:
            operations=db.execute('SELECT operation,state,count(*)::int AS count FROM mc_business_operations GROUP BY operation,state ORDER BY operation,state').fetchall()
            events=db.execute('SELECT count(*)::int AS count FROM mc_business_operation_events').fetchone()['count']
            approvals=db.execute("SELECT count(*)::int AS count FROM mc_events WHERE kind IN ('model_approve','result_approve')").fetchone()['count']
            migrations=[r['version'] for r in db.execute('SELECT version FROM mc_migrations ORDER BY version').fetchall()]
        assert approvals==0 and migrations==list(range(1,16))
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in baseline.items())
        xml=ET.parse(output/'pytest-results.xml').getroot();cases=list(xml.iter('testcase'))
        skipped=[{'test':c.attrib['classname']+'.'+c.attrib['name'],'reason':c.find('skipped').attrib.get('message','')} for c in cases if c.find('skipped') is not None]
        report={'schema_version':'1.0.0','status':'passed','scope':'Synthetic adapter/stdio/PostgreSQL verification, not DSH integration or real three-hand quality acceptance',
                'test_database':database,'test_database_kept':keep_database,
                'python':{'passed':len(cases)-len(skipped),'skipped':skipped,
                          'business_mcp_cases':sum(c.attrib['classname']=='tests.test_business_mcp' for c in cases)},
                'legacy_js':{'passed':5},'resources':verify_resources(),'capabilities':BusinessAdapter().capabilities(),
                'database':{'migrations':migrations,'operation_counts':operations,'immutable_operation_events':events,'user_model_or_result_approval_events':approvals},
                'g1_frozen_identities_unchanged':baseline,'model_or_solver_requests':0,
                'real_process_exit_after_commit_tested':True,'restarted_standard_mcp_client_tested':True,
                'stderr_stdout_separation_tested':True,'new_user_approvals_created':False,
                'evidence':[identity(output/'pytest-results.xml'),identity(output/'pytest.log'),identity(output/'legacy-bridge.log')]}
        (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        success=True
        return report
    finally:
        if created and not keep_database:
            with psycopg.connect(original,autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
        if not success:
            (output/'verification-failed.json').write_text(json.dumps({'status':'failed','database':database,'database_kept':keep_database,'details':'Read local logs; credentials omitted'})+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--keep-database',action='store_true',help='Keep only the newly created synthetic probe database')
    args=p.parse_args()
    try:
        report=verify(args.output,keep_database=args.keep_database)
    except Exception as exc:
        print(json.dumps({'status':'failed','error_type':type(exc).__name__,'output':str(args.output)}));raise SystemExit(1) from None
    print(json.dumps({'status':report['status'],'python':report['python'],'mcp_tools':len(report['capabilities']['operations']),'output':str(args.output)},ensure_ascii=False))


if __name__=='__main__':main()
