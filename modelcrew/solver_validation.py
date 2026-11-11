"""Independent external validation of a v2 container's numerical artifacts.

The model report is evidence, never the sole basis for pass. Recomputations use
human reference solve plus independently recomputed geometry and workbook reads.
"""
from pathlib import Path
import json,hashlib,math
import numpy as np
from scipy.integrate import quad
from openpyxl import load_workbook
from .contracts import digest
from .config import ROOT

class ResultError(ValueError):pass

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def validate_run(run,contract):
    run=Path(run).resolve();base=(ROOT/'stage-b/runs').resolve()
    if run.parent!=base or run.is_symlink():raise ResultError('Run path outside stage-b/runs')
    def checked(relative):
        p=run/relative
        if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(run):raise ResultError('Invalid artifact path')
        return p
    files=['contract.json','generated_solver.py','review.json','execution.json','container-inspect.json','output/checks.json','output/result1.xlsx','output/trajectories.npz','fault-probes/fault-probes.json','fault-probe-execution.json','metadata.json']
    paths={f:checked(f) for f in files}
    if sum(p.stat().st_size for p in paths.values())>40*1024*1024:raise ResultError('Oversized run')
    load=lambda name:json.loads(paths[name].read_text(encoding='utf-8-sig'))
    contract_hash=digest(contract);code_hash=sha(paths['generated_solver.py'])
    if digest(load('contract.json'))!=contract_hash:raise ResultError('Contract mismatch')
    review=load('review.json');execution=load('execution.json');report=load('output/checks.json')
    if review.get('code_sha256')!=code_hash or review.get('contract_sha256')!=contract_hash or not review.get('security_review',{}).get('passed') or not review.get('math_review',{}).get('passed'):raise ResultError('Manual review binding mismatch')
    if execution.get('exit_code')!=0 or execution.get('status')!='completed':raise ResultError('Solver execution failed')
    inspections=load('container-inspect.json')
    if not isinstance(inspections,list) or len(inspections)!=1:raise ResultError('Missing container inspection')
    inspect=inspections[0];host=inspect['HostConfig']
    if inspect['State']['ExitCode']!=0 or host['NetworkMode']!='none' or not host['ReadonlyRootfs']:raise ResultError('Container isolation/exit invalid')
    mount=next((m for m in inspect['Mounts'] if m['Destination']=='/work/solver.py'),None)
    if not mount or mount['RW'] or Path(mount['Source']).resolve()!=paths['generated_solver.py'].resolve():raise ResultError('Container code mount mismatch')
    if report.get('contract_sha256')!=contract_hash or report.get('code_sha256')!=code_hash:raise ResultError('Model report binding mismatch')
    fault=load('fault-probes/fault-probes.json');fault_execution=load('fault-probe-execution.json')
    if fault.get('code_sha256')!=code_hash or not fault.get('passed') or fault_execution.get('exit_code')!=0:raise ResultError('Missing or failed fault probes')
    meta=load('metadata.json')
    if meta.get('contract_sha256')!=contract_hash or meta.get('contract_version')!=2:raise ResultError('Generation contract binding mismatch')
    ids={c['id'] for c in contract['checks']}
    if set(report.get('checks',{}))!=ids:raise ResultError('Model report check IDs incomplete')
    for key,item in report['checks'].items():
        if item.get('status')!='passed' or not item.get('evidence'):raise ResultError('Model report not passed or missing evidence: '+key)
    from scripts.reference_2024_a_q1 import solve as reference_solve,arc
    parameters=json.loads((ROOT/'stage-a/2024-A-problem-1/parameters.json').read_text(encoding='utf-8'))
    # Reference comparator is case-specific: don't use it for changed physical inputs.
    vals={p['id']:p['value'] for p in contract['parameters']}
    frozen={'pitch':.55,'head_gap':2.86,'body_gap':1.65,'head_speed':1,'initial_turns':16,'handle_count':224,'end_time':300}
    if any(vals.get(k)!=v for k,v in frozen.items()):raise ResultError('Reference supports only original physical inputs')
    checks={}
    def check(name,value,limit):checks[name]={'passed':bool(value<=limit),'value':float(value),'limit':limit}
    with np.load(paths['output/trajectories.npz'],allow_pickle=False) as data:
        expected={'time_s':(301,),'theta_rad':(301,224),'position_m':(301,224,2),'velocity_m_s':(301,224,2),'speed_m_s':(301,224)}
        arrays={}
        for name,shape in expected.items():
            x=data[name]
            if x.shape!=shape or not np.all(np.isfinite(x)):raise ResultError('Invalid '+name)
            arrays[name]=x.copy()
    times=arrays['time_s'];theta=arrays['theta_rad'];pos=arrays['position_m'];vel=arrays['velocity_m_s'];speed=arrays['speed_m_s']
    if not np.array_equal(times,np.arange(301)):raise ResultError('Invalid time axis')
    b=.55/(2*math.pi);r=b*theta
    formula=np.stack((r*np.cos(theta),r*np.sin(theta)),axis=2)
    check('position_from_theta',np.max(np.abs(pos-formula)),1e-8)
    check('head_speed',np.max(np.abs(speed[:,0]-1)),1e-9)
    check('initial_position',np.linalg.norm(pos[0,0]-[8.8,0]),1e-9)
    checks['theta_order_and_clockwise']={'passed':bool(np.all(np.diff(theta,axis=1)>0) and np.all(np.diff(theta,axis=0)<0) and vel[0,0,1]<0)}
    delta=np.diff(theta,axis=1);rprev=r[:,:-1];L=np.full(223,1.65);L[0]=2.86
    square=(b*delta)**2+4*rprev*(rprev+b*delta)*np.sin(delta/2)**2
    check('stable_chord_squared_residual',np.max(np.abs(square-L**2)),1e-10)
    rod=np.diff(pos,axis=1)
    check('rod_distance',np.max(np.abs(np.linalg.norm(rod,axis=2)-L)),1e-8)
    # f'(delta)>0 for 0<delta<pi,r>0,b>0: each derivative term nonnegative,
    # and 2*b^2*delta > 0. Also f(0)<0 and f(pi)>0 certify first root.
    bracket_upper=(b*math.pi)**2+4*rprev*(rprev+b*math.pi)-L**2
    checks['monotone_first_root_bracket']={'passed':bool(np.all((delta>0)&(delta<math.pi)) and np.all(bracket_upper>0) and np.all(rprev>0)),'proof':'f_prime=2b²δ+4rb sin²(δ/2)+2r(r+bδ)sinδ >0 on (0,pi)'}
    tangent=b*np.stack((np.cos(theta)-theta*np.sin(theta),np.sin(theta)+theta*np.cos(theta)),axis=2)
    denominator=np.sum(rod*tangent[:,1:],axis=2);minimum=float(np.min(np.abs(denominator)))
    checks['denominator_guard_observed']={'passed':minimum>1e-10,'minimum_abs_m2':minimum,'threshold_m2':1e-10,'minimum_index':list(map(int,np.unravel_index(np.argmin(np.abs(denominator)),denominator.shape))),'branch_test':'Separate fault probe triggered guard and verified nonzero exit with unknown checks.'}
    check('velocity_speed_consistency',np.max(np.abs(np.linalg.norm(vel,axis=2)-speed)),1e-10)
    check('rigid_velocity_constraint',np.max(np.abs(np.sum(rod*np.diff(vel,axis=1),axis=2))),1e-8)
    check('velocity_tangent',np.max(np.abs(tangent[:,:,0]*vel[:,:,1]-tangent[:,:,1]*vel[:,:,0])),1e-8)
    arc_error=[];quad_errors=[]
    for t in range(301):
        integral,err=quad(lambda q:b*math.hypot(q,1),theta[t,0],32*math.pi,epsabs=1e-10,epsrel=1e-12)
        arc_error.append(abs(integral-t));quad_errors.append(err)
    check('head_arc_quadrature',max(arc_error),1e-8)
    fd={}
    for h in [1e-2,1e-3,1e-4]:
        errors=[]
        for t in [1,60,120,180,240,299]:
            v=(reference_solve(t+h,parameters)[1]-reference_solve(t-h,parameters)[1])/(2*h)
            errors.append(float(np.max(np.linalg.norm(v-vel[t],axis=1))))
        endpoints=[]
        for t,d in [(0,1),(300,-1)]:
            p0=reference_solve(t,parameters)[1];p1=reference_solve(t+d*h,parameters)[1];p2=reference_solve(t+2*d*h,parameters)[1]
            v=d*(-3*p0+4*p1-p2)/(2*h);endpoints.append(float(np.max(np.linalg.norm(v-vel[t],axis=1))))
        fd[str(h)]={'interior_max_m_s':max(errors),'endpoint_max_m_s':max(endpoints)}
    check('velocity_finite_difference',max(fd['0.001'].values()),1e-5)
    samples=[]
    for t in [0,60,120,180,240,300]:
        default=reference_solve(t,parameters);refined=reference_solve(t,parameters,xtol=5e-15)
        samples.append({'time_s':t,'position_difference_m':float(np.max(np.abs(default[1]-refined[1]))),'velocity_difference_m_s':float(np.max(np.abs(default[2]-refined[2]))),'v2_position_vs_refined_m':float(np.max(np.abs(pos[t]-refined[1])))})
    check('reference_refinement',max(x['position_difference_m'] for x in samples),1e-10)
    check('sample_position_vs_refined_reference',max(x['v2_position_vs_refined_m'] for x in samples),1e-6)
    ref=ROOT/'stage-a/2024-A-problem-1/runs/reference-20261101T124835482890Z/trajectories.npz'
    with np.load(ref,allow_pickle=False) as known:
        for name in ['position_m','velocity_m_s','speed_m_s']:check(name+'_reference_difference',np.max(np.abs(arrays[name]-known[name])),1e-6)
    workbook=load_workbook(paths['output/result1.xlsx'],read_only=True,data_only=True)
    inputfile=next(x for x in contract['inputs'] if x['role']=='required_output_template')
    templatepath=Path(inputfile['path'])
    if sha(templatepath)!=inputfile['sha256'].lower():raise ResultError('Template hash changed')
    template=load_workbook(templatepath,read_only=True,data_only=True)
    if workbook.sheetnames!=template.sheetnames:raise ResultError('Sheet names changed')
    for title,values in [('位置',pos.transpose(1,2,0).reshape(448,301)),('速度',speed.T)]:
        ws=workbook[title];original=template[title]
        if (ws.max_row,ws.max_column)!=(values.shape[0]+1,302):raise ResultError('Wrong workbook dimensions')
        if [c.value for c in ws[1]]!=[c.value for c in original[1]]:raise ResultError('Time labels changed')
        rows=list(ws.iter_rows());orows=list(original.iter_rows())
        if [row[0].value for row in rows]!=[row[0].value for row in orows]:raise ResultError('Row labels changed')
        cells=[row[1:] for row in rows[1:]]
        exported=np.array([[c.value for c in row] for row in cells],dtype=float)
        if not np.all(np.isfinite(exported)):raise ResultError('Nonfinite workbook values')
        check(title+'_roundtrip',np.max(np.abs(exported-values)),5.00001e-7)
        checks[title+'_format']={'passed':all(c.number_format=='0.000000' for row in cells for c in row)}
    workbook.close();template.close()
    checks['fault_probe_denominator']={'passed':bool(fault['checks']['near_zero_guard_fail_closed']['passed'])}
    checks['fault_probe_bracket']={'passed':bool(fault['checks']['impossible_bracket_fail_closed']['passed'])}
    passed=all(x['passed'] for x in checks.values())
    result={'passed':passed,'contract_sha256':contract_hash,'code_sha256':code_hash,'validation_type':'independent_v2_artifact_checks_plus_manual_review','model_report_status':'all_12_reported_passed','checks':checks,'finite_difference':fd,'root_refinement_samples':samples,'quadrature':{'epsabs':1e-10,'epsrel':1e-12,'max_error_estimate':max(quad_errors)},'limitations':['Fault probes intentionally alter threshold/gap to exercise abort paths, and are not physical-case predictions.','Independent finite differences use reviewed reference solver; model own finite-difference report is checked separately.','Not a proof of general model correctness or robustness on other problems.']}
    (run/'independent-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed:raise ResultError('Independent numeric checks failed')
    paths['independent-validation.json']=run/'independent-validation.json'
    artifacts=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'role':'real_solver_evidence'} for p in paths.values()]
    return result,artifacts
