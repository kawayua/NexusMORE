"""Record the user's explicit confirmation of the current D3 minimal result only."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from psycopg.conninfo import make_conninfo
from modelcrew.config import ROOT,database_url
from modelcrew.workflow import Workflow
from modelcrew.collaboration import CollaborationStore,Receipt,sha_file
from modelcrew.docker_executor import DockerExecutor
from modelcrew.mcp_client import executor_root
from modelcrew.modeling_hand import assert_m1
from modelcrew.mathematics import assert_gate_binding


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def main():
    current=read(ROOT/'stage-d/d3/current-solve.json')
    run=ROOT/current['current_run'];admission=read(run/'P1-admission.json')
    store=CollaborationStore(run/'records');receipt=store.load(Receipt,admission['receipt_sha256'])
    assert receipt.status=='PASS'
    assert store.accept_review(receipt,admission['snapshot_sha256'])==admission['receipt_sha256']
    execution=read(run/'execution.json');DockerExecutor(executor_root()).verify_artifacts(execution)
    assert execution['status']=='succeeded'
    identifier='user-minimal-result-confirmation-'+admission['receipt_sha256'][:20]
    folder=ROOT/'stage-d/d3/confirmations'/identifier;folder.mkdir(parents=True,exist_ok=True)
    with Workflow(url=make_conninfo(database_url(),connect_timeout=5)) as w,w.lock(current['task_id']):
        state=w.inspect(current['task_id']);task=state['task']
        assert task['current_version']==current['contract_version'] and state['contract']['sha256']==current['contract_sha256']
        assert task['model_approved'] and task['result_revision']==0 and not task['result_approved']
        assert_m1(w,task);assert_gate_binding(w,task,'model')
        approval=folder/'approval.json'
        if not approval.exists():
            payload={'schema_version':'1.0.0','actor':'user','user_statement':'结果确认','recorded_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                'task_id':task['id'],'contract_version':task['current_version'],'contract_sha256':state['contract']['sha256'],
                'scope':'D3_current_case_minimal_result','decision':'approve','run_folder':current['current_run'],
                'minimal_times_s':current['minimal_times_s'],'handle_count':224,'P1_receipt_sha256':admission['receipt_sha256'],
                'P1_snapshot_sha256':admission['snapshot_sha256'],'execution_run_id':execution['run_id'],'code_sha256':execution['code_sha256'],
                'approved_artifacts':execution['artifacts'],'validation_sha256':sha_file(run/'validation.json'),
                'full_301_time_result_approved':False,'formal_result_revision':0,'generic_D3_implementation_accepted':False,
                'explanation':'用户确认上一轮展示的8时刻全部224把手最小运行与独立P1结果；301时刻全量结果和P2尚未产生，不能预先批准。'}
            write(approval,payload)
        payload=read(approval)
        assert payload['P1_receipt_sha256']==admission['receipt_sha256'] and payload['validation_sha256']==sha_file(run/'validation.json')
        response=w.record_entry(task['id'],version=task['current_version'],kind='feedback',actor='user',request_id=identifier,
            text='用户：结果确认。已确认当前D3开发题8时刻×224把手的最小运行及P1结果；不涵盖尚未生成的301时刻全量结果或P2。',
            artifacts=[{'path':approval.relative_to(ROOT).as_posix(),'sha256':sha_file(approval),'role':'user_minimal_result_approval'}],
            metadata={'decision':'approve','scope':'D3_current_case_minimal_result','run_folder':current['current_run'],'P1_receipt_sha256':admission['receipt_sha256']})
        after=w.inspect(task['id'])
        assert after['task']['result_revision']==0 and not after['task']['result_approved'] and after['execution'] is None
        registration={'database_entry':response,'approval_sha256':sha_file(approval),'phase':after['task']['phase'],
            'minimal_result_approved':True,'formal_full_result_approved':False,'formal_result_revision':0}
        if not (folder/'registration.json').exists():write(folder/'registration.json',registration)
        else:assert read(folder/'registration.json')==registration
    progress=read(ROOT/'stage-d/progress.json')
    progress['current_milestone']='D3_case_minimal_result_user_confirmed'
    progress['milestones']['D3']['minimal_result_user_confirmation']={'status':'approved','scope':'current_case_minimal_result_only',
        'evidence':approval.relative_to(ROOT).as_posix(),'registration':(folder/'registration.json').relative_to(ROOT).as_posix()}
    write(ROOT/'stage-d/progress.json',progress)
    assert read(approval)['decision']=='approve'
    print(json.dumps({'minimal_result_confirmed':True,'full_result_confirmed':False,'record':approval.relative_to(ROOT).as_posix(),'entry_id':response['entry_id']}))


if __name__=='__main__':main()
