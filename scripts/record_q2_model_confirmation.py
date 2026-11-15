"""Record explicit user approval of Q2 v2; defer execution until Coder/P1."""
from modelcrew.project_assets import asset_path
import json,os
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.writing_hand import read,new,rel,frozen_manifest,verify_files
from modelcrew.collaboration import sha_file
from modelcrew.modeling_hand import assert_m1
from modelcrew.mathematics import assert_gate_binding
from scripts.run_d4_full import workflow

STATEMENT='相邻板凳整对豁免、按完整矩形外包络处理孔洞、非相邻板凳首次接触即停止的想法很正确 通过'
def replace(path,value):
    tmp=path.with_name(path.name+'.next');new(tmp,value);os.replace(tmp,path)

def main():
    base=asset_path(ROOT,'stage-d/q2-modeling');current=read(base/'current-model.json');folder=ROOT/current['run_dir']
    dest=base/'confirmations'/('user-model-v2-'+current['contract_sha256'][:16]);dest.mkdir(parents=True,exist_ok=True)
    record={'actor':'user','user_statement':STATEMENT,'decision':'approve','scope':'Q2_current_model_v2_including_three_collision_assumptions','task_id':current['task_id'],'contract_version':2,'contract_sha256':current['contract_sha256'],'math_semantic_sha256':current['math_semantic_sha256'],'M1_receipt_sha256':current['M1_receipt_sha256'],'M1_snapshot_sha256':current['M1_snapshot_sha256'],'approved_assumptions':['相邻板凳整对豁免','按完整矩形外包络处理孔洞','非相邻板凳首次接触即停止，包含孤立相切'],'proposal_path':current['proposal'],'proposal_sha256':sha_file(ROOT/current['proposal']),'contract_file_sha256':sha_file(folder/'attempt-0/contract.json'),'mathematics_file_sha256':sha_file(folder/'attempt-0/mathematics.json'),'does_not_approve_results':True,'execution_deferred_for_code_and_P1':True}
    path=dest/'approval.json'
    if not path.exists():new(path,{**record,'recorded_at':datetime.now(timezone.utc).isoformat()})
    else:assert all(read(path)[k]==v for k,v in record.items())
    with workflow() as w:
        t=w.task(current['task_id']);assert t['current_version']==2
        gate=assert_m1(w,t);assert gate['receipt_sha256']==current['M1_receipt_sha256']
        state=w.action(t['id'],actor='user',request_id='user-Q2-v2-model-'+current['contract_sha256'][:20],version=2,kind='model',decision='approve',math_semantic_sha256=current['math_semantic_sha256'],reason=STATEMENT+'；批准当前第二题版本2完整模型方案及明确的三项碰撞约定，后续结果另行确认。',defer_execution=True)
        after=state['task'];assert after['model_approved'] and not after['result_approved'] and after['execution_id'] is None
        assert_gate_binding(w,after,'model')
        entry=w.record_entry(t['id'],version=2,kind='feedback',actor='user',request_id='user-Q2-v2-assumptions-'+current['contract_sha256'][:20],text=STATEMENT,artifacts=[{'path':rel(path),'sha256':sha_file(path),'role':'Q2_explicit_model_and_collision_assumption_approval'}],metadata={'decision':'approve','scope':record['scope'],'contract_sha256':current['contract_sha256'],'math_semantic_sha256':current['math_semantic_sha256']})
        assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(t['id'],)).fetchone()['n']==0
        registration={'database_entry':entry,'task_id':t['id'],'version':2,'model_approved':True,'result_approved':False,'phase':after['phase'],'execution':None,'approval_sha256':sha_file(path),'independent_M1':'PASS','new_solver_runs':0}
        if not (dest/'registration.json').exists():new(dest/'registration.json',registration)
        else:assert read(dest/'registration.json')==registration
    current.update({'phase':after['phase'],'model_approved':True,'new_assumptions_require_user_confirmation':False,'new_assumptions_user_confirmed':True,'model_approval':rel(path),'confirmation_registration':rel(dest/'registration.json'),'next':'Coder implementation, controlled minimal run and independent P1; results remain unapproved'})
    replace(base/'current-model.json',current)
    p=read(asset_path(ROOT,'stage-d/progress.json'));p['current_milestone']='Q2_model_v2_and_collision_assumptions_user_confirmed';p['questions']['Q2'].update({'phase':after['phase'],'model_approved':True,'model_approval':rel(path),'three_collision_assumptions':'user_confirmed','result_approved':False,'execution_deferred_for_Coder_P1':True});p['next']='Q2 Coder implementation, controlled minimal run and independent P1, then full event search after P1; result approval remains separate'
    replace(asset_path(ROOT,'stage-d/progress.json'),p)
    text='# 第二题方案用户确认\n\n用户明确：“'+STATEMENT+'”。已记录为第二题当前契约版本2完整方案通过，包含相邻整对豁免、完整填孔外包矩形、非相邻首次接触即停三项约定。\n\n批准绑定当前模型语义、方案文件与独立M1回执；模型批准为true，结果批准仍为false。执行暂缓以先完成代码实现、受控最小运行和独立P1，没有调用求解器。\n\n[确认记录]('+rel(path).split('stage-d/q2-modeling/')[1]+') · [数据库登记]('+rel(dest/'registration.json').split('stage-d/q2-modeling/')[1]+')\n'
    if not (base/'user-confirmation.md').exists():(base/'user-confirmation.md').write_text(text,encoding='utf-8')
    else:assert (base/'user-confirmation.md').read_text(encoding='utf-8')==text
    paths=[path,dest/'registration.json',base/'user-confirmation.md',base/'current-model.json',asset_path(ROOT,'stage-d/progress.json'),ROOT/'scripts/record_q2_model_confirmation.py',ROOT/current['proposal'],folder/'attempt-0/contract.json',folder/'attempt-0/mathematics.json']
    new(base/'confirmation-evidence.json',{'recorded_at':datetime.now(timezone.utc).isoformat(),'files':frozen_manifest(paths),'model_approved':True,'result_approved':False,'new_solver_runs':0})
    verify_files(read(base/'confirmation-evidence.json')['files'])
    print(json.dumps({'Q2_version':2,'model_approved':True,'three_collision_assumptions':'user_confirmed','result_approved':False,'new_solver_runs':0,'record':rel(base/'user-confirmation.md')}))
if __name__=='__main__':main()
