from modelcrew.project_assets import asset_path,local_history
import copy,json
import numpy as np
import pytest
from modelcrew.config import ROOT
from modelcrew.evidence_planning import representative_times,geometry_evidence,check_catalog

@pytest.fixture
def parameters():return json.loads((asset_path(ROOT,'stage-a/2024-A-problem-1/parameters.json')).read_text(encoding='utf-8'))
@pytest.fixture
def state(parameters):
    # Independent straight chain fixture has exact known board dimensions, not a solver output.
    distances=np.r_[parameters['head_handle_distance_m'],np.full(222,parameters['other_handle_distance_m'])]
    points=np.column_stack((np.r_[0,np.cumsum(distances)],np.zeros(224)))
    times=np.array(parameters['report_times_s'],dtype=float)
    return times,np.repeat(points[None],len(times),axis=0)

def test_full_geometry_and_shared_scale(parameters,state):
    times,positions=state
    original=positions.copy();g=geometry_evidence(parameters,times,positions)
    assert g['boards_per_time']==223 and g['handle_count']==224
    assert g['sample_indices']==list(range(6))
    assert g['overview']['xlim_m']==g['overview']['ylim_m']
    assert all(x['board_indices']==[0,1,2] for x in g['local_views'])
    np.testing.assert_array_equal(positions,original)
    assert g['maximum_length_error_m']<1e-8
    assert 'NOT collision' in g['claim_scope']

@pytest.mark.parametrize('times',[None,[],[0,60,60],[60,0],[0,float('nan')],[False,60],[-1,60]])
def test_bad_or_unspecified_times_do_not_get_silent_defaults(times):
    with pytest.raises(ValueError):representative_times('spiral_chain',times)

def test_other_structure_does_not_inherit_bench_times():
    result=representative_times('resource_allocation',[0,60,300])
    assert result['status']=='not_applicable' and result['times_s']==[]

@pytest.mark.parametrize('key,value', [('bench_width_m',None),('hole_offset_m',0),('hole_diameter_m',.4),('head_bench_length_m',3.5),('bench_count',222)])
def test_unverified_or_inconsistent_physical_dimensions_fail(parameters,state,key,value):
    parameters[key]=value
    with pytest.raises(ValueError):geometry_evidence(parameters,*state)

def test_missing_requested_time_rejected(parameters,state):
    times,points=state
    with pytest.raises(ValueError,match='missing'):geometry_evidence(parameters,np.delete(times,2),np.delete(points,2,axis=0))

def test_nonrigid_positions_not_smoothed_into_plausible_outline(parameters,state):
    times,points=state;points[2,1,0]+=.01
    with pytest.raises(ValueError,match='rigid'):geometry_evidence(parameters,times,points)

def test_unselected_times_still_determine_global_bounds(parameters,state):
    times,points=state
    times=np.insert(times,1,30);points=np.insert(points,1,points[0]+[200,0],axis=0)
    result=geometry_evidence(parameters,times,points)
    assert result['overview']['xlim_m'][1]>500

@pytest.fixture
def planned_catalog():
    base=asset_path(ROOT,'stage-a-plus/evidence-planning-20261107')
    plan=json.loads((base/'evidence-plan.json').read_text(encoding='utf-8'))
    catalog=json.loads((ROOT/'output/md/modeling-q1-candidates-v3/figure-catalog.json').read_text(encoding='utf-8'))
    return plan['geometry'],catalog

def test_existing_candidates_match_plan(planned_catalog):
    assert check_catalog(*planned_catalog)['status']=='passed'

@pytest.mark.parametrize('defect',['missing_time','scale','dimension','formal','zoom','limitation','duplicate_id','category'])
def test_misleading_catalog_metadata_cannot_pass(planned_catalog,defect):
    geometry,catalog=planned_catalog;f=next(f for f in catalog['figures'] if f.get('time_s')==0)
    if defect=='missing_time':catalog['figures'].remove(f)
    elif defect=='scale':f['geometry']['overview_limits_m']=[-5,5]
    elif defect=='dimension':f['geometry']['width_m']=.5
    elif defect=='formal':f['formal']=True
    elif defect=='zoom':f['geometry']['zoom_board_indices']=[0]
    elif defect=='limitation':f['limitation']='collision-free'
    elif defect=='duplicate_id':catalog['figures'].append(copy.deepcopy(f))
    else:
        for x in catalog['figures']:x['category']='result'
    assert check_catalog(geometry,catalog)['status']=='failed'
