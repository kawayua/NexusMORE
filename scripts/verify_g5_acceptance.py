"""G5 final boundary acceptance: disposable database, real stdio, no real approvals."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[1]
PROJECT='cumc-2026a-q1-drying-20261116'
TASK='native-4ed02afe4e71cb59297717350d6b97f5'
BUILD='134d08ff-b255-404c-9651-bc20d72a13ac'
DB_TESTS=['tests/test_business_mcp.py','tests/test_trusted_decisions.py','tests/test_dsh_decisions.py',
 'tests/test_dsh_inputs.py','tests/test_assembly_chat_review.py','tests/test_assembly_reconciliation.py']
UNIT_TESTS=['tests/test_business_contract.py','tests/test_combined_paper_review.py',
 'tests/test_dsh_integration.py','tests/test_w2_protocol.py','tests/test_w2_protocol_v3.py','tests/test_w2_runtime_evidence.py']
JS_TESTS=['tests/harness/test-workflow.mjs','tests/harness/dsh-connection.test.mjs',
 'tests/harness/dsh-conversation.test.mjs','tests/harness/dsh-decisions.test.mjs']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')


def live_snapshot(url):
    with psycopg.connect(url,row_factory=dict_row) as db:
        tables={}
        queries={'task':('SELECT * FROM mc_tasks WHERE id=%s',(TASK,)),
          'task_events':('SELECT * FROM mc_events WHERE task_id=%s ORDER BY id',(TASK,)),
          'contracts':('SELECT * FROM mc_contracts WHERE task_id=%s ORDER BY version',(TASK,)),
          'builds':('SELECT * FROM mc_assembly_builds WHERE project_id=%s ORDER BY id',(PROJECT,)),
          'business_operations':("SELECT * FROM mc_business_operations WHERE scope->>'project_id'=%s ORDER BY operation,request_id",(PROJECT,))}
        for name,(query,args) in queries.items():
            rows=db.execute(query,args).fetchall();tables[name]={'count':len(rows),'sha256':digest(rows)}
        row=db.execute('SELECT * FROM mc_assembly_builds WHERE id=%s',(BUILD,)).fetchone()
        if not row or row['phase']!='W2_PASSED':raise RuntimeError('Protected real paper is not at its expected terminal phase')
        files={}
        for relative,expected in row['payload']['sealed'].items():
            path=ROOT/relative
            if sha(path)!=expected:raise RuntimeError('Protected real paper artifact differs: '+relative)
            files[relative]=expected
        return {'tables':tables,'sealed_files':files,'build_id':BUILD,'phase':row['phase'],
          'source_policy':'Read-only baseline only. No user approval or business action is generated.'}


def source_identity():
    files=list((ROOT/'src').rglob('*.py'))+list((ROOT/'src').rglob('*.mjs'))+list((ROOT/'src').rglob('*.js'))
    files+=list((ROOT/'tests').rglob('*.py'))+list((ROOT/'tests/harness').glob('*.mjs'))+[Path(__file__).resolve()]
    files=[p for p in files if '__pycache__' not in p.parts]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files))}


def xml_results(path):
    cases=[]
    for c in ET.parse(path).getroot().iter('testcase'):
        state='failed' if c.find('failure') is not None or c.find('error') is not None else 'skipped' if c.find('skipped') is not None else 'passed'
        cases.append({'test':c.attrib.get('classname','')+'.'+c.attrib['name'],'status':state,'seconds':float(c.attrib.get('time','0'))})
    return {'passed':sum(c['status']=='passed' for c in cases),'failed':sum(c['status']=='failed' for c in cases),
        'skipped':sum(c['status']=='skipped' for c in cases),'cases':cases}


def run_group(output,name,command,env):
    with (output/(name+'.log')).open('w',encoding='utf-8') as log:
        p=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    result={'name':name,'command':command,'returncode':p.returncode,'log':name+'.log'}
    if name!='javascript' and (output/(name+'.xml')).exists():result.update(xml_results(output/(name+'.xml')))
    write(output/(name+'-result.json'),result)
    return result


def verify(output):
    from modelcrew.config import database_url
    from modelcrew.package_resources import verify_resources
    output=output.resolve();output.relative_to(ROOT/'runs')
    output.mkdir(parents=True,exist_ok=False)
    original=database_url();protected=live_snapshot(original);write(output/'live-before.json',protected)
    sources=source_identity();write(output/'source-identity.json',{'files':sources,'aggregate_sha256':digest(sources)})
    packages={}
    for name in ['modelcrew','pytest','psycopg','mcp','pydantic','numpy','scipy']:
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]='not_installed'
    write(output/'environment.json',{'platform':platform.platform(),'python':sys.version,'python_executable':sys.executable,'packages':packages,
      'node':subprocess.check_output(['node','--version'],text=True).strip(),
      'source_checkout':'Existing editable working tree, including uncommitted repairs; see full content identities. Not a clean release tag.'})
    name='nexusmore_dsh_decision_probe_'+uuid.uuid4().hex[:12]
    assert name.startswith('nexusmore_dsh_decision_probe_') and len(name.rsplit('_',1)[-1])==12
    with psycopg.connect(original,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    results=[];cleanup=False
    try:
        url=make_conninfo(original,dbname=name)
        env={**os.environ,'MODELCREW_DATABASE_URL':url,'MODELCREW_BUSINESS_TEST_URL':url,
          'MODELCREW_DSH_DECISIONS_TEST_URL':url,'MODELCREW_USER_EVENTS_TEST_URL':url,'PYTHONIOENCODING':'utf-8',
          'MODELCREW_LLM_BASE_URL':'http://127.0.0.1:9/g5-no-model-calls'}
        commands=[('database',[sys.executable,'-u','-m','pytest',*DB_TESTS,'-vv','--tb=short','--junitxml='+str(output/'database.xml')]),
          ('unit',[sys.executable,'-u','-m','pytest',*UNIT_TESTS,'-vv','--tb=short','--junitxml='+str(output/'unit.xml')]),
          ('javascript',['node','--test',*JS_TESTS])]
        # Independent tests run in separate processes; DB mutations are confined
        # to one suite and one disposable database. No live UI is driven.
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(run_group,output,n,c,env) for n,c in commands]
            for f in futures:results.append(f.result())
        with psycopg.connect(url,row_factory=dict_row) as db:
            evidence={'database':name,'migrations':[r['version'] for r in db.execute('SELECT version FROM mc_migrations ORDER BY version')],
                'operation_states':db.execute('SELECT operation,state,count(*)::int AS count FROM mc_business_operations GROUP BY operation,state ORDER BY operation,state').fetchall(),
                'immutable_operation_events':db.execute('SELECT count(*)::int AS n FROM mc_business_operation_events').fetchone()['n'],
                'scope':'All objects are synthetic and confined to the generated probe database.'}
        write(output/'isolated-database-evidence.json',evidence)
    finally:
        with psycopg.connect(original,autocommit=True) as db:
            db.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
            cleanup=db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone() is None
        after=live_snapshot(original);write(output/'live-after.json',after)
        write(output/'run-result.json',{'groups':results,'isolated_database_removed':cleanup,
          'live_q1_unchanged':protected==after,'runtime_source_unchanged_during_run':sources==source_identity(),
          'status':'passed' if results and all(r['returncode']==0 and r.get('skipped',0)==0 for r in results) and cleanup and protected==after and sources==source_identity() else 'failed'})
    resources=verify_resources();write(output/'resources.json',resources)
    return json.loads((output/'run-result.json').read_text(encoding='utf-8'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    result=verify(args.output)
    print(json.dumps({'status':result['status'],'groups':[{k:v for k,v in r.items() if k not in ['cases','command']} for r in result['groups']],
      'live_q1_unchanged':result['live_q1_unchanged'],'isolated_database_removed':result['isolated_database_removed']},ensure_ascii=False))
    raise SystemExit(0 if result['status']=='passed' else 1)
