"""A+ explicit prerequisite checks for two declared problem structures.

This is a finite, human-authored baseline, not a natural-language classifier or
learned/general algorithm router. Unknown premises do not become true.
"""
import math

def choose_method(problem):
    kind=problem.get('structure');checks=[]
    def check(name,value,reason):
        state='unknown' if value is None else ('satisfied' if value else 'violated')
        checks.append({'condition':name,'status':state,'reason':reason})
        return value is True
    if kind=='spiral_chain':
        numeric=all(isinstance(problem.get(k),(int,float)) and not isinstance(problem.get(k),bool) and math.isfinite(problem[k]) for k in ['pitch_m','speed_m_s','initial_theta_rad','end_time_s','max_chord_m'])
        if not check('finite_physical_inputs',numeric,'Finite pitch, speed, initial angle, end time and maximum chord are required.'):
            return {'status':'blocked','selected':None,'checks':checks}
        p,v,q,t,L=[problem[k] for k in ['pitch_m','speed_m_s','initial_theta_rad','end_time_s','max_chord_m']]
        good=check('positive_geometry',p>0 and v>0 and q>0 and t>=0 and L>0,'The inward positive-radius branch requires p,v,theta0,L>0 and T>=0.')
        b=p/(2*math.pi)
        arc=lambda x:b/2*(x*math.hypot(x,1)+math.asinh(x))
        good=check('before_origin',good and v*t<arc(q),'Requested duration must end strictly before the head reaches the origin.') and good
        good=check('fixed_chord_chain',problem.get('fixed_chord_chain'),'Rod lengths are straight chord constraints, not arc lengths.') and good
        if not good:return {'status':'blocked','selected':None,'checks':checks}
        return {'status':'candidate','selected':'arc_inversion_and_bracketed_chords','checks':checks,'runtime_conditions':['Each chord root needs f(0)<0<f(pi); lack of bracket is not proof of no root outside the chosen branch.','Check derivative/velocity denominator and error budget.'],'alternative':'ODE of the same head motion, with tolerances, boundary events and independent checks.'}
    if kind=='resource_allocation':
        good=check('linear_objective',problem.get('linear_objective'),'LP requires a linear objective.')
        good=check('linear_constraints',problem.get('linear_constraints'),'LP requires linear constraints.') and good
        good=check('known_coefficients',problem.get('known_coefficients'),'Coefficients and their units must be known.') and good
        domain=problem.get('variable_domain')
        if domain=='integer':
            check('continuous_variables',False,'Continuous LP can return fractional quantities; use MILP/IP and check integer feasibility.')
            return {'status':'redirect' if good else 'blocked','selected':'mixed_integer_programming' if good else None,'checks':checks,'reason':'Do not round a continuous relaxation and claim a valid integer optimum.'}
        good=check('continuous_variables',True if domain=='continuous' else None,'This LP baseline requires explicitly continuous decision quantities.') and good
        return {'status':'candidate' if good else 'blocked','selected':'linear_programming' if good else None,'checks':checks,'runtime_conditions':['Verify solver termination, primal feasibility and an optimality certificate.']}
    return {'status':'unsupported','selected':None,'checks':[],'reason':'No implemented structural baseline; analyse the mechanism and read appropriate indexed sources.'}


def check_dossier(dossier):
    """ID/declared-unit/premise lint only. Never parses or proves LaTeX."""
    findings=[]
    groups=['symbols','assumptions','equations','derivations','propositions']
    for group in groups:
        ids=[x['id'] for x in dossier[group]]
        if len(ids)!=len(set(ids)):findings.append('duplicate '+group+' IDs')
    symbols={x['id']:x for x in dossier['symbols']};assumptions={x['id'] for x in dossier['assumptions']};equations={x['id'] for x in dossier['equations']}
    for eq in dossier['equations']:
        for name in eq['symbol_ids']:
            if name not in symbols:findings.append(eq['id']+': undefined symbol '+name)
        for name in eq['assumption_ids']:
            if name not in assumptions:findings.append(eq['id']+': undefined assumption '+name)
        if eq['lhs_dimension']!=eq['rhs_dimension']:findings.append(eq['id']+': declared dimension mismatch')
        for name,expected in eq.get('required_symbol_units',{}).items():
            if name in symbols and symbols[name]['unit']!=expected:findings.append(eq['id']+': symbol unit mismatch '+name)
    for item in dossier['derivations']+dossier['propositions']:
        if not item['conditions']:findings.append(item['id']+': missing conditions')
        if not item['steps']:findings.append(item['id']+': missing derivation/proof steps')
        for name in item['equation_ids']:
            if name not in equations:findings.append(item['id']+': undefined equation '+name)
        if item.get('status')=='proved' and item.get('open_gaps'):findings.append(item['id']+': proved with open gaps')
    if dossier['structure']=='spiral_chain':
        required={'positive_geometry','constant_chords','branch_scope'}
        for item in dossier['propositions']:
            if item['id']=='prop:chord-first-root' and not required<=set(item['conditions']):findings.append(item['id']+': missing first-root proof premises')
    return {'status':'failed' if findings else 'passed','findings':findings,'scope':'IDs, explicit premises and declared dimensions/units only; separate mathematical review is mandatory.'}
