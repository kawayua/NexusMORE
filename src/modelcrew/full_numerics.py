"""Independent, case-specific D4 numeric and workbook validation; no generated imports."""
from .project_assets import asset_path
import json,math
from pathlib import Path
import numpy as np
from scipy.integrate import quad
from openpyxl import load_workbook
from modelcrew.config import ROOT
from modelcrew.collaboration import sha_file

SHAPES={'time_s':(301,),'theta_rad':(301,224),'position_m':(301,224,2),'velocity_m_s':(301,224,2),'speed_m_s':(301,224)}


def load_arrays(path):
    with np.load(path,allow_pickle=False) as data:
        if set(data.files)!=set(SHAPES):raise ValueError('Unexpected array members')
        arrays={key:data[key].copy() for key in SHAPES}
    if any(a.shape!=SHAPES[k] or a.dtype.kind not in 'fi' or not np.all(np.isfinite(a)) for k,a in arrays.items()):
        raise ValueError('Invalid full arrays')
    if not np.array_equal(arrays['time_s'],np.arange(301)):raise ValueError('Invalid full time axis')
    return arrays


def numeric_checks(arrays, contract, self_report, *, compare_reference=True):
    values={p['id']:p['value'] for p in contract['parameters']}
    expected={'pitch':.55,'head_gap':2.86,'body_gap':1.65,'head_speed':1,'initial_turns':16,'handle_count':224,'end_time':300}
    if any(values.get(k)!=v for k,v in expected.items()):raise ValueError('Independent comparator supports original Q1 parameters only')
    if any(a.shape!=SHAPES[k] or not np.all(np.isfinite(a)) for k,a in arrays.items()):raise ValueError('Invalid full arrays')
    if not np.array_equal(arrays['time_s'],np.arange(301)):raise ValueError('Invalid time axis')
    q,p,v,s=tuple(arrays[k] for k in ['theta_rad','position_m','velocity_m_s','speed_m_s'])
    b=.55/(2*math.pi);r=b*q;d=np.diff(p,axis=1);delta=np.diff(q,axis=1)
    lengths=np.full(223,1.65);lengths[0]=2.86
    tangent=b*np.stack((np.cos(q)-q*np.sin(q),np.sin(q)+q*np.cos(q)),axis=2)
    denom=np.sum(d*tangent[:,1:],axis=2)
    checks={};series={}
    def check(key,value,limit,unit):checks[key]={'passed':bool(value<=limit),'value':float(value),'limit':float(limit),'unit':unit}
    check('position_formula',np.max(np.abs(p-r[:,:,None]*np.stack((np.cos(q),np.sin(q)),axis=2))),1e-9,'m')
    series['rod_distance_error_m']=np.max(np.abs(np.linalg.norm(d,axis=2)-lengths),axis=1).tolist()
    check('rod_distance',max(series['rod_distance_error_m']),1e-8,'m')
    check('head_speed',np.max(np.abs(s[:,0]-1)),1e-9,'m/s')
    check('speed_consistency',np.max(np.abs(s-np.linalg.norm(v,axis=2))),1e-10,'m/s')
    check('initial_position',np.linalg.norm(p[0,0]-[8.8,0]),1e-9,'m')
    check('rigid_velocity',np.max(np.abs(np.sum(d*np.diff(v,axis=1),axis=2))),1e-8,'m^2/s')
    check('tangent_velocity',np.max(np.abs(tangent[:,:,0]*v[:,:,1]-tangent[:,:,1]*v[:,:,0])),1e-8,'m^2/s')
    chord=(b*delta)**2+4*r[:,:-1]*(r[:,:-1]+b*delta)*np.sin(delta/2)**2-lengths**2
    check('stable_chord_squared',np.max(np.abs(chord)),1e-10,'m^2')
    upper=(2*r[:,:-1]+b*math.pi)**2-lengths**2
    checks['first_outward_branch']={'passed':bool(np.all((delta>0)&(delta<math.pi)) and np.all(upper>0) and np.all(r>0)),
        'proof':'Fprime=2b^2*delta+4rb*sin(delta/2)^2+2r(r+b*delta)*sin(delta)>0 on (0,pi), r,b>0'}
    checks['theta_order_direction']={'passed':bool(np.all(np.diff(q,axis=0)<0) and np.all(delta>0) and v[0,0,1]<0)}
    minimum=float(np.min(np.abs(denom)))
    checks['denominator_margin']={'passed':minimum>1e-10,'minimum_abs_m2':minimum,'threshold_m2':1e-10,
        'minimum_index':[int(i) for i in np.unravel_index(np.argmin(np.abs(denom)),denom.shape)]}
    series['min_denominator_m2']=np.min(np.abs(denom),axis=1).tolist()
    series['min_bracket_upper_m2']=np.min(upper,axis=1).tolist()
    errors=[];estimates=[]
    for t in range(301):
        val,err=quad(lambda x:b*math.hypot(x,1),q[t,0],32*math.pi,epsabs=1e-10,epsrel=1e-12)
        errors.append(abs(val-t));estimates.append(err)
    check('head_arc_integration',max(errors),1e-8,'m')
    series['head_arc_error_m']=errors
    refinement=self_report.get('root_refinement',[])
    if [x.get('time_s') for x in refinement]!=[0,60,120,180,240,300] or any(x.get('xtol')!=5e-15 for x in refinement):
        raise ValueError('Missing actual root-refinement samples')
    check('solver_root_refinement',max(x['max_position_difference_m'] for x in refinement),1e-10,'m')
    fd={}
    if compare_reference:
        from scripts.reference_2024_a_q1 import solve
        parameters=json.loads((asset_path(ROOT,'stage-a/2024-A-problem-1/parameters.json')).read_text(encoding='utf-8'))
        fresh=[solve(t,parameters) for t in range(301)]
        for name,index in [('theta_rad',0),('position_m',1),('velocity_m_s',2)]:
            check('fresh_reference_'+name,np.max(np.abs(arrays[name]-np.stack([x[index] for x in fresh]))),1e-6,'rad' if index==0 else ('m' if index==1 else 'm/s'))
        for h in [.01,.001,.0001]:
            inside=[];end=[]
            for t in [1,60,120,180,240,299]:
                approx=(solve(t+h,parameters)[1]-solve(t-h,parameters)[1])/(2*h)
                inside.append(float(np.max(np.linalg.norm(approx-v[t],axis=1))))
            for t,direction in [(0,1),(300,-1)]:
                approx=direction*(-3*fresh[t][1]+4*solve(t+direction*h,parameters)[1]-solve(t+2*direction*h,parameters)[1])/(2*h)
                end.append(float(np.max(np.linalg.norm(approx-v[t],axis=1))))
            fd[str(h)]={'interior_max_m_s':max(inside),'endpoint_max_m_s':max(end)}
        check('independent_velocity_fd',max(fd['0.001'].values()),1e-5,'m/s')
        samples=[]
        for t in [0,60,120,180,240,300]:
            refined=solve(t,parameters,xtol=5e-15)
            samples.append(float(np.max(np.abs(p[t]-refined[1]))))
        check('refined_reference_position',max(samples),1e-6,'m')
    result={'passed':all(c['passed'] for c in checks.values()),'checks':checks,'series':series,
        'finite_difference':fd,'quadrature':{'epsabs':1e-10,'epsrel':1e-12,'max_estimated_error_m':float(max(estimates))},
        'scope':'all_301_times_224_handles','fresh_reference_computation':compare_reference,
        'generated_code_executed_on_host':False}
    return result


def workbook_checks(path, arrays, template):
    if sha_file(template['path'])!=template['sha256']:raise ValueError('Template hash changed')
    actual=load_workbook(path,read_only=True,data_only=True)
    original=load_workbook(template['path'],read_only=True,data_only=True)
    checks={}
    try:
        if actual.sheetnames!=original.sheetnames:raise ValueError('Workbook sheet names changed')
        for title,expected in [('位置',arrays['position_m'].transpose(1,2,0).reshape(448,301)),('速度',arrays['speed_m_s'].T)]:
            a=actual[title];o=original[title]
            if (a.max_row,a.max_column)!=(expected.shape[0]+1,302):raise ValueError('Workbook shape mismatch')
            arows=list(a.iter_rows());orows=list(o.iter_rows())
            if [c.value for c in arows[0]]!=[c.value for c in orows[0]]:raise ValueError('Workbook time labels changed')
            if [row[0].value for row in arows]!=[row[0].value for row in orows]:raise ValueError('Workbook handle labels changed')
            cells=[row[1:] for row in arows[1:]]
            values=np.array([[c.value for c in row] for row in cells],dtype=float)
            if not np.all(np.isfinite(values)):raise ValueError('Nonfinite spreadsheet output')
            error=float(np.max(np.abs(values-expected)))
            checks[title]={'passed':error<=5.00001e-7 and all(c.number_format=='0.000000' for row in cells for c in row),
                'max_rounding_error':error,'limit':5.00001e-7,'shape':[a.max_row,a.max_column],'labels_preserved':True,'six_decimal_format':all(c.number_format=='0.000000' for row in cells for c in row)}
    finally:actual.close();original.close()
    return {'passed':all(c['passed'] for c in checks.values()),'checks':checks,'authoring':'trusted_host_openpyxl_template_fill','artifact_tool_available':False}
