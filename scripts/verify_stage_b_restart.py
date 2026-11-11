"""Explicit real database restart drill using simulated test tasks only."""
from pathlib import Path
import json,subprocess,sys,os,uuid,time
from datetime import datetime,timezone
from modelcrew.workflow import Workflow
from modelcrew.config import ROOT

def cli_resume(task):
    p=subprocess.run([sys.executable,'-m','modelcrew','resume',task],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=30)
    if p.returncode:raise RuntimeError('Fresh CLI resume failed: '+p.stderr[-2000:])
    return json.loads(p.stdout)
def restart():
    subprocess.run(['docker','restart','--time','10','modelcrew-stage-b-postgres'],check=True,capture_output=True,timeout=45)
    for _ in range(30):
        ready=subprocess.run(['docker','exec','modelcrew-stage-b-postgres','pg_isready','-U','modelcrew','-d','modelcrew'],capture_output=True,timeout=5)
        if ready.returncode==0:return
        time.sleep(.5)
    raise RuntimeError('Database failed to become ready')
def main():
    contract=json.loads((ROOT/'contracts/examples/valid-2024-a-q1.json').read_text(encoding='utf-8'))
    task='test-db-restart-'+uuid.uuid4().hex
    with Workflow() as w:
        first=w.create(task,contract,project='automated-tests')
        thread=first['task']['thread_id'];sha=first['contract']['sha256']
    restart();model=cli_resume(task)
    assert model['task']['phase']=='WAITING_MODEL_APPROVAL' and model['execution'] is None
    assert model['task']['thread_id']==thread and model['contract']['sha256']==sha
    with Workflow() as w:
        s=w.action(task,actor='TEST_SIMULATED_USER',request_id='restart-model',version=1,kind='model',decision='approve')
        eid=str(s['task']['execution_id'])
    restart();result=cli_resume(task)
    assert result['task']['phase']=='WAITING_RESULT_APPROVAL' and str(result['task']['execution_id'])==eid
    assert not result['task']['result_approved'] and result['checkpoint_next']==['result_gate']
    with Workflow() as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(task,)).fetchone()['n']==1
        assert not w.db.execute('SELECT 1 FROM mc_summaries WHERE task_id=%s',(task,)).fetchone()
    report={'date':datetime.now(timezone.utc).isoformat(),'task_id':task,'actor':'TEST_SIMULATED_USER','database_restarts':2,'fresh_cli_processes':2,'model_wait_restored':True,'result_wait_restored':True,'thread_and_contract_preserved':True,'execution_not_duplicated':True,'result_not_auto_approved':True,'mode':'historical_fixture_only','passed':True}
    (ROOT/'stage-b/database-restart-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
