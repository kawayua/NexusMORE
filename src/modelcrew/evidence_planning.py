"""A+ question-specific evidence planning; no plotting, approval or collision claims."""
import math
import numpy as np
from .bench_visuals import bench_geometry

DIMENSIONS = ('head_bench_length_m','other_bench_length_m','hole_offset_m',
              'head_handle_distance_m','other_handle_distance_m','bench_width_m','hole_diameter_m')

def representative_times(structure, requested_times=None):
    """Unknown/non-geometric problems never inherit the bench-dragon timestamps."""
    if structure != 'spiral_chain':
        return {'status':'not_applicable','times_s':[], 'reason':'Choose views from this problem\'s scientific question; no imposed bench-dragon time series.'}
    if requested_times is None:
        raise ValueError('Time-dependent geometry requires explicit problem/user times')
    values=list(requested_times)
    if not values or any(isinstance(t,bool) or not isinstance(t,(float,int)) or not math.isfinite(t) or t<0 for t in values):
        raise ValueError('Representative times must be finite nonnegative numbers')
    if any(a>=b for a,b in zip(values,values[1:])):
        raise ValueError('Representative times must be strictly increasing and unique')
    return {'status':'planned','times_s':values,'reason':'Use problem-specified report times, including the initial and final state; not selected from visually favourable results.'}

def geometry_evidence(parameters, times, positions):
    """Check frozen input dimensions and derive shared bounds from ALL stored times."""
    for key in DIMENSIONS:
        value=parameters.get(key)
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<=0:
            raise ValueError('Missing/invalid verified dimension: '+key)
    p=parameters
    for prefix,length in [('head','head_bench_length_m'),('other','other_bench_length_m')]:
        if not math.isclose(p[prefix+'_handle_distance_m']+2*p['hole_offset_m'],p[length],abs_tol=1e-12,rel_tol=0):
            raise ValueError('Inconsistent board length and hole offsets')
    if p['hole_diameter_m']>=min(p['bench_width_m'],2*p['hole_offset_m']):
        raise ValueError('Handle hole does not fit the declared rectangular board')
    if (p['bench_count'],p['handle_count'],p['body_bench_count'])!=(223,224,221):
        raise ValueError('This case requires head + 221 body + tail boards and 224 handles')
    ts=np.asarray(times,dtype=float);xy=np.asarray(positions,dtype=float)
    if ts.ndim!=1 or len(ts)<2 or not np.isfinite(ts).all() or np.any(np.diff(ts)<=0):
        raise ValueError('Stored times must be finite and strictly increasing')
    if xy.shape!=(len(ts),224,2) or not np.isfinite(xy).all():
        raise ValueError('Expected finite time x 224 x 2 handle positions')
    if ts[0]!=p['time_start_s'] or ts[-1]!=p['time_end_s']:
        raise ValueError('Stored time range differs from declared problem range')
    chosen=representative_times('spiral_chain',p['report_times_s'])['times_s']
    indices=[]
    for t in chosen:
        match=np.flatnonzero(ts==t)
        if len(match)!=1:raise ValueError('Requested representative time missing from stored results')
        indices.append(int(match[0]))
    if chosen[0]!=ts[0] or chosen[-1]!=ts[-1]:raise ValueError('Initial and final report times required')
    boards=np.asarray([bench_geometry(x,p['bench_width_m'],p['hole_offset_m']) for x in xy])
    expected=np.full(223,p['other_bench_length_m']);expected[0]=p['head_bench_length_m']
    length_error=float(np.max(np.abs(np.linalg.norm(boards[:,:,1]-boards[:,:,0],axis=-1)-expected)))
    width_error=float(np.max(np.abs(np.linalg.norm(boards[:,:,2]-boards[:,:,1],axis=-1)-p['bench_width_m'])))
    if length_error>1e-8 or width_error>1e-12:raise ValueError('Stored centers cannot reconstruct declared rigid board dimensions')
    limit=float(np.max(np.abs(boards)))+.6
    zooms=[]
    for t,i in zip(chosen,indices):
        corners=boards[i,:3].reshape(-1,2);center=(corners.max(0)+corners.min(0))/2
        half=float(np.ptp(corners,axis=0).max())/2+.4
        zooms.append({'time_s':t,'sample_index':i,'board_indices':[0,1,2],
                      'xlim_m':[float(center[0]-half),float(center[0]+half)],
                      'ylim_m':[float(center[1]-half),float(center[1]+half)]})
    return {'sample_count':len(ts),'boards_per_time':223,'handle_count':224,
            'report_times_s':chosen,'sample_indices':indices,'dimension_values_m':{k:p[k] for k in DIMENSIONS},
            'reconstruction':'u=(P_next-P)/norm(P_next-P); endpoints P-offset*u and P_next+offset*u; corners endpoints +/- width*n/2; hole radius=diameter/2',
            'maximum_length_error_m':length_error,'maximum_width_error_m':width_error,
            'overview':{'xlim_m':[-limit,limit],'ylim_m':[-limit,limit],'aspect':'equal','bounds_source':'all stored times, all 223 board rectangles','margin_m':.6},
            'local_views':zooms,'local_margin_m':.4,
            'claim_scope':'Rigid plan-view schematic reconstructed from confirmed centers and input dimensions; NOT collision detection, clearance certification, force simulation or physical experiment.'}

def check_catalog(geometry,catalog):
    """Check candidate metadata against the plan, without certifying rendered image pixels."""
    findings=[];figs=catalog.get('figures',[])
    ids=[x['id'] for x in figs]
    if len(ids)!=len(set(ids)):findings.append('Duplicate logical figure IDs')
    counts={kind:sum(x.get('category')==kind for x in figs) for kind in ['raw','process','result']}
    if len(figs)<9 or min(counts.values())<3:findings.append('Candidate category coverage below project policy')
    for t in geometry['report_times_s']:
        matches=[x for x in figs if x.get('time_s')==t and x.get('source_kind')=='historical_centers_with_input_dimension_schematic']
        if len(matches)!=1:
            findings.append('Missing/duplicate physical-outline candidate at '+str(t));continue
        f=matches[0];g=f.get('geometry',{})
        if f.get('formal') or f.get('selection_status')!='proposed_not_user_approved':findings.append('New outline must remain an unselected candidate')
        for k,pkey in [('width_m','bench_width_m'),('hole_offset_m','hole_offset_m'),('hole_diameter_m','hole_diameter_m')]:
            if g.get(k)!=geometry['dimension_values_m'][pkey]:findings.append('Dimension mismatch '+k)
        limits=g.get('overview_limits_m',[])
        if len(limits)!=2 or not np.allclose(limits,geometry['overview']['xlim_m'],rtol=0,atol=1e-12):findings.append('Overview scale differs from all-time shared bounds')
        if g.get('boards')!=223 or g.get('zoom_board_indices')!=[0,1,2]:findings.append('Board coverage/local scope mismatch')
        if '未进行碰撞' not in f.get('limitation',''):findings.append('Missing collision limitation')
    return {'status':'failed' if findings else 'passed','findings':findings,'candidate_count':len(figs),'categories':counts,'scope':'Plan/metadata consistency only; visual review is separate.'}
