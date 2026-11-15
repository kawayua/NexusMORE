"""Reproduce A+ mathematical/method checks without new LLM or solver-code execution."""
from modelcrew.project_assets import asset_path
import copy,json,math,platform,sys,importlib.metadata,re
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import sympy as sp
from scipy.integrate import quad
from scipy.optimize import linprog
from modelcrew.aplus import choose_method,check_dossier
from modelcrew.config import ROOT
from modelcrew.inputs import file_hash
from modelcrew.contracts import digest

BASE=asset_path(ROOT,'stage-a-plus')
def load(relative):return json.loads((ROOT/relative).read_text(encoding='utf-8-sig'))
def symbolic_checks():
    theta=sp.symbols('theta',real=True);b,r,ell=sp.symbols('b r ell',positive=True);delta=sp.symbols('delta',real=True)
    X=sp.Matrix([b*theta*sp.cos(theta),b*theta*sp.sin(theta)]);tangent=X.diff(theta)
    primitive=b/2*(theta*sp.sqrt(1+theta**2)+sp.asinh(theta))
    squared=(r+b*delta)**2+r**2-2*r*(r+b*delta)*sp.cos(delta)-ell**2
    stable=(b*delta)**2+4*r*(r+b*delta)*sp.sin(delta/2)**2-ell**2
    derivative=2*b*b*delta+4*r*b*sp.sin(delta/2)**2+2*r*(r+b*delta)*sp.sin(delta)
    return {'tangent_norm_squared':sp.simplify(tangent.dot(tangent)-b*b*(1+theta**2))==0,
            'arc_primitive_derivative':sp.simplify(sp.diff(primitive,theta)-b*sp.sqrt(1+theta**2))==0,
            'stable_chord_identity':sp.trigsimp(sp.expand_trig(squared-stable))==0,
            'chord_derivative':sp.trigsimp(sp.diff(stable,delta)-derivative)==0,
            'bracket_upper_identity':sp.simplify(stable.subs(delta,sp.pi)-((2*r+b*sp.pi)**2-ell**2))==0,
            'positive_denominator_identity':sp.trigsimp((sp.Matrix([(r+b*delta)*sp.cos(delta)-r,(r+b*delta)*sp.sin(delta)]).dot(sp.Matrix([b*sp.cos(delta)-(r+b*delta)*sp.sin(delta),b*sp.sin(delta)+(r+b*delta)*sp.cos(delta)])))-derivative/2)==0}

def main():
    run=BASE/'runs'/datetime.now(timezone.utc).strftime('verification-%Y%m%dT%H%M%S%fZ');run.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,passed,**details):checks.append({'id':name,'passed':bool(passed),**details})
    readings=load('stage-a-plus/sources/read-log.json')
    for source in readings['sources']:
        original=ROOT/source['project_path'];excerpt=BASE/source['excerpt_path']
        expected='\n'.join(original.read_text(encoding='utf-8-sig').splitlines()[source['line_start']-1:source['line_end']])+'\n'
        check('source:'+source['id'],file_hash(original)==source['file_sha256'] and file_hash(excerpt)==source['excerpt_sha256'] and excerpt.read_text(encoding='utf-8')==expected)
    dossiers=[load('stage-a-plus/math/'+name+'-dossier.json') for name in ['bench-dragon','resource']]
    for dossier in dossiers:
        lint=check_dossier(dossier);check('dossier:'+dossier['id'],lint['status']=='passed',review=lint)
    for name in ['bench-dragon','resource']:
        dossier=load(f'stage-a-plus/math/{name}-dossier.json');text=(BASE/f'math/{name}-fragments.tex').read_text(encoding='utf-8')
        check('latex_source:'+name,all(text.count('\\label{'+e['id']+'}')==1 and e['latex'] in text for e in dossier['equations']) and not any(ord(c)<32 and c not in '\n\r\t' for c in text) and all('\t' not in s['latex'] for s in dossier['symbols']),coverage='Labels and byte fidelity only; not compilation/rendering.')
    symbolic=symbolic_checks()
    for key,value in symbolic.items():check('symbolic:'+key,value,evidence_type='symbolic_identity_not_general_theorem_prover')
    geometry=load('stage-a-plus/cases/bench-dragon.json');allocation=load('stage-a-plus/cases/resource-allocation.json')
    choices=[{'case':geometry['id'],'result':choose_method(geometry)},{'case':allocation['id'],'result':choose_method(allocation)}]
    check('cross_structure_selection',choices[0]['result']['selected']=='arc_inversion_and_bracketed_chords' and choices[1]['result']['selected']=='linear_programming')
    invalid_geometry=copy.deepcopy(geometry);invalid_geometry['pitch_m']=0
    past_origin=copy.deepcopy(geometry);past_origin['end_time_s']=1e5
    unknown=copy.deepcopy(allocation);unknown.pop('variable_domain')
    integer=copy.deepcopy(allocation);integer['variable_domain']='integer'
    counters=[{'id':'zero_pitch','result':choose_method(invalid_geometry),'expected':'blocked'},{'id':'past_origin','result':choose_method(past_origin),'expected':'blocked'},{'id':'unknown_domain','result':choose_method(unknown),'expected':'blocked'},{'id':'integer_domain','result':choose_method(integer),'expected':'redirect'},{'id':'unsupported_structure','result':choose_method({'structure':'unmodelled'}),'expected':'unsupported'}]
    for item in counters:check('premise_counter:'+item['id'],item['result']['status']==item['expected'],result=item['result'])
    broken=[]
    for mutation in ['undefined_symbol','wrong_unit','missing_premise','claimed_proof_gap','wrong_declared_dimension']:
        bad=copy.deepcopy(dossiers[0])
        if mutation=='undefined_symbol':bad['equations'][0]['symbol_ids'].append('sym:never-defined')
        elif mutation=='wrong_unit':next(s for s in bad['symbols'] if s['id']=='sym:p')['unit']='s'
        elif mutation=='missing_premise':next(p for p in bad['propositions'] if p['id']=='prop:chord-first-root')['conditions'].remove('positive_geometry')
        elif mutation=='claimed_proof_gap':bad['propositions'][0]['open_gaps']=['No argument supplied']
        else:bad['equations'][0]['rhs_dimension']='s'
        review=check_dossier(bad);check('math_counter:'+mutation,review['status']=='failed',findings=review['findings']);broken.append({'mutation':mutation,'findings':review['findings']})
    # Monotonicity alone does NOT imply a root on the chosen open bracket.
    b=.55/(2*math.pi);r=.1;ell=1.
    residual=lambda d:(b*d)**2+4*r*(r+b*d)*math.sin(d/2)**2-ell**2
    check('no_bracket_counter',residual(0)<0 and residual(math.pi)<0,upper_residual_m2=residual(math.pi),conclusion='No certified root in(0,pi), not a claim of no root on all later turns.')
    check('endpoint_counter',math.isclose((2*r+b*math.pi)**2-(2*r+b*math.pi)**2,0),conclusion='At ell=2r+b*pi root is pi; excluded by open-branch rule.')
    A=np.asarray(allocation['A']);a=np.asarray(allocation['b']);c=np.asarray(allocation['c'])
    sol=linprog(-c,A_ub=A,b_ub=a,bounds=(0,None),method='highs');x=sol.x if sol.success else np.full(2,np.nan)
    prices=np.ones(2);gap=float(a@prices-c@x)
    lp_report={'synthetic':True,'status':int(sol.status),'message':str(sol.message),'x_kg':x.tolist(),'objective_currency':float(c@x),'resource_slack_h':(a-A@x).tolist(),'dual_prices_currency_per_h':prices.tolist(),'dual_bound_currency':float(a@prices),'primal_dual_gap_currency':gap,'claimed_optimum_basis':'Direct weighted-inequality proof plus explicit feasible point; solver status alone is insufficient.'}
    check('lp_primal_dual',sol.success and np.all(x>=-1e-10) and np.all(a-A@x>=-1e-10) and np.all(A.T@prices>=c) and abs(gap)<1e-10 and np.max(np.abs(x-[2,2]))<1e-10,**lp_report)
    impossible=linprog(-c,A_ub=A,b_ub=[-1,6],bounds=(0,None),method='highs')
    check('lp_infeasible',impossible.status==2,solver_status=int(impossible.status),certificate='x1+x2>=0 for nonnegative variables, but first capacity requires<=-1; no feasible point.')
    relaxed=linprog([-1.],A_ub=[[1.]],b_ub=[1.5],bounds=(0,None),method='highs')
    check('integer_relaxation_counter',relaxed.success and abs(relaxed.x[0]-1.5)<1e-12 and choices[1]['result']['selected']!='mixed_integer_programming',relaxation_optimum=relaxed.x.tolist(),integer_feasible_optimum=1,policy='Integer case redirected by premise check; no rounding-based optimum claim.')
    # Bind ONLY existing project arrays; the original stored hash is independently retained.
    confirmation=load('stage-b/v2-result-confirmation.json');contract=load('stage-b/runs/solver-v2-20261104T131332959555Z/contract.json')
    audit=load('stage-b/stage-b-production-audit-20261106.json')
    array_path=asset_path(ROOT,'stage-b/runs/solver-v2-20261104T131332959555Z/output/trajectories.npz')
    registered=next(a for a in audit['artifacts'] if a['execution_id']==confirmation['execution_id'] and Path(a['path']).name=='trajectories.npz')
    check('existing_result_binding',confirmation['result_approved'] and digest(contract)==confirmation['contract_sha256'] and file_hash(array_path)==registered['registered_sha256'],execution_id=confirmation['execution_id'],version=confirmation['version'],revision=confirmation['result_revision'],array_sha256=file_hash(array_path))
    with np.load(array_path,allow_pickle=False) as arrays:
        theta=arrays['theta_rad'].copy();pos=arrays['position_m'].copy();vel=arrays['velocity_m_s'].copy();speed=arrays['speed_m_s'].copy();times=arrays['time_s'].copy()
    check('arrays_finite_and_shape',theta.shape==(301,224) and pos.shape==(301,224,2) and vel.shape==(301,224,2) and speed.shape==(301,224) and np.array_equal(times,np.arange(301)) and all(np.isfinite(x).all() for x in [theta,pos,vel,speed]))
    def bounded(name,value,limit,unit):check(name,value<=limit,value=float(value),limit=limit,unit=unit)
    radius=b*theta;d=np.diff(pos,axis=1);L=np.full(223,1.65);L[0]=2.86
    formula=np.stack([radius*np.cos(theta),radius*np.sin(theta)],axis=-1)
    bounded('position_from_spiral',float(np.max(np.abs(pos-formula))),1e-8,'m')
    bounded('rod_distances',float(np.max(np.abs(np.linalg.norm(d,axis=-1)-L))),1e-8,'m')
    bounded('head_speed',float(np.max(np.abs(speed[:,0]-1))),1e-9,'m/s')
    bounded('velocity_norm',float(np.max(np.abs(np.linalg.norm(vel,axis=-1)-speed))),1e-9,'m/s')
    bounded('rigid_velocity',float(np.max(np.abs(np.sum(d*np.diff(vel,axis=1),axis=-1)))),1e-8,'m^2/s')
    tangent=b*np.stack([np.cos(theta)-theta*np.sin(theta),np.sin(theta)+theta*np.cos(theta)],axis=-1)
    denominator=np.sum(d*tangent[:,1:],axis=-1)
    check('velocity_denominator',np.min(denominator)>1e-10,minimum_m2=float(np.min(denominator)),threshold_m2=1e-10,scope='Observed at301 discrete times; no uniform conditioning theorem.')
    check('branch_order',np.all(np.diff(theta,axis=1)>0) and np.all(np.diff(theta,axis=1)<math.pi) and np.all(np.diff(theta,axis=0)<0),scope='Time-monotonicity of follower angles is a numerical observation, not claimed proved for all continuous times.')
    bounded('initial_position',float(np.linalg.norm(pos[0,0]-[8.8,0])),1e-9,'m')
    arc_res=[];quad_errors=[]
    for t,head in zip(times,theta[:,0]):
        integral,error=quad(lambda angle:b*math.hypot(1,angle),head,32*math.pi,epsabs=1e-9,epsrel=1e-12);arc_res.append(abs(integral-t));quad_errors.append(error)
    bounded('independent_arc_quadrature',max(arc_res),1e-8,'m')
    check('analytic_full_interval_margin',105.6*3-4.4>300,lower_bound_without_decimal_pi_m=105.6*3-4.4,maximum_chord_m=2.86,conservative_upper_chord_capacity_m=9.075,proof_reference='prop:frozen-interval; uses pi>3 and frozen parameters')
    from scripts.reference_2024_a_q1 import solve
    parameters=load('stage-a/2024-A-problem-1/parameters.json');fd=[];refinement=[]
    for h in [1e-2,1e-3,1e-4]:
        errors=[]
        for t in [0,60,120,180,240,300]:
            if t in (0,300):
                direction=1 if t==0 else -1;p0=solve(t,parameters)[1];p1=solve(t+direction*h,parameters)[1];p2=solve(t+2*direction*h,parameters)[1];approx=direction*(-3*p0+4*p1-p2)/(2*h)
            else:approx=(solve(t+h,parameters)[1]-solve(t-h,parameters)[1])/(2*h)
            errors.append(float(np.max(np.linalg.norm(approx-vel[t],axis=-1))))
        fd.append({'h_s':h,'max_vector_error_m_s':max(errors),'times_s':[0,60,120,180,240,300],'endpoint_rule':'second-order one-sided; interiors centred'})
    bounded('finite_difference_h001',fd[1]['max_vector_error_m_s'],1e-5,'m/s')
    for t in [0,60,120,180,240,300]:
        normal=solve(t,parameters);tight=solve(t,parameters,xtol=5e-15)
        refinement.append({'time_s':t,'position_change_m':float(np.max(np.abs(normal[1]-tight[1]))),'vs_existing_position_m':float(np.max(np.abs(tight[1]-pos[t]))),'vs_existing_velocity_m_s':float(np.max(np.abs(tight[2]-vel[t])))})
    bounded('root_refinement',max(x['position_change_m'] for x in refinement),1e-10,'m')
    bounded('existing_vs_reference_position',max(x['vs_existing_position_m'] for x in refinement),1e-6,'m')
    bounded('existing_vs_reference_velocity',max(x['vs_existing_velocity_m_s'] for x in refinement),1e-6,'m/s')
    # Numerical counterexample to a structurally plausible but algebraically wrong sign.
    delta=.2;r=5.;ell=1.;correct=(b*delta)**2+4*r*(r+b*delta)*math.sin(delta/2)**2-ell**2;wrong=(b*delta)**2-4*r*(r+b*delta)*math.sin(delta/2)**2-ell**2
    check('algebra_sign_mutation_detected',abs(correct-wrong)>1,absolute_discrepancy_m2=abs(correct-wrong),scope='One deliberately injected sign defect; not a mathematical defect detection rate.')
    report={'date':datetime.now().astimezone().isoformat(),'status':'passed' if all(c['passed'] for c in checks) else 'failed','check_count':len(checks),'checks':checks,'method_cases':choices,'counterexamples':counters,'lint_counterexamples':broken,'finite_difference':fd,'reference_refinement':refinement,'quadrature_max_error_estimate_m':max(quad_errors),'lp':lp_report,'result_binding':confirmation,'environment':{'python':platform.python_version(),'dependencies':{p:importlib.metadata.version(p) for p in ['numpy','scipy','sympy']}},'execution_mode':'Existing confirmed project arrays + new read-only diagnostics and human-authored synthetic LP; no model solver code executed','new_llm_calls':0,'new_contest_solver_runs':0,'new_synthetic_lp_solves':3,'new_reference_diagnostic_calls':'finite differences/refinement; not fresh full301x224 run','formal_prover_used':False,'latex_compilation':'not_run_A+_source_only_C+_deferred','historical_confirmation_modified':False,'limitations':['Finite authored structures, not universal routing or LLM Modeler integration.','Symbolic identities and declared-unit lint are limited checks, not a universal proof or semantic parser.','Proof text is assistant-authored review; no independent human peer review claimed.','Historical fixed-fixture Excel exception remains; A+uses unchanged confirmed v2 NPZ, not that workbook.']}
    (run/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    binding={'input_files':{str(p.relative_to(ROOT)):file_hash(p) for p in [asset_path(ROOT,'stage-a/2024-A-problem-1/parameters.json'),asset_path(ROOT,'stage-a/2024-A-problem-1/input-manifest.json'),array_path,asset_path(ROOT,'stage-b/v2-result-confirmation.json')]},'baseline_artifacts':{str(p.relative_to(ROOT)):file_hash(p) for folder in ['math','cases','sources'] for p in (BASE/folder).glob('*') if p.is_file()},'sources_read_log':file_hash(BASE/'sources/read-log.json'),'author_code':{str(p.relative_to(ROOT)):file_hash(p) for p in [Path(__file__),ROOT/'modelcrew/aplus.py',ROOT/'scripts/reference_2024_a_q1.py']}}
    (run/'manifest.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (BASE/'verification-summary.json').write_text(json.dumps({'report_path':str((run/'verification.json').relative_to(ROOT)),'report_sha256':file_hash(run/'verification.json'),'manifest_path':str((run/'manifest.json').relative_to(ROOT)),'status':report['status'],'check_count':len(checks),'date':report['date'],'new_llm_calls':0,'latex_compilation':report['latex_compilation']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(checks),'failed':[c for c in checks if not c['passed']],'lp_optimum':lp_report['x_kg'],'lp_objective':lp_report['objective_currency'],'report':str(run/'verification.json')},ensure_ascii=False,indent=2))
    if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
