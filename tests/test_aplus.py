import copy,json,math,re
from pathlib import Path
import pytest
from modelcrew.aplus import choose_method,check_dossier
from modelcrew.config import ROOT
from modelcrew.inputs import file_hash
BASE=ROOT/'stage-a-plus'
def read(path):return json.loads((BASE/path).read_text(encoding='utf-8'))

@pytest.fixture
def geometry():return read('cases/bench-dragon.json')
@pytest.fixture
def allocation():return read('cases/resource-allocation.json')
@pytest.fixture
def dossier():return read('math/bench-dragon-dossier.json')

def test_distinct_structures_get_relevant_methods(geometry,allocation):
    assert choose_method(geometry)['selected']=='arc_inversion_and_bracketed_chords'
    assert choose_method(allocation)['selected']=='linear_programming'

@pytest.mark.parametrize('key,value',[('pitch_m',0),('pitch_m',-.55),('speed_m_s',0),('initial_theta_rad',0),('end_time_s',-1),('end_time_s',1e5),('max_chord_m',0),('pitch_m',float('nan')),('pitch_m',float('inf')),('pitch_m',True)])
def test_geometry_invalid_or_outside_domain_blocks(geometry,key,value):
    geometry[key]=value
    assert choose_method(geometry)['status']=='blocked'

@pytest.mark.parametrize('key',['linear_objective','linear_constraints','known_coefficients'])
def test_unknown_lp_prerequisite_is_not_satisfied(allocation,key):
    allocation.pop(key)
    assert choose_method(allocation)['status']=='blocked'
    assert any(x['status']=='unknown' for x in choose_method(allocation)['checks'])

def test_integer_variables_redirect_without_continuous_rounding(allocation):
    allocation['variable_domain']='integer'
    answer=choose_method(allocation)
    assert answer['status']=='redirect' and answer['selected']=='mixed_integer_programming'

def test_unknown_structure_stays_unsupported():
    assert choose_method({'structure':'unknown'})['status']=='unsupported'

def test_unknown_fixed_chords_do_not_certify_geometry(geometry):
    geometry.pop('fixed_chord_chain');assert choose_method(geometry)['status']=='blocked'

def test_unknown_variable_domain_blocks(allocation):
    allocation.pop('variable_domain');assert choose_method(allocation)['status']=='blocked'

@pytest.mark.parametrize('name',['bench-dragon','resource'])
def test_actual_dossier_and_latex_are_consistent(name):
    d=read('math/'+name+'-dossier.json');assert check_dossier(d)['status']=='passed'
    tex=(BASE/'math'/f'{name}-fragments.tex').read_text(encoding='utf-8')
    for e in d['equations']:
        assert e['latex'] in tex and tex.count('\\label{'+e['id']+'}')==1
    for s in d['symbols']:
        assert '$'+s['latex']+'$' in tex
        assert not any(ord(c)<32 for c in s['latex'])

@pytest.mark.parametrize('mutation',['missing_symbol','unit','dimension','premise','proof_gap','duplicate'])
def test_mathematical_dossier_defects_are_reported(dossier,mutation):
    if mutation=='missing_symbol':dossier['symbols']=dossier['symbols'][1:]
    elif mutation=='unit':dossier['symbols'][0]['unit']='s'
    elif mutation=='dimension':dossier['equations'][0]['rhs_dimension']='1'
    elif mutation=='premise':next(x for x in dossier['propositions'] if x['id']=='prop:chord-first-root')['conditions'].remove('branch_scope')
    elif mutation=='proof_gap':dossier['propositions'][0]['open_gaps']=['not proved']
    else:dossier['equations'].append(copy.deepcopy(dossier['equations'][0]))
    assert check_dossier(dossier)['status']=='failed'

def test_lint_is_not_a_semantic_math_proof(dossier):
    dossier['equations'][0]['latex']='1=2'
    assert check_dossier(dossier)['status']=='passed' # Explicit boundary: independent math review is still required.
    assert 'separate mathematical review' in check_dossier(dossier)['scope']

def test_monotonicity_does_not_imply_bracket_root():
    b=.55/(2*math.pi);r=.1;ell=1.
    f=lambda d:(b*d)**2+4*r*(r+b*d)*math.sin(d/2)**2-ell**2
    assert f(0)<0 and f(math.pi)<0
    for delta in [.01,.1,1.,3.]:
        derivative=2*b*b*delta+4*r*b*math.sin(delta/2)**2+2*r*(r+b*delta)*math.sin(delta)
        assert derivative>0

def test_lp_optimality_certificate_and_infeasibility():
    import numpy as np
    from scipy.optimize import linprog
    A=np.array([[1.,1.],[2.,1.]]);a=np.array([4.,6.]);c=np.array([3.,2.]);prices=np.ones(2)
    result=linprog(-c,A_ub=A,b_ub=a,bounds=(0,None),method='highs')
    assert result.success and np.allclose(result.x,[2,2])
    assert np.all(A.T@prices>=c) and abs(a@prices-c@result.x)<1e-12
    assert linprog(-c,A_ub=A,b_ub=[-1,6],bounds=(0,None),method='highs').status==2

def test_source_read_ranges_and_hashes():
    log=read('sources/read-log.json')
    for source in log['sources']:
        original=ROOT/source['project_path'];excerpt=BASE/source['excerpt_path']
        assert file_hash(original)==source['file_sha256'] and file_hash(excerpt)==source['excerpt_sha256']
        assert excerpt.read_text(encoding='utf-8')=='\n'.join(original.read_text(encoding='utf-8-sig').splitlines()[source['line_start']-1:source['line_end']])+'\n'
