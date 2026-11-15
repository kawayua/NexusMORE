"""CLI/real-Postgres drill for receipt recovery and interpretation review.

Uses fixed numeric evidence and TEST_SIMULATED_USER only. No model/code execution.
"""
from modelcrew.project_assets import asset_path
import copy,json,os,subprocess,sys,uuid
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.inputs import file_hash
from modelcrew.workflow import Workflow
from scripts.verify_stage_b_restart import restart

def cli(*args,expected_code=0):
    p=subprocess.run([sys.executable,'-m','modelcrew',*map(str,args)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=45)
    assert p.returncode==expected_code,(p.returncode,p.stderr[-2000:])
    return json.loads(p.stdout if p.returncode==0 else p.stderr)

def main():
    run=asset_path(ROOT,'stage-b/runs')/('execution-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));run.mkdir(parents=True)
    task='test-execution-review-'+uuid.uuid4().hex
    contract=json.loads((asset_path(ROOT,'contracts/examples/valid-2024-a-q1.json')).read_text(encoding='utf-8'))
    array=asset_path(ROOT,'stage-b/runs/solver-v2-20261104T131332959555Z/output/trajectories.npz')
    manifest={'contract_sha256':digest(contract),'description':'TEST_ONLY import fixed historical arrays, not a new solve','artifacts':[{'path':str(array),'sha256':file_hash(array),'role':'fixed_fixture'}]}
    manifest_path=run/'manifest.json';manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    config={'manifest_path':str(manifest_path),'manifest_sha256':file_hash(manifest_path)}
    with Workflow() as w:
        w.create(task,contract,project='automated-tests',executor_key='manifest-fixture',executor_config=config)
        original_event=w._event
        def fail_publication(*args):
            if args[1]=='execution_receipt_registered':raise RuntimeError('TEST crash after durable receipt before execution publication')
            return original_event(*args)
        w._event=fail_publication
        try:w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id='model-1')
        except RuntimeError as exc:assert 'TEST crash' in str(exc)
        else:raise AssertionError('Expected failure injection')
        assert w.db.execute('SELECT count(*) AS n FROM mc_backend_receipts WHERE task_id=%s',(task,)).fetchone()['n']==1
        assert not w.db.execute('SELECT 1 FROM mc_executions WHERE task_id=%s',(task,)).fetchone()
    restart();initial=cli('resume',task)
    assert initial['task']['phase']=='WAITING_RESULT_APPROVAL' and len(initial['execution_attempts'])==2
    eid=initial['task']['execution_id'];artifact=initial['execution']['artifacts'][0]
    good={'schema_version':'1.0.0','claims':[{'id':'head_speed_at_t0','source':{'artifact_sha256':artifact['sha256'],'output_id':'arrays','field':'speed_m_s','selector':{'index':[0,0]}},'operator':'eq','expected':1.,'unit':'m/s','abs_tolerance':1e-9}]}
    good_path=run/'claims-good.json';good_path.write_text(json.dumps(good),encoding='utf-8')
    common=['--version','1','--actor','TEST_SIMULATED_USER']
    passed=cli('act',task,'--kind','revise_interpretation',*common,'--request-id','good','--result-revision','1','--reason','TEST_ONLY verify numeric assertion','--claims',good_path,'--structured-only')
    assert passed['result']['review']['status']=='passed' and passed['task']['execution_id']==eid
    cli('act',task,'--kind','result',*common,'--request-id','approve-good','--result-revision','2','--decision','approve')
    bad=copy.deepcopy(good);bad['claims'][0]['expected']=999.;bad_path=run/'claims-bad.json';bad_path.write_text(json.dumps(bad),encoding='utf-8')
    failed=cli('act',task,'--kind','revise_interpretation',*common,'--request-id','bad','--result-revision','2','--reason','TEST_ONLY deliberately false assertion','--claims',bad_path,'--structured-only')
    assert failed['result']['review']['status']=='failed'
    rejected=cli('act',task,'--kind','result',*common,'--request-id','reject-failed-review','--result-revision','3','--decision','approve',expected_code=2)
    assert 'Failed review' in rejected['error']
    unknown=cli('act',task,'--kind','revise_interpretation',*common,'--request-id','unknown','--result-revision','3','--reason','TEST_ONLY free narrative requiring human assessment')
    assert unknown['result']['review']['status']=='unknown'
    restart();restored=cli('resume',task)
    assert restored['task']['phase']=='WAITING_RESULT_APPROVAL' and restored['result']['review']['status']=='unknown' and restored['task']['execution_id']==eid
    rejected=cli('act',task,'--kind','result',*common,'--request-id','unknown-no-reason','--result-revision','4','--decision','approve',expected_code=2)
    assert 'explicit human review reason' in rejected['error']
    final=cli('act',task,'--kind','result',*common,'--request-id','human-reviewed','--result-revision','4','--decision','approve','--reason','TEST_SIMULATED_USER reviewed the free narrative and explicitly acknowledged unknown semantics')
    replay=cli('act',task,'--kind','result',*common,'--request-id','human-reviewed','--result-revision','4','--decision','approve','--reason','TEST_SIMULATED_USER reviewed the free narrative and explicitly acknowledged unknown semantics')
    assert replay['task']['phase']=='COMPLETED'
    with Workflow() as w:
        counts={name:w.db.execute(f'SELECT count(*) AS n FROM {name} WHERE task_id=%s',(task,)).fetchone()['n'] for name in ['mc_executions','mc_backend_receipts','mc_backend_attempts','mc_results']}
    assert counts=={'mc_executions':1,'mc_backend_receipts':1,'mc_backend_attempts':2,'mc_results':4},counts
    report={'date':datetime.now().astimezone().isoformat(),'passed':True,'task_id':task,'actor':'TEST_SIMULATED_USER','mode':'fixture','backend':'manifest-fixture','database_restarts':2,
            'durable_receipt_before_publication_survived_restart':True,'backend_not_replayed_after_restart':True,
            'review_statuses_exercised':['passed','failed','unknown'],'false_numeric_claim_blocked':True,'unknown_requires_human_review_reason':True,
            'same_execution_reused_for_all_interpretations':True,'pending_review_survived_restart':True,'duplicate_confirmation_idempotent':True,'counts':counts,
            'new_model_calls':0,'new_code_executions':0,'limitations':['Passed claims verify declared arithmetic predicates against fixed evidence, not physical model correctness.','Free narrative remains unknown until explicit human assessment.']}
    (run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (asset_path(ROOT,'stage-b/executor-review-verification.json')).write_text(json.dumps({'report_path':str((run/'report.json').relative_to(ROOT)),**report},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
