"""Live configured-provider + Docker probe on NEW synthetic tasks, never Q1/Q2 approval."""
from modelcrew.project_assets import asset_path
import json,uuid,argparse
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.contracts import validate,digest
from modelcrew.collaboration import sha_file
from modelcrew.workflow import Workflow
from modelcrew.hand_runtime import load,run_folder
BASE=asset_path(ROOT,'stage-d/runtime-integration/20261110-v1')

def coding():
    BASE.mkdir(parents=True,exist_ok=True)
    c=json.loads((asset_path(ROOT,'contracts/examples/valid-2024-a-q1.json')).read_text(encoding='utf-8-sig'))
    source=BASE/'linear-input.json';source.write_text(json.dumps({'a':2,'b':1,'x':list(range(11))}),encoding='utf-8')
    c['problem']={'case_id':'SYNTHETIC_LINEAR_RUNTIME','subproblem_id':'Q1','title':'Synthetic linear runtime probe','scope':'Engineering-only: y=2*x+1 for integer x=0..10. Minimal scope first 3 values. No real competition answer.','objective':{'kind':'simulation','description':'Compute exact linear map and report residuals.'}}
    c['sources']=[{'id':'statement','kind':'problem_statement','locator':'Explicit synthetic engineering probe, not user competition data','sha256':sha_file(source)}]
    c['inputs']=[{'id':'input0','source_id':'statement','path':str(source),'sha256':sha_file(source),'role':'dataset'}]
    c['conventions']={k:'dimensionless linear-map engineering probe' for k in c['conventions']}
    c['parameters']=[{'id':k,'value':v,'unit':'1','source_id':'statement','origin':'given','derivation':None} for k,v in [('a',2),('b',1)]]
    c['variables']=[{'id':'x','meaning':'integer input','unit':'1','domain':'0..10'},{'id':'y','meaning':'linear output','unit':'1','domain':'1..21'}]
    c['constraints']=[{'id':'linear','expression':'y=2*x+1','meaning':'Exact linear map','check_id':'residual'}]
    c['method']={'steps':['Read JSON input; compute y=a*x+b; independently check residuals and output JSON.'],'root_selection':'Not applicable, no root solving.','allowed_equivalent_changes':['Equivalent vectorized or scalar arithmetic.'],'requires_new_confirmation':['Changed coefficients or inputs.']}
    c['outputs']=[{'id':'result','path':'result.json','format':'json','fields':[{'name':'x','shape':[11],'unit':'1'},{'name':'y','shape':[11],'unit':'1'}],'decimal_places':None}]
    c['checks']=[{'id':'residual','description':'Every y equals 2*x+1','method':'Independent scalar residuals','tolerance':1e-12,'unit':'1','evidence_required':'Each selected input, output and residual; explicitly label minimal scope','initial_status':'unknown'}]
    c['risks']=['Synthetic fixture proves execution/routing only.'];c['alternatives']=['Scalar arithmetic']
    validate(c);task='runtime-live-linear-'+uuid.uuid4().hex
    with Workflow() as w:
        w.setup();w.create(task,c,executor_key='pending-code')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='synthetic-model-consent',version=1,kind='model',decision='approve',defer_execution=True,reason='TEST_ONLY simulated approval for isolated engineering probe; never a real Q1/Q2 confirmation.')
        r=w.start_hand(task,'coding',version=1,actor='ENGINEERING_PROBE',request_id='linear-runtime',guidance='Compute the supplied exact linear mapping. This is explicitly synthetic; no general competition conclusion. Minimal result.json should provide x,y,residuals and scope.',minimal_scope='Use exactly first 3 x values and label this a minimal test, not full-contract completeness.',limits={'timeout_s':30,'max_files':32})
        states=[r]
        for _ in range(12):
            if r['phase'] in ['GENERATE_FULL','NEEDS_HUMAN','NEEDS_MODEL_REVISION','PROVIDER_UNKNOWN']:break
            r=w.advance_hand(task,r['run_id']);states.append(r)
        row=load(w,task,r['run_id']);folder=run_folder(row)
        record={'task_id':task,'run_id':r['run_id'],'final_phase':r['phase'],'engineering_probe_only':True,'simulation_of_user_approval':True,'business_Q1_Q2_modified':False,'states':states,'folder':folder.relative_to(ROOT).as_posix()}
        (BASE/('coding-live-'+r['run_id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'probe':'coding','phase':r['phase'],'record':str(BASE/('coding-live-'+r['run_id']+'.json'))}))

def writing():
    p=json.loads((asset_path(ROOT,'stage-d/d5/current-writing.json')).read_text(encoding='utf-8'))
    task=p['binding']['task_id'];src=ROOT/p['run_dir']
    with Workflow() as w:
        t=w.task(task);art=w.db.execute('SELECT artifacts FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()['artifacts']
        names={'sample-results.json','independent-numerics.json'}
        selected=[a.get('origin_path',a['path']) for a in art if Path(a.get('origin_path',a['path'])).name in names]
        if not selected:raise RuntimeError('No approved numerical summary selected')
        r=w.start_hand(task,'writing',version=1,actor='ENGINEERING_PROBE',request_id='generic-writer-live-'+uuid.uuid4().hex,guidance='生成完整中文问题一研究审阅稿。使用已确认数值和9张原图，仅验证通用Writer接入。大纲只列6个简洁保守论断：题意范围、模型约束、已确认求解方法、300秒实际结果、已认证误差与差分样本范围、模型局限。所有证据指针逐字选用有效路径示例，不写未证实的半径下界或碰撞结论。新稿需要单独审阅，不能继承既有正文批准。',figure_catalog=(src/'figure-catalog.json').relative_to(ROOT).as_posix(),sources=['stage-d/d5/sources/cumcm2024a-statement.txt','stage-d/d5/sources/scipy-brentq-1.15.3.txt'],result_evidence=selected)
        states=[r]
        for _ in range(15):
            if r['phase'] in ['WAITING_MANUSCRIPT_AND_FIGURES','NEEDS_HUMAN','NEEDS_MODEL_REVISION','PROVIDER_UNKNOWN']:break
            r=w.advance_hand(task,r['run_id']);states.append(r)
        record={'task_id':task,'run_id':r['run_id'],'final_phase':r['phase'],'engineering_probe_only':True,'new_user_approval_created':False,'old_manuscript_modified':False,'states':states}
        (BASE/('writing-live-'+r['run_id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'probe':'writing','phase':r['phase'],'record':str(BASE/('writing-live-'+r['run_id']+'.json'))}))
def recheck_writing(run_id,rationale=None):
    task='d2-bench-q1-20261108'
    with Workflow() as w:
        r=w.recheck_hand(task,run_id,rationale=rationale or '请根据实际结构化binding而非历史版本叙述核对版本；/result/binding不存在，绑定在result的/binding。程序重新校验原模型、结果批准与原文件哈希，请独立检查，原FAIL保留不要求PASS。如新大纲缺图文映射应按实际问题返工，模型与正文问题区分；证据ID/指针及issue域/责任手须严格符合约定。')
        states=[r]
        for _ in range(15):
            if r['phase'] in ['WAITING_MANUSCRIPT_AND_FIGURES','NEEDS_HUMAN','NEEDS_MODEL_REVISION','PROVIDER_UNKNOWN']:break
            r=w.advance_hand(task,run_id);states.append(r)
        record={'task_id':task,'run_id':run_id,'final_phase':r['phase'],'original_receipt_preserved':True,'new_user_approval_created':False,'states':states}
        path=BASE/('writing-recheck-'+run_id+'.json');path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'probe':'read-only writing recheck','phase':r['phase'],'record':str(path)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('hand',choices=['coding','writing','recheck-writing']);p.add_argument('--run-id');p.add_argument('--rationale');p.add_argument('--output',type=Path);a=p.parse_args();
    if a.output:
        BASE=(ROOT/a.output).resolve();BASE.relative_to(ROOT.resolve());BASE.mkdir(parents=True,exist_ok=True)
    coding() if a.hand=='coding' else recheck_writing(a.run_id,a.rationale) if a.hand=='recheck-writing' else writing()
