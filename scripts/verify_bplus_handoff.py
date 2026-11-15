"""B+ durable handoff demonstration. Synthetic evidence and simulated actors only."""
from modelcrew.project_assets import asset_path
import copy,json,os,subprocess,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.inputs import file_hash
from modelcrew.workflow import Workflow,WorkflowError
from modelcrew.mathematics import MathematicsError

def main():
    run=asset_path(ROOT,'stage-b-plus/runs')/('handoff-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));run.mkdir(parents=True)
    checks=[]
    def check(name,ok,details=None):
        checks.append({'id':name,'passed':bool(ok),'details':details})
        if not ok:raise AssertionError(name)
    def reject(name,fn,classes=(ValueError,)):
        try:fn()
        except classes as exc:check(name,True,{'exception':type(exc).__name__,'message':str(exc)})
        else:check(name,False)
    def production(w):
        with w.lock('dragon-q1'),w.db.transaction():
            w.db.execute('SET TRANSACTION READ ONLY')
            t=w.task('dragon-q1')
            cs=w.db.execute('SELECT version,sha256,content FROM mc_contracts WHERE task_id=%s ORDER BY version',('dragon-q1',)).fetchall()
            events=w.db.execute('SELECT kind,actor,payload FROM mc_events WHERE task_id=%s ORDER BY id',('dragon-q1',)).fetchall()
            return {'task':{k:str(t[k]) if k in ['execution_id','updated_at'] else t[k] for k in ['id','current_version','result_revision','phase','model_approved','result_approved','execution_id','thread_id','updated_at']},'contracts':[{'version':c['version'],'sha256':c['sha256'],'valid_hash':digest(c['content'])==c['sha256']} for c in cs],'event_digest':digest(events),'math_packages':w.db.execute('SELECT count(*) AS n FROM mc_math_packages WHERE task_id=%s',('dragon-q1',)).fetchone()['n']}
    c=json.loads((asset_path(ROOT,'stage-b-plus/examples/contract-v2-snapshot.json')).read_text(encoding='utf-8'));p=json.loads((asset_path(ROOT,'stage-b-plus/examples/valid-bench-dragon.json')).read_text(encoding='utf-8'))
    fixture=run/'fixture.json';fixture.write_text('{"TEST_ONLY":true,"not_contest_result":true}',encoding='utf-8')
    manifest=run/'manifest.json';manifest.write_text(json.dumps({'description':'TEST_ONLY B+ version handoff; no model generated or numerical solve','contract_sha256':digest(c),'artifacts':[{'path':str(fixture),'sha256':file_hash(fixture),'role':'synthetic_bplus_fixture'}]},ensure_ascii=False),encoding='utf-8')
    config={'manifest_path':str(manifest),'manifest_sha256':file_hash(manifest)}
    task='test-bplus-demo-'+uuid.uuid4().hex
    def act(w,kind='model',version=1,request=None,**kw):return w.action(task,actor='TEST_SIMULATED_USER',request_id=request or uuid.uuid4().hex,version=version,kind=kind,reason='TEST_ONLY reviewed symbols, assumptions, branch limits and evidence',**kw)
    def child(cmd):
        done=subprocess.run([sys.executable,'-m','modelcrew',cmd,task],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=30)
        check('new_process_'+cmd,done.returncode==0,{'returncode':done.returncode})
        return json.loads(done.stdout)
    with Workflow() as w:
        before=production(w)
        s=w.create(task,c,project='bplus-engineering-tests',executor_key='manifest-fixture',executor_config=config,math_package=p)
        sha=s['mathematics']['semantic_sha256']
        check('no_auto_approval_or_execution',not s['task']['model_approved'] and s['execution'] is None)
        (run/'model-proposal.json').write_text(json.dumps(s['mathematics'],ensure_ascii=False,indent=2),encoding='utf-8')
        reject('missing_math_snapshot_blocks',lambda:act(w,decision='approve'))
        check('model_wait_survives_process_restart',child('resume')['task']['phase']=='WAITING_MODEL_APPROVAL')
        reject('business_commit_crash_injected',lambda:act(w,decision='approve',math_semantic_sha256=sha,request='approve-1',crash_after_commit=True),(RuntimeError,))
    recovered=child('resume');check('recover_to_result_gate',recovered['task']['phase']=='WAITING_RESULT_APPROVAL')
    with Workflow() as w:
        eid=str(w.task(task)['execution_id'])
        act(w,decision='approve',math_semantic_sha256=sha,request='approve-1')
        check('duplicate_model_approval_one_execution',len(w.version_dossier(task)['executions'])==1)
        reject('stale_result_revision_blocks',lambda:act(w,kind='result',decision='approve',math_semantic_sha256=sha,result_revision=2))
        done=act(w,kind='result',decision='approve',math_semantic_sha256=sha,result_revision=1)
        check('both_gates_confirmed',done['task']['phase']=='COMPLETED')
        layout=copy.deepcopy(p);layout['presentation']['equation_spacing']='relaxed'
        lr=w.publish_mathematics(task,version=1,package=layout,actor='TEST_EDITOR',request_id='layout-1',reason='TEST_ONLY line spacing')
        check('layout_revision_not_business_version',lr['revision']==2 and w.task(task)['current_version']==1)
        check('layout_preserves_confirmation_and_execution',w.task(task)['model_approved'] and w.task(task)['result_approved'] and str(w.task(task)['execution_id'])==eid and lr['semantic_sha256']==sha)
        changed=copy.deepcopy(layout);changed['validation_plan'][0]['threshold']=1e-9
        reject('math_change_cannot_use_layout_endpoint',lambda:w.publish_mathematics(task,version=1,package=changed,actor='TEST_EDITOR',request_id='bad-layout',reason='TEST_ONLY'))
        s=act(w,kind='revise_mathematics',math_package=changed)
        check('semantic_change_invalidates_downstream',s['task']['current_version']==2 and not s['task']['model_approved'] and not s['task']['result_approved'] and s['execution'] is None and s['task']['result_revision']==0)
        check('unchanged_contract_can_have_new_math_version',s['contract']['sha256']==digest(c) and s['mathematics']['semantic_sha256']!=sha)
        reject('old_math_hash_cannot_approve_v2',lambda:act(w,version=2,decision='approve',math_semantic_sha256=sha))
        reject('stale_business_version_cannot_approve',lambda:act(w,version=1,decision='approve',math_semantic_sha256=sha))
        s=act(w,version=2,kind='restore_version',source_version=1)
        check('restoration_requires_new_approval',s['task']['current_version']==3 and s['task']['phase']=='WAITING_MODEL_APPROVAL' and not s['task']['model_approved'] and s['execution'] is None)
        check('restoration_binds_new_identity',s['mathematics']['content']==layout and s['mathematics']['semantic_sha256']!=sha)
        dossier=w.version_dossier(task,1)
        check('history_retains_old_math_and_result',len(dossier['mathematical_history'])==2 and len(dossier['executions'])==1 and len(dossier['results'])==1)
        check('confirmations_contain_mathematical_snapshots',all(e['payload'].get('math_snapshot',{}).get('semantic_sha256')==sha for e in dossier['confirmations_and_events'] if e['kind'] in ['model_approve','result_approve']))
        after=production(w);check('production_task_unchanged',before==after)
        (run/'version1-dossier.json').write_text(json.dumps(dossier,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        (run/'final-state.json').write_text(json.dumps(s,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    report={'stage':'B+','status':'passed','task_id':task,'checks':checks,'production_before':before,'production_after':after,'actors_are_simulated':True,'new_model_calls':0,'new_contest_solver_runs':0,'execution_mode':'synthetic fixture','full_tex_compilation':False,'source_package_sha256':file_hash(asset_path(ROOT,'stage-b-plus/examples/valid-bench-dragon.json'))}
    target=run/'verification.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'stage':'B+','status':'passed','checks_passed':len(checks),'report_path':str(target.relative_to(ROOT)),'report_sha256':file_hash(target),'task_id':task}
    (asset_path(ROOT,'stage-b-plus/verification-summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
