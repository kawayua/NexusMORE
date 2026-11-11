"""Trusted Q2 minimal-run orchestration. Never import the generated payload on host."""
import argparse,json,uuid
from pathlib import Path
import numpy as np
from modelcrew.config import ROOT
from modelcrew.collaboration import Artifact,Binding,Call,CollaborationStore,Snapshot,sha_file
from modelcrew.docker_executor import DockerExecutor,register_job
from modelcrew.mcp_client import executor_root
from modelcrew.mcp_workflow import trace_call
from scripts.run_d3_minimal import approved,static_check,read,write
from scripts.run_d4_full import workflow
TASK='d6-bench-q2-20261109'

def build():
    with workflow() as w,w.lock(TASK):
        s=approved(w,TASK,2)
        folder=ROOT/'stage-d/runs/coding'/('q2-minimal-'+uuid.uuid4().hex)
        folder.mkdir()
        contract=s['contract']['content']
        source=ROOT/'stage-d/runs/full/full-ed1a97c89d2c4aa3a4a2298a44a8ce77/generated_solver.py'
        core=source.read_text(encoding='utf-8').split('# D4 wrapper;')[0]
        core=core.replace('CONTRACT_SHA256 = "44e23c6a10b7581d82a2b2697159e7aaee1625d8486cb177bd541a9a36d2e61e"','CONTRACT_SHA256 = '+repr(s['contract']['sha256']))
        core=core[:core.index('CHECK_IDS =')]+ 'CHECK_IDS = '+repr([c['id'] for c in contract['checks']])+'\n'+core[core.index('ROD_L ='):]
        payload=ROOT/'scripts/q2_minimal_payload.py'
        code=core+'\n'+payload.read_text(encoding='utf-8-sig')
        (folder/'generated_solver.py').write_text(code,encoding='utf-8')
        write(folder/'preflight.json',static_check(code));write(folder/'contract.json',contract)
        write(folder/'inputs.json',{'inputs':contract['inputs']})
        write(folder/'mathematics.json',s['mathematics']['content'])
        bind=Binding(task_id=TASK,contract_version=2,contract_sha256=s['contract']['sha256'])
        coder=Call(call_id=str(uuid.uuid4()),context_id=str(uuid.uuid4()),role='coding',binding=bind)
        store=CollaborationStore(folder/'records');store.register_call(coder)
        origin=read(ROOT/'stage-d/q2-modeling/current-model.json')
        write(folder/'handoff.json',{'approved_model':origin,'model_sha256':s['contract']['sha256'],'M1_receipt_sha256':origin['M1_receipt_sha256'],'author':coder.model_dump(mode='json'),'source_artifacts':[{'path':str(source.relative_to(ROOT)),'sha256':sha_file(source),'use':'Q1 reviewed kinematic routines restricted to 0..300; Q2 collision code new'},{'path':'scripts/q2_minimal_payload.py','sha256':sha_file(payload),'use':'Q2 interval and SAT implementation'}],'algorithm_sources':[{'path':p,'sha256':sha_file(ROOT/p)} for p in ['resources/algorithms/index.md','resources/algorithms/numerical-geometry.md']]})
        write(folder/'code-evidence.json',{'code':code,'code_sha256':sha_file(folder/'generated_solver.py'),'authorship':'Codex coding context; no supplier Coder API called','scope':'minimal P1, no full first-event search'})
        meta=dict(task_id=TASK,contract_version=2,contract_sha256=s['contract']['sha256'],folder=folder.relative_to(ROOT).as_posix(),author=coder.model_dump(mode='json'),status='generated',code_sha256=sha_file(folder/'generated_solver.py'),user_result_confirmation='pending')
        write(folder/'run.json',meta)
        w.record_entry(TASK,version=2,kind='code',text='Q2代码手已实现最小运动/SAT/区间前缀验证，未计算首次碰撞答案。',actor='coding-hand',request_id=folder.name+'-code',artifacts=[{'path':meta['folder']+'/generated_solver.py','sha256':meta['code_sha256'],'role':'minimal_solver_code'}])
        print(str(folder));return folder

def execute(folder):
    m=read(folder/'run.json');root=executor_root()
    with workflow() as w,w.lock(TASK):
        state=approved(w,TASK,2,m['contract_sha256'])
        if sha_file(folder/'generated_solver.py')!=m['code_sha256']:raise ValueError('changed code')
        static_check((folder/'generated_solver.py').read_text(encoding='utf-8'))
        if not (folder/'job.json').exists():
            inputs=[{'name':'template.xlsx' if i['role']=='required_output_template' else 'statement.pdf','path':i['path'],'sha256':i['sha256'],'input_id':i['id']} for i in state['contract']['content']['inputs']]
            write(folder/'job.json',register_job(root,folder.name,folder/'generated_solver.py',inputs,{'mode':'workflow','task_id':TASK,'version':2,'contract_sha256':m['contract_sha256']},{'timeout_s':180,'memory_mb':1024}))
        job=read(folder/'job.json')
        tool='code_execution_status' if (folder/'dispatch.json').exists() else 'code_execute'
        if (folder/'execution-envelope.json').exists():
            previous=read(folder/'execution-envelope.json')
            if previous.get('error',{} ) and previous['error'].get('code')=='not_found' and not (root/'runs'/folder.name).exists():
                write(folder/'not-dispatched-recovery.json',{'evidence':previous,'run_directory_absent':True,'action':'dispatch same immutable job; prior attempt confirmed never dispatched'})
                tool='code_execute'
        write(folder/'dispatch.json',dict(tool=tool,job_id=folder.name))
        trace,envelope=trace_call(w,TASK,2,'code-executor',tool,{'run_id' if tool=='code_execution_status' else 'job_id':folder.name},folder.name)
        write(folder/('mcp-'+envelope['call_id']+'.json'),envelope)
        write(folder/'execution-envelope.json',envelope)
        if envelope['status']!='ok':raise ValueError('MCP failure; query this run, never resend')
        result=envelope['data'];write(folder/'execution.json',result)
        if result['status']!='succeeded':
            m.update(status='execution_'+result['status']);write(folder/'run.json',m);print(json.dumps(result,ensure_ascii=False));raise ValueError('execution failed; immutable failed run retained')
        if result['job_sha256']!=job['job_sha256'] or result['authorization']!=job['authorization'] or result['code_sha256']!=m['code_sha256'] or result['run_id']!=folder.name or result.get('cleanup',{}).get('removed') is not True:raise ValueError('provenance mismatch')
        DockerExecutor(root).verify_artifacts(result)
        m.update(status='executed',mcp_trace_id=trace);write(folder/'run.json',m)
    return validate(folder)

def validate(folder):
    m=read(folder/'run.json');r=read(folder/'execution.json');root=executor_root()
    job=read(folder/'job.json');_,registered=DockerExecutor(root).job(folder.name)
    if registered!=job or sha_file(folder/'generated_solver.py')!=m['code_sha256'] or r['code_sha256']!=m['code_sha256'] or r['job_sha256']!=job['job_sha256'] or r['authorization']!=job['authorization'] or r['status']!='succeeded' or r['cleanup']['removed'] is not True:raise ValueError('bad provenance')
    DockerExecutor(root).verify_artifacts(r)
    artifacts={a['name']:root/a['path'] for a in r['artifacts']}
    if set(artifacts)!={'minimal.npz','checks.json','sat-gap-0.npz','sat-gap-1.npz'}:raise ValueError('unexpected artifacts')
    for p in artifacts.values():
        if not p.resolve().is_relative_to((root/'runs'/folder.name/'artifacts').resolve()):raise ValueError('bad output path')
    report=read(artifacts['checks.json'])
    if report['code_sha256']!=m['code_sha256'] or report['contract_sha256']!=m['contract_sha256']:raise ValueError('report binding')
    with np.load(artifacts['minimal.npz'],allow_pickle=False) as z:data={key:z[key].copy() for key in z.files}
    with np.load(artifacts['sat-gap-0.npz'],allow_pickle=False) as one, np.load(artifacts['sat-gap-1.npz'],allow_pickle=False) as two:data['sat_gap_m']=np.concatenate([one['sat_gap_m'],two['sat_gap_m']])
    expected={'time_s':(8,),'theta_rad':(8,224),'position_m':(8,224,2),'velocity_m_s':(8,224,2),'speed_m_s':(8,224),'sat_gap_m':(8,24531),'pair_i':(24531,),'pair_j':(24531,)}
    if set(data)!=set(expected) or any(data[k].shape!=shape or not np.isfinite(data[k]).all() for k,shape in expected.items()):raise ValueError('shape or finite')
    from scripts.reference_2024_a_q1 import solve
    par=read(ROOT/'stage-a/2024-A-problem-1/parameters.json')
    ref=[solve(float(t),par) for t in data['time_s']]
    checks={}
    def check(k,x,lim):checks[k]={'passed':bool(x<=lim),'value':float(x),'limit':lim}
    check('fresh_reference_position_m',np.max(abs(data['position_m']-np.stack([s[1] for s in ref]))),1e-8)
    check('fresh_reference_velocity_m_s',np.max(abs(data['velocity_m_s']-np.stack([s[2] for s in ref]))),1e-8)
    pi,pj=np.triu_indices(223,2)
    if not np.array_equal(pi,data['pair_i']) or not np.array_equal(pj,data['pair_j']):raise ValueError('pair policy')
    # Independent geometry comparator projects actual vertices onto each polygon edge normal.
    lengths=np.full(223,2.2);lengths[0]=3.41
    geomerr=0.;minrecord=[]
    for ti,p in enumerate(data['position_m']):
        rods=np.diff(p,axis=0);u=rods/np.linalg.norm(rods,axis=1)[:,None];n=np.stack((-u[:,1],u[:,0]),axis=1);c=(p[:-1]+p[1:])/2
        corners=c[:,None,:]+lengths[:,None,None]/2*u[:,None,:]*np.array([1,1,-1,-1])[None,:,None]+.15*n[:,None,:]*np.array([1,-1,-1,1])[None,:,None]
        axes=np.stack((u[pi],n[pi],u[pj],n[pj]),axis=1)
        one=np.einsum('pvd,pad->pav',corners[pi],axes);two=np.einsum('pvd,pad->pav',corners[pj],axes)
        g=np.max(np.maximum(np.min(two,axis=2)-np.max(one,axis=2),np.min(one,axis=2)-np.max(two,axis=2)),axis=1)
        geomerr=max(geomerr,float(np.max(abs(g-data['sat_gap_m'][ti]))))
        minrecord.append({'time_s':float(data['time_s'][ti]),'minimum_gap_m':float(np.min(g))})
    check('independent_corner_projection_gap_m',geomerr,1e-8)
    errs=[]
    for ti,t in enumerate(data['time_s']):
        h=.001
        if t==0:der=(-3*solve(0,par)[1]+4*solve(h,par)[1]-solve(2*h,par)[1])/(2*h)
        elif t==300:der=(3*solve(300,par)[1]-4*solve(300-h,par)[1]+solve(300-2*h,par)[1])/(2*h)
        else:der=(solve(t+h,par)[1]-solve(t-h,par)[1])/(2*h)
        errs.append(float(np.max(np.linalg.norm(der-data['velocity_m_s'][ti],axis=1))))
    check('independent_velocity_fd_m_s',max(errs),1e-5)
    cert=report['prefix_certificate'];segments=cert['safe_intervals']
    cursor=0.
    for seg in segments:
        if seg['start_s']!=cursor or seg['end_s']<=cursor or seg['minimum_gap_lower_bound_m']<=0 or seg['all_pairs']!=24531:raise ValueError('certificate coverage')
        cursor=seg['end_s']
    if cursor!=1 or cert['status']!='SAFE':raise ValueError('prefix not proven')
    if report['first_contact_answer_status']!='NOT_COMPUTED' or any(v!='unknown' for v in report['full_contract_checks'].values()):raise ValueError('overclaimed final answer')
    checks['certificate_coverage']={'passed':True,'scope_s':[0,1],'segments':len(segments),'note':'coverage mechanically checked; interval arithmetic proof requires independent P1 source review'}
    v={'scope':'Q2_minimal_P1','passed':all(x['passed'] for x in checks.values()),'checks':checks,'samples':minrecord,'self_report':report,'generated_payload_executed_on_host':False,'final_answer_confirmable':False,'full_first_contact_search':'not implemented','not_user_approval':True}
    write(folder/'validation.json',v)
    if not v['passed']:raise ValueError('trusted checks failed')
    m['status']='validated';write(folder/'run.json',m)
    print(json.dumps({'folder':m['folder'],'passed':True,'checks':checks},ensure_ascii=False));return v

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['build','execute','validate']);p.add_argument('--run',type=Path);a=p.parse_args()
    if a.stage=='build':build()
    else:
        folder=a.run.resolve()
        if folder.parent!=(ROOT/'stage-d/runs/coding').resolve():raise ValueError('invalid folder')
        (execute if a.stage=='execute' else validate)(folder)
