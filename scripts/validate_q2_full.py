"""Trusted Q2 postprocessing: fresh references, immutable certificates and template readback."""
from modelcrew.project_assets import asset_path
import argparse,json,math,uuid,shutil,subprocess
from pathlib import Path
import numpy as np
from scipy.integrate import quad
from scipy.optimize import brentq
from openpyxl import load_workbook
from modelcrew.config import ROOT
from modelcrew.collaboration import sha_file
from modelcrew.docker_executor import DockerExecutor
from modelcrew.mcp_client import executor_root
from scripts.run_d3_minimal import read,write
from scripts.run_q2_full import active
from scripts.reference_2024_a_q1 import solve
PARAMETERS=read(asset_path(ROOT,'stage-a/2024-A-problem-1/parameters.json'))

def artifacts(folder,key):
    sub=folder/key;execution=read(sub/'execution.json');registered=read(sub/'job.json');_,live=DockerExecutor(executor_root()).job(registered['job_id'])
    if registered!=live or execution['job_sha256']!=registered['job_sha256'] or execution['code_sha256']!=sha_file(sub/'generated_solver.py') or execution['authorization']!=registered['authorization'] or execution['cleanup']['removed'] is not True or execution['status']!='succeeded':raise ValueError('provenance changed')
    DockerExecutor(executor_root()).verify_artifacts(execution)
    return {a['name']:executor_root()/a['path'] for a in execution['artifacts']}

def corners(p):
    rods=np.diff(p,axis=0);u=rods/np.linalg.norm(rods,axis=1)[:,None];n=np.column_stack((-u[:,1],u[:,0]));c=(p[:-1]+p[1:])/2
    half=np.full(223,1.1);half[0]=1.705
    verts=c[:,None,:]+half[:,None,None]*u[:,None,:]*np.array([1,1,-1,-1])[None,:,None]+.15*n[:,None,:]*np.array([1,-1,-1,1])[None,:,None]
    return verts,c,u,n,half

def gaps(p):
    verts,c,u,n,half=corners(p);i,j=np.triu_indices(223,2);axes=np.stack((u[i],n[i],u[j],n[j]),axis=1)
    one=np.einsum('pvd,pad->pav',verts[i],axes);two=np.einsum('pvd,pad->pav',verts[j],axes)
    out=np.max(np.maximum(two.min(2)-one.max(2),one.min(2)-two.max(2)),axis=1)
    return out,i,j

def validate(folder):
    meta=read(folder/'run.json');event=read(folder/'collision-event.json');segments=[];results=[];cursor=0.;endkey=None
    plan=read(folder/'primary-plan.json')['partitions']
    for part in plan:
        key=part['key'];files=artifacts(folder,key);r=read(files['partition-result.json'])
        if r['partition_s'][0]!=cursor:raise ValueError('partition gap')
        with np.load(files['safe-segments.npz'],allow_pickle=False) as z:part=z['segments'].copy()
        for a,b,lower in part:
            if a!=cursor or b<=a or lower<=0:raise ValueError('unsafe certificate')
            cursor=float(b)
        if cursor!=r['safe_prefix_end_s']:raise ValueError('safe certificate tail')
        segments.extend(part.tolist());results.append({'key':key,'status':r['status'],'code_sha256':r['code_sha256'],'report_sha256':sha_file(files['partition-result.json']),'execution_sha256':sha_file(folder/key/'execution.json'),'safe_end_s':cursor,'segments':len(part)})
        if r['status']=='FIRST_CONTACT':
            if r!=event:raise ValueError('event report changed')
            endkey=key;lastfiles=files;break
        if r['status']!='SAFE':raise ValueError('unresolved prefix')
        cursor=r['partition_s'][1]
    if endkey is None:raise ValueError('missing event')
    if cursor!=event['first_event_enclosure_s'][0]:raise ValueError('gap before local feature enclosure')
    lo,hi=event['time_interval_s'];t=event['time_estimate_s'];a,b=event['first_event_enclosure_s']
    if not a<=lo<=t<=hi<=b or hi-lo>1e-6:raise ValueError('invalid time bracket')
    if event['feature_derivative_m_s'][1]>=0 or event['other_pairs_min_gap_lower_bound_m']<=0:raise ValueError('local uniqueness not proven')
    (folder/'results').mkdir(exist_ok=True)
    for name,path in lastfiles.items():
        if name!='safe-segments.npz':shutil.copyfile(path,folder/'results'/name)
    with np.load(lastfiles['terminal-state.npz'],allow_pickle=False) as z:data={k:z[k].copy() for k in z.files}
    checks={}
    def check(k,x,limit):checks[k]={'passed':bool(x<=limit),'value':float(x),'limit':limit}
    q,p,v=solve(t,PARAMETERS)
    for name,x,threshold in [('position_m',p,1e-8),('velocity_m_s',v,1e-8),('theta_rad',q,1e-9)]:check('fresh_reference_'+name,np.max(abs(data[name]-x)),threshold)
    pos=data['position_m'];vel=data['velocity_m_s'];speed=data['speed_m_s'];L=np.full(223,1.65);L[0]=2.86
    check('rod_distance_m',np.max(abs(np.linalg.norm(np.diff(pos,axis=0),axis=1)-L)),1e-8)
    check('head_speed_m_s',abs(speed[0]-1),1e-9)
    check('speed_norm_m_s',np.max(abs(np.linalg.norm(vel,axis=1)-speed)),1e-10)
    check('rigid_velocity_m2_s',np.max(abs(np.sum(np.diff(pos,axis=0)*np.diff(vel,axis=0),axis=1))),1e-8)
    fd={}
    for h in [.01,.001,.0001]:
        approx=(3*p-4*solve(t-h,PARAMETERS)[1]+solve(t-2*h,PARAMETERS)[1])/(2*h)
        fd[str(h)]=float(np.max(np.linalg.norm(approx-vel,axis=1)))
    check('independent_left_velocity_fd_m_s',fd['0.001'],1e-5)
    q2,p2,v2=solve(t,PARAMETERS,xtol=5e-15)
    check('tight_root_position_m',np.max(abs(p-p2)),1e-10)
    bspiral=.55/(2*math.pi);init=32*math.pi
    integrated=quad(lambda x:bspiral*math.hypot(x,1),q[0],init,epsabs=1e-10,epsrel=1e-12)[0]
    check('head_arc_quadrature_m',abs(integrated-t),1e-8)
    g,i,j=gaps(pos);k=int(np.argmin(g));pair=[int(i[k]),int(j[k])]
    if pair!=event['active_board_pairs'][0]:raise ValueError('independent active pair mismatch')
    check('contact_sat_gap_m',abs(g[k]),1e-8)
    # Independent finite-segment distance: minimum over vertices and opposite edges.
    verts,*_=corners(pos);one,two=verts[pair[0]],verts[pair[1]]
    def point_segment(pt,x,y):
        d=y-x;r=np.clip(np.dot(pt-x,d)/np.dot(d,d),0,1);return np.linalg.norm(pt-(x+r*d))
    distance=min(point_segment(pt,poly[kk],poly[(kk+1)%4]) for src,poly in [(one,two),(two,one)] for pt in src for kk in range(4))
    check('independent_contact_edge_distance_m',distance,1e-8)
    check('position_enclosure_error_m',event['coordinate_error_bound_m'],5e-7)
    if not np.all(data['position_lower_m']<=p) or not np.all(p<=data['position_upper_m']):raise ValueError('fresh state outside enclosure')
    initial_g,_,_=gaps(solve(0,PARAMETERS)[1])
    if initial_g.min()<=0:raise ValueError('initial contact')
    # Recompute contact scalar with the frozen finite edge/corner identity.
    spec=event['unique_contact_feature']
    def feature(x):
        _,pp,_=solve(x,PARAMETERS);_,c,u,n,h=corners(pp);bb=spec['base'];oo=spec['other'];ax=spec['normal_sign']*(u if spec['axis_kind']==0 else n)[bb];corner=c[oo]+spec['corner_u_sign']*h[oo]*u[oo]+spec['corner_n_sign']*.15*n[oo]
        return float(ax@(corner-c[bb])-(h[bb] if spec['axis_kind']==0 else .15))
    root=brentq(feature,a,b,xtol=5e-14,rtol=4*np.finfo(float).eps)
    check('independent_feature_time_s',abs(root-t),1e-8)
    # Output precision is bounded; separately disclose any rounding-bin ambiguity.
    stable=(np.round(data['position_lower_m'],6)==np.round(data['position_upper_m'],6))
    ambiguity=np.argwhere(~stable).tolist()
    # Freeze actual template output; only three numerical columns filled.
    template=read(folder/'inputs.json')['inputs'];path=next(x['path'] for x in template if x['role']=='required_output_template')
    wb=load_workbook(path);sh=wb[wb.sheetnames[0]]
    structure={'sheetnames':wb.sheetnames,'rows':sh.max_row,'cols':sh.max_column,'first_rows':list(sh.iter_rows(min_row=1,max_row=3,values_only=True))}
    if sh.max_row!=225 or sh.max_column!=4:raise ValueError('unexpected result2 template')
    wb.close()
    write(folder/'workbook-input.json',{'template':path,'values':np.column_stack((pos,speed)).tolist()})
    builder=folder/'export_q2_workbook.mjs'
    if not builder.exists():shutil.copyfile(ROOT/'scripts/export_q2_workbook.mjs',builder)
    subprocess.run(['node',str(builder),str(folder)],check=True)
    target=folder/'results/result2.xlsx'
    out=load_workbook(target,data_only=True);sheet=out[out.sheetnames[0]];values=np.array([[sheet.cell(k+2,c).value for c in [2,3,4]] for k in range(224)]);formats=[sheet.cell(k+2,c).number_format for k in range(224) for c in [2,3,4]];out.close()
    check('xlsx_readback',np.max(abs(values-np.column_stack((pos,speed)))),1e-12)
    if any(f!='0.000000' for f in formats):raise ValueError('format wrong')
    selected=[0,1,51,101,151,201,223]
    write(folder/'results/selected-handles.json',{'index_base':0,'time_interval_s':[lo,hi],'handles':[{'index':k,'x_m':float(pos[k,0]),'y_m':float(pos[k,1]),'speed_m_s':float(speed[k])} for k in selected]})
    np.savez_compressed(folder/'results/continuous-certificate.npz',segments=np.array(segments))
    validation={'scope':'Q2_full','passed':all(x['passed'] for x in checks.values()),'checks':checks,'independent_left_fd_m_s':fd,'initial_min_gap_m':float(initial_g.min()),'first_contact_event':event,'partition_evidence':results,'safe_segments':len(segments),'safe_prefix_end_s':cursor,'continuous_certificate':'positive outward interval bounds over every safe segment, plus unique decreasing finite-edge feature over final interval; independent P2 source review still required','template_structure':structure,'six_decimal_position_rounding_ambiguous_coordinates':ambiguity,'six_decimal_display_bound_m':5e-7,'generated_code_executed_on_host':False,'new_final_answer_user_approval':False,'full_contract_checks':{key:'unknown_pending_independent_P2' for key in [c['id'] for c in read(folder/'contract.json')['checks']]}}
    write(folder/'validation.json',validation)
    if not validation['passed']:raise ValueError('numeric validation failed')
    print(json.dumps({'passed':True,'time_interval_s':[lo,hi],'pair':pair,'checks':checks,'rounding_ambiguous':ambiguity,'safe_segments':len(segments)},ensure_ascii=False),flush=True)
    return validation
if __name__=='__main__':validate(active())
