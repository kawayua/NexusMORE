"""D4 case-specific full Q1 execution, export, validation and result submission."""
from modelcrew.project_assets import asset_path
import argparse,hashlib,json,shutil,uuid,sys,platform
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from openpyxl import load_workbook
from psycopg.conninfo import make_conninfo
from modelcrew.config import ROOT,database_url
from modelcrew.contracts import digest
from modelcrew.workflow import Workflow,WorkflowError
from modelcrew.collaboration import (CollaborationStore,Call,Receipt,Binding,Snapshot,Artifact,sha_file)
from modelcrew.docker_executor import DockerExecutor,register_job
from modelcrew.mcp_client import executor_root
from modelcrew.mcp_workflow import trace_call
from modelcrew.full_numerics import load_arrays,numeric_checks,workbook_checks
from scripts.run_d3_minimal import approved,static_check,read,write

BASE=asset_path(ROOT,'stage-d/runs/full')
TASK='d2-bench-q1-20261108'
PARENT=asset_path(ROOT,'stage-d/runs/coding/minimal-f3630a0b71e246b686a0017e5cd3a69b')


def workflow():return Workflow(url=make_conninfo(database_url(),connect_timeout=5))


def ensure_current(w,meta):
    return approved(w,meta['task_id'],meta['contract_version'],meta['contract_sha256'])


def prepare(task=TASK):
    previous=read(PARENT/'run.json');admission=read(PARENT/'P1-admission.json')
    origin=CollaborationStore(PARENT/'records');receipt=origin.load(Receipt,admission['receipt_sha256'])
    if receipt.status!='PASS' or origin.accept_review(receipt,admission['snapshot_sha256'])!=admission['receipt_sha256']:
        raise ValueError('Current minimal P1 PASS required')
    if sha_file(PARENT/'generated_solver.py')!=previous['code_sha256']:raise ValueError('P1 source changed')
    user_confirmation=asset_path(ROOT,'stage-d/d3/confirmations/user-minimal-result-confirmation-9463202292597fcf4946/approval.json')
    if read(user_confirmation)['P1_receipt_sha256']!=admission['receipt_sha256']:raise ValueError('Minimal confirmation binding mismatch')
    with workflow() as w,w.lock(task):
        state=approved(w,task,previous['contract_version'],previous['contract_sha256'])
        name='full-'+uuid.uuid4().hex;folder=BASE/name;folder.mkdir(parents=True,exist_ok=False)
        (folder/'output').mkdir();(folder/'sources').mkdir()
        source=(PARENT/'generated_solver.py').read_text(encoding='utf-8')
        core=source[:source.index('def run_checks():')]
        code=core+'\n'+(asset_path(ROOT,'execution/full_q1_tail.py')).read_text(encoding='utf-8-sig')
        static_check(code)
        (folder/'numerical-core.py').write_text(core,encoding='utf-8')
        (folder/'generated_solver.py').write_text(code,encoding='utf-8')
        execution_id=str(uuid.uuid4())
        binding=Binding(task_id=task,contract_version=state['task']['current_version'],contract_sha256=state['contract']['sha256'],execution_id=execution_id,result_revision=state['task']['result_revision']+1)
        store=CollaborationStore(folder/'records');shutil.copytree(PARENT/'records',folder/'records',dirs_exist_ok=True)
        author=Call(call_id=str(uuid.uuid4()),context_id='codex-D4-coding-'+uuid.uuid4().hex,role='coding',binding=binding)
        store.register_call(author)
        meta={'task_id':task,'contract_version':binding.contract_version,'contract_sha256':binding.contract_sha256,
            'folder':folder.relative_to(ROOT).as_posix(),'parent_run':previous['folder'],'parent_P1_receipt_sha256':admission['receipt_sha256'],
            'code_sha256':sha_file(folder/'generated_solver.py'),'core_sha256':sha_file(folder/'numerical-core.py'),
            'P1_core_preserved_exactly':True,'author':author.model_dump(mode='json'),
            'lineage_call_ids':previous.get('prior_author_ids',[])+[previous['author']['call_id'],author.call_id],
            'execution_id':execution_id,'result_revision':binding.result_revision,'status':'prepared',
            'new_model_generation_calls':0,'implementation_author':'Codex coding-hand extension of P1-approved core',
            'result_user_approval':'pending','figure_selection_user_approval':'pending','created_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
        write(folder/'run.json',meta);write(folder/'contract.json',state['contract']['content'])
        write(folder/'inputs.json',{'inputs':state['contract']['content']['inputs']})
        write(folder/'mathematics.json',state['mathematics']['content'])
        config_files=['resources/paper/workflow.json','resources/paper/writer-instructions.md','resources/paper/chinese-modeling-policy.json',
            'docs/scientific-figure-contract.md','resources/algorithms/index.md','resources/algorithms/numerical-geometry.md']
        configs=[]
        for i,path in enumerate(config_files):
            p=ROOT/path;target=folder/'sources'/f'{i}-{p.name}';shutil.copyfile(p,target)
            configs.append({'path':path,'sha256':sha_file(p),'snapshot':target.relative_to(ROOT).as_posix()})
        write(folder/'configuration.json',{'sources':configs,'backend':'Python/matplotlib','source':'explicit project workflow','artifact_tool_available':False,'spreadsheet_fallback':'openpyxl under approved template and unavailable artifact-tool exception'})
        for path in ['scripts/run_d4_full.py','modelcrew/full_numerics.py','execution/full_q1_tail.py']:
            shutil.copyfile(ROOT/path,folder/'sources'/Path(path).name)
        write(folder/'code-evidence.json',{'code':code,'code_sha256':meta['code_sha256'],'core_sha256':meta['core_sha256'],
            'source_P1_code_sha256':previous['code_sha256'],'core_preserved_exactly':True,'extension':'301 times, same numerical functions; chunked NPZ output; FD/refinement/integration samples'})
        for key,extra in [('guard-probe','DENOM_GUARD=1e99\nsolve(0.0)\n'),('bracket-probe','ROD_L[0]=1e6\nsolve(0.0)\n')]:
            (folder/(key+'.py')).write_text(core+'\n'+extra,encoding='utf-8')
        w.record_entry(task,version=binding.contract_version,kind='code',actor='coding-hand',request_id=name+'-prepared',text='D4全量代码准备完成；原P1数学求解函数保持字节不变，新增全量驱动与验证。尚未执行。',artifacts=[{'path':(folder/'generated_solver.py').relative_to(ROOT).as_posix(),'sha256':meta['code_sha256'],'role':'full_solver_code'}],metadata={'run_folder':meta['folder'],'parent_P1_receipt_sha256':admission['receipt_sha256']})
        print(str(folder),flush=True);return folder


def run_job(folder,key):
    meta=read(folder/'run.json');job_id=folder.name+'-'+key
    code=folder/(key+'.py') if key.endswith('probe') else folder/'generated_solver.py'
    if key not in ['primary','reproduction','guard-probe','bracket-probe']:raise ValueError('Invalid job kind')
    with workflow() as w,w.lock(meta['task_id']):
        current=ensure_current(w,meta)
        if sha_file(folder/'generated_solver.py')!=meta['code_sha256']:raise ValueError('Full solver source changed')
        root=executor_root();saved=folder/(key+'-job.json');dispatch=folder/(key+'-dispatch.json')
        if not saved.exists():
            if dispatch.exists():raise ValueError('Dispatch has no job record; inspect, do not retry')
            inputs=[{'name':'template.xlsx' if i['role']=='required_output_template' else 'statement.pdf','path':i['path'],'sha256':i['sha256'],'input_id':i['id']} for i in current['contract']['content']['inputs']]
            job=register_job(root,job_id,code,inputs,{'mode':'workflow','task_id':meta['task_id'],'version':meta['contract_version'],'contract_sha256':meta['contract_sha256']},{'timeout_s':180,'memory_mb':1024,'max_file_bytes':2*1024*1024,'max_total_bytes':4*1024*1024})
            write(saved,job)
        job=read(saved);_,actual=DockerExecutor(root).job(job_id)
        if job!=actual or job['code_sha256']!=sha_file(code):raise ValueError('Job registration changed')
        tool='code_execution_status' if dispatch.exists() else 'code_execute'
        write(dispatch,{'job_id':job_id,'tool':tool,'operation_key':job_id})
        trace,envelope=trace_call(w,meta['task_id'],meta['contract_version'],'code-executor',tool,{'run_id' if tool=='code_execution_status' else 'job_id':job_id},job_id)
        write(folder/(key+'-envelope.json'),envelope)
        if envelope['status']!='ok':raise WorkflowError('MCP infrastructure error; inspect existing operation/status, never blindly resend')
        result=envelope['data'];write(folder/(key+'-execution.json'),result)
        if result.get('job_sha256')!=job['job_sha256'] or result.get('code_sha256')!=job['code_sha256'] or result.get('authorization')!=job['authorization'] or result.get('run_id')!=job_id or result.get('cleanup',{}).get('removed') is not True:
            raise ValueError('Execution provenance/cleanup mismatch')
        if key.endswith('probe'):
            needle='denominator below guard' if key=='guard-probe' else 'no outward bracket'
            if result['status']!='code_error' or result.get('exit_code') in [0,None] or needle not in result.get('stderr',''):
                raise ValueError('Fault probe did not produce expected nonzero abort')
        elif result['status']!='succeeded':raise ValueError('Full solver did not succeed: '+result['status'])
        DockerExecutor(root).verify_artifacts(result)
        print(json.dumps({'job':key,'status':result['status'],'elapsed_s':result.get('elapsed_s')}),flush=True)
        return result


def read_execution(folder,key):
    meta=read(folder/'run.json');job=read(folder/(key+'-job.json'));result=read(folder/(key+'-execution.json'))
    _,registered=DockerExecutor(executor_root()).job(job['job_id'])
    code=folder/(key+'.py') if key.endswith('probe') else folder/'generated_solver.py'
    if registered!=job or sha_file(code)!=job['code_sha256'] or result.get('job_sha256')!=job['job_sha256'] or result.get('code_sha256')!=job['code_sha256'] or result.get('authorization')!=job['authorization'] or result.get('run_id')!=job['run_id'] or result.get('cleanup',{}).get('removed') is not True:
        raise ValueError('Execution snapshot no longer matches')
    if job['authorization']!={'mode':'workflow','task_id':meta['task_id'],'version':meta['contract_version'],'contract_sha256':meta['contract_sha256']}:raise ValueError('Execution task binding mismatch')
    if key.endswith('probe'):
        needle='denominator below guard' if key=='guard-probe' else 'no outward bracket'
        if result['status']!='code_error' or result.get('exit_code') in [0,None] or needle not in result.get('stderr',''):raise ValueError('Probe abort evidence missing')
    else:
        if result['status']!='succeeded' or result.get('exit_code')!=0:raise ValueError('Full execution not successful')
    DockerExecutor(executor_root()).verify_artifacts(result)
    root=executor_root();artifacts={}
    for item in result['artifacts']:
        path=(root/item['path']).resolve()
        if not path.is_relative_to(root/'runs'/job['job_id']/'artifacts') or item['name'] in artifacts:raise ValueError('Unexpected artifact path/duplicate name')
        artifacts[item['name']]=path
    return result,artifacts


def merge_arrays(folder,key):
    execution,files=read_execution(folder,key)
    expected={'numeric-checks.json','trajectory-0.npz','trajectory-1.npz','trajectory-2.npz'}
    if set(files)!=expected:raise ValueError('Full output files incomplete')
    report=read(files['numeric-checks.json']);meta=read(folder/'run.json')
    if report.get('code_sha256')!=meta['code_sha256'] or report.get('contract_sha256')!=meta['contract_sha256'] or report.get('numerical_self_checks_passed') is not True or report.get('actual_solver_run') is not True or report.get('fixture') is not False:raise ValueError('Numeric report binding/failure')
    parts=[]
    for i,(a,b) in enumerate([(0,100),(100,200),(200,301)]):
        with np.load(files[f'trajectory-{i}.npz'],allow_pickle=False) as data:
            wanted={'time_s':(b-a,),'theta_rad':(b-a,224),'position_m':(b-a,224,2),'velocity_m_s':(b-a,224,2),'speed_m_s':(b-a,224)}
            if set(data.files)!=set(wanted):raise ValueError('Unexpected chunk members')
            part={name:data[name].copy() for name in wanted}
            if any(value.shape!=wanted[name] or not np.all(np.isfinite(value)) for name,value in part.items()) or not np.array_equal(part['time_s'],np.arange(a,b)):raise ValueError('Invalid chunk shape/time/values')
            parts.append(part)
    arrays={name:np.concatenate([part[name] for part in parts]) for name in parts[0]}
    return arrays,report


def execute(folder):
    if (folder/'frozen-artifacts.json').exists():
        # Frozen results are immutable: replay checks existing receipts and
        # archived outputs without rewriting dispatches, reports or run state.
        from modelcrew.full_result import verify_frozen_files
        verify_frozen_files(folder)
        for key in ['primary','reproduction','guard-probe','bracket-probe']:
            result,_=read_execution(folder,key)
            print(json.dumps({'job':key,'status':result['status'],'frozen_read_only':True,'new_code_executed':False}),flush=True)
        verify_frozen_files(folder)
        return
    for key in ['primary','reproduction','guard-probe','bracket-probe']:run_job(folder,key)
    arrays,report=merge_arrays(folder,'primary');again,_=merge_arrays(folder,'reproduction')
    differences={name:float(np.max(np.abs(arrays[name]-again[name]))) for name in arrays}
    if not all(value==0 for value in differences.values()):raise ValueError('Independent rerun differs')
    output=folder/'output';destination=output/'trajectories.npz'
    if destination.exists():
        existing=load_arrays(destination)
        if any(not np.array_equal(arrays[k],existing[k]) for k in arrays):raise ValueError('Existing full arrays differ')
    else:np.savez_compressed(destination,**arrays)
    write(output/'numeric-self-report.json',report)
    repro={'passed':True,'new_independent_container_run':True,'primary':read(folder/'primary-execution.json')['run_id'],
        'reproduction':read(folder/'reproduction-execution.json')['run_id'],'identical_code_sha256':read(folder/'run.json')['code_sha256'],
        'max_absolute_array_difference':differences,'comparison':'unrounded floating arrays, exact equality',
        'source_archives':[p.relative_to(ROOT).as_posix() for p in (folder/'sources').iterdir()],
        'replay_command':'python -m scripts.run_d4_full execute --run '+folder.relative_to(ROOT).as_posix(),
        'replay_semantics':'Completed registered jobs are status queries. Fresh new execution requires a newly prepared run; the recorded reproduction already used a separate real container.',
        'python':platform.python_version(),'numpy':np.__version__,'image_id':read(folder/'primary-execution.json')['image_id']}
    write(folder/'reproduction.json',repro)
    probes={'passed':True,'base_core_sha256':read(folder/'run.json')['core_sha256'],'not_physical_predictions':True,'probes':{}}
    for key in ['guard-probe','bracket-probe']:
        result,_=read_execution(folder,key)
        probes['probes'][key]={'passed':True,'status':result['status'],'exit_code':result['exit_code'],'stderr':result['stderr'],'probe_code_sha256':result['code_sha256'],'function_definitions_unchanged':True}
    write(folder/'fault-probes.json',probes)
    meta=read(folder/'run.json');meta['status']='executed_and_reproduced';write(folder/'run.json',meta)


def export(folder):
    meta=read(folder/'run.json')
    with workflow() as w:ensure_current(w,meta)
    arrays=load_arrays(folder/'output/trajectories.npz');contract=read(folder/'contract.json')
    template=next(i for i in contract['inputs'] if i['role']=='required_output_template')
    if sha_file(template['path'])!=template['sha256']:raise ValueError('Approved template changed')
    target=folder/'output/result1.xlsx'
    if not target.exists():
        book=load_workbook(template['path'])
        try:
            for title,values in [('位置',arrays['position_m'].transpose(1,2,0).reshape(448,301)),('速度',arrays['speed_m_s'].T)]:
                ws=book[title]
                for row in range(values.shape[0]):
                    for col in range(301):
                        cell=ws.cell(row+2,col+2);cell.value=round(float(values[row,col]),6);cell.number_format='0.000000'
            book.save(target)
        finally:book.close()
    check=workbook_checks(target,arrays,template);write(folder/'workbook-validation.json',check)
    if not check['passed']:raise ValueError('Spreadsheet roundtrip failed')
    print('full workbook exported and independently reread',flush=True)


def validate(folder):
    meta=read(folder/'run.json');contract=read(folder/'contract.json')
    if digest(contract)!=meta['contract_sha256'] or sha_file(folder/'generated_solver.py')!=meta['code_sha256']:raise ValueError('Full contract/code changed')
    arrays,report=merge_arrays(folder,'primary');replica,_=merge_arrays(folder,'reproduction')
    saved=load_arrays(folder/'output/trajectories.npz')
    if any(not np.array_equal(arrays[k],saved[k]) or not np.array_equal(arrays[k],replica[k]) for k in arrays):raise ValueError('Merged or reproduced arrays differ')
    for key in ['guard-probe','bracket-probe']:read_execution(folder,key)
    numeric=numeric_checks(arrays,contract,report)
    template=next(i for i in contract['inputs'] if i['role']=='required_output_template')
    workbook=workbook_checks(folder/'output/result1.xlsx',arrays,template)
    if not numeric['passed'] or not workbook['passed']:raise ValueError('Full independent validation failed')
    write(folder/'independent-numerics.json',numeric);write(folder/'workbook-validation.json',workbook)
    mapping={'head_speed':['head_speed'],'rod_distance':['rod_distance'],'velocity_fd':['independent_velocity_fd'],
        'completeness':['position_formula','speed_consistency'],'chord_delta_stable':['stable_chord_squared','first_outward_branch'],
        'velocity_recurrence_guard':['denominator_margin','rigid_velocity'],'theta_diagnostics':['theta_order_direction','initial_position'],
        'head_arc_integration':['head_arc_integration'],'velocity_fd_refined':['independent_velocity_fd'],
        'root_tolerance_resample':['solver_root_refinement','refined_reference_position'],'excel_readback':[],'v2_execution_status':[]}
    if set(mapping)!={c['id'] for c in contract['checks']}:raise ValueError('Unsupported contract check set')
    checks={key:{'status':'passed','evidence':{'numeric_checks':{name:numeric['checks'][name] for name in names},'source':'independent-numerics.json'}} for key,names in mapping.items()}
    checks['completeness']['evidence']['arrays']={k:list(a.shape) for k,a in arrays.items()}
    checks['completeness']['evidence']['workbook']=workbook
    checks['excel_readback']['evidence']=workbook
    checks['velocity_recurrence_guard']['evidence']['fault_probes']=read(folder/'fault-probes.json')
    checks['v2_execution_status']['evidence']={'actual_solver_run':True,'fixture':False,'primary_run_id':read(folder/'primary-execution.json')['run_id'],'reproduction_run_id':read(folder/'reproduction-execution.json')['run_id'],'reproduction':read(folder/'reproduction.json'),'contract_version':meta['contract_version']}
    result={'passed':True,'contract_sha256':meta['contract_sha256'],'code_sha256':meta['code_sha256'],
        'checks':checks,'user_confirmation':'pending','P2_status':'pending','deterministic_error_bars':'not_applicable','not_collision_verification':True}
    write(folder/'output/checks.json',result)
    meta['status']='full_numerics_validated';write(folder/'run.json',meta)
    print(json.dumps({'full_contract_checks_passed':len(checks),'max_rod_error_m':numeric['checks']['rod_distance']['value']}),flush=True)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['prepare','execute','export','validate']);ap.add_argument('--run',type=Path);ap.add_argument('--task',default=TASK);args=ap.parse_args()
    if args.stage=='prepare':prepare(args.task);return
    if args.run is None:ap.error('--run required')
    folder=args.run.resolve()
    if folder.parent!=BASE.resolve() or folder.is_symlink():raise ValueError('Invalid full run path')
    {'execute':execute,'export':export,'validate':validate}[args.stage](folder)


if __name__=='__main__':main()
