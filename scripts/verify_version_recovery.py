"""Real DB restarts at both gates and after a committed version restoration.

Only TEST_SIMULATED_USER tasks are changed; no model calls or fresh solver runs.
"""
from modelcrew.project_assets import asset_path
import copy,json,os,subprocess,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.workflow import Workflow
from modelcrew.inputs import file_hash
from scripts.verify_stage_b_restart import restart,cli_resume

def main():
    run=asset_path(ROOT,'stage-b/runs')/('version-recovery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));run.mkdir(parents=True)
    task='test-version-recovery-'+uuid.uuid4().hex
    contract=json.loads((asset_path(ROOT,'contracts/examples/valid-2024-a-q1.json')).read_text(encoding='utf-8'))
    note={'version':1,'kind':'proposal','text':'TEST_ONLY persisted proposal for recovery drill','actor':'TEST_SIMULATED_USER','request_id':'proposal-1'}
    with Workflow() as w:
        first=w.create(task,contract,project='automated-tests');thread=first['task']['thread_id']
        entry=w.record_entry(task,**note)
    restart();model=cli_resume(task)
    assert model['task']['phase']=='WAITING_MODEL_APPROVAL' and not model['execution'] and model['task']['thread_id']==thread
    with Workflow() as w:
        assert w.record_entry(task,**note)==entry
        state=w.action(task,version=1,kind='model',decision='approve',actor='TEST_SIMULATED_USER',request_id='approve-1')
        eid=str(state['task']['execution_id'])
    restart();result=cli_resume(task)
    assert result['task']['phase']=='WAITING_RESULT_APPROVAL' and str(result['task']['execution_id'])==eid
    assert not result['task']['result_approved']
    restoration={'version':2,'kind':'restore_version','source_version':1,'reason':'TEST_ONLY restore original after a version change','actor':'TEST_SIMULATED_USER','request_id':'restore-after-commit'}
    with Workflow() as w:
        changed=copy.deepcopy(contract);changed['risks'].append('TEST_ONLY recovery change')
        w.action(task,version=1,kind='revise_model',contract=changed,reason='TEST_ONLY v2',actor='TEST_SIMULATED_USER',request_id='revise-2')
        try:w.action(task,**restoration,crash_after_commit=True)
        except RuntimeError as exc:assert 'Injected crash' in str(exc)
        else:raise AssertionError('Expected committed/checkpoint failure injection')
    restart();restored=cli_resume(task)
    assert restored['task']['current_version']==3 and restored['task']['phase']=='WAITING_MODEL_APPROVAL'
    assert restored['contract']['restored_from_version']==1 and not restored['task']['model_approved'] and not restored['task']['result_approved']
    assert restored['execution'] is None and digest(restored['contract']['content'])==digest(contract)
    with Workflow() as w:
        replay=w.action(task,**restoration)
        assert replay['task']['current_version']==3 and len(w.versions(task))==3
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1
        assert w.db.execute('SELECT count(*) AS n FROM mc_version_entries WHERE task_id=%s',(task,)).fetchone()['n']==1
        assert not w.db.execute('SELECT 1 FROM mc_summaries WHERE task_id=%s',(task,)).fetchone()
    report={'date':datetime.now().astimezone().isoformat(),'task_id':task,'actor':'TEST_SIMULATED_USER','passed':True,
            'database_restarts':3,'fresh_cli_processes':3,'model_wait_restored':True,'result_wait_restored':True,
            'version_entry_survived_and_replay_idempotent':True,'restoration_commit_before_checkpoint_recovered':True,
            'restoration_replay_did_not_duplicate_version':True,'execution_count':1,'version_count':3,'entry_count':1,
            'new_version_requires_model_confirmation':True,'historical_results_not_auto_confirmed':True,
            'new_model_calls':0,'new_solver_runs':0,'mode':'historical_fixture_only'}
    (run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (asset_path(ROOT,'stage-b/version-recovery-verification.json')).write_text(json.dumps({'report_path':str((run/'report.json').relative_to(ROOT)),**report},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
