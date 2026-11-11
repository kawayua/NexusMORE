"""Precision-only Q2 supplement; frozen numerical functions execute solely in Docker."""
import json
from pathlib import Path
import numpy as np
from modelcrew.collaboration import sha_file
from scripts.run_q2_full import active,job
from scripts.run_d3_minimal import read,write

def prepare(folder):
    sub=folder/'precision-supplement';sub.mkdir(exist_ok=True)
    source=folder/'part-10g-final-bound/generated_solver.py'
    base=source.read_text(encoding='utf-8').split("if __name__=='__main__':full_main()")[0]
    event=read(folder/'collision-event.json')
    tail='''
def precision_main():
    lo,hi=EVENT_TIME
    qi=iv(enclosed_state(hi)[3][0],enclosed_state(lo)[3][1])
    vel,den=velocity_iv(qi)
    speed=sqrtiv(isum(sqr(vel),1))
    q,p,v=solve(EVENT_ESTIMATE)
    nominal=np.linalg.norm(v,axis=1)
    if not np.all((vel[0]<=v)&(v<=vel[1])) or not np.all((speed[0]<=nominal)&(nominal<=speed[1])):raise ValueError('nominal outside certified enclosure')
    report={'purpose':'terminal velocity and speed precision only; unchanged frozen functions, no continuous search rerun','contract_sha256':CONTRACT_SHA256,'source_primary_sha256':PRIMARY_SHA,'code_sha256':hashlib.sha256(Path('/work/job/solver.py').read_bytes()).hexdigest(),'time_interval_s':list(EVENT_TIME),'time_estimate_s':EVENT_ESTIMATE,'velocity_lower_m_s':vel[0].tolist(),'velocity_upper_m_s':vel[1].tolist(),'speed_lower_m_s':speed[0].tolist(),'speed_upper_m_s':speed[1].tolist(),'nominal_velocity_m_s':v.tolist(),'nominal_speed_m_s':nominal.tolist(),'denominator_lower_bound_m2':den,'max_speed_enclosure_error_m_s':float(np.max(np.maximum(nominal-speed[0],speed[1]-nominal))),'six_decimal_speed_rounding_ambiguous_handles':[int(i) for i in np.flatnonzero(np.round(speed[0],6)!=np.round(speed[1],6))]}
    Path('/work/output/support-certificate.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
    print('224 terminal velocity and speed intervals certified on event bracket')
if __name__=='__main__':precision_main()
'''
    code=base+'\nEVENT_TIME='+repr(event['time_interval_s'])+'\nEVENT_ESTIMATE='+repr(event['time_estimate_s'])+'\nPRIMARY_SHA='+repr(sha_file(source))+'\n'+tail
    target=sub/'generated_solver.py'
    if target.exists() and target.read_text(encoding='utf-8')!=code:raise ValueError('existing supplement source differs')
    target.write_text(code,encoding='utf-8')
    return event

def main():
    folder=active();event=prepare(folder);report=job(folder,'precision-supplement',*event['time_interval_s'])
    sub=folder/'precision-supplement';receipt=read(sub/'execution.json');out=read(sub/'output-manifest.json')['support-certificate.json']
    if report['code_sha256']!=receipt['code_sha256'] or report['source_primary_sha256']!=sha_file(folder/'part-10g-final-bound/generated_solver.py'):raise ValueError('precision source mismatch')
    with np.load(folder/'results/terminal-state.npz',allow_pickle=False) as z:
        v=z['velocity_m_s'];s=z['speed_m_s']
    vl=np.array(report['velocity_lower_m_s']);vu=np.array(report['velocity_upper_m_s']);sl=np.array(report['speed_lower_m_s']);su=np.array(report['speed_upper_m_s'])
    if vl.shape!=(224,2) or vu.shape!=(224,2) or sl.shape!=(224,) or su.shape!=(224,) or not all(np.isfinite(a).all() for a in [vl,vu,sl,su]):raise ValueError('invalid precision arrays')
    if not np.all((vl<=v)&(v<=vu)) or not np.all((sl<=s)&(s<=su)) or np.max(abs(np.array(report['nominal_speed_m_s'])-s))!=0:raise ValueError('existing terminal state outside precision supplement')
    ambiguous=[{'handle_index_zero_based':int(i),'xlsx_cell':'D'+str(i+2),'estimate_m_s':float(s[i]),'interval_m_s':[float(sl[i]),float(su[i])],'rounded_lower_6dp':round(float(sl[i]),6),'rounded_upper_6dp':round(float(su[i]),6)} for i in np.flatnonzero(np.round(sl,6)!=np.round(su,6))]
    final={'status':'PASS','certificate':report,'execution':receipt,'output_manifest':out,'trusted_checks':{'all_224_existing_nominal_velocity_and_speed_inside':True,'unchanged_final_primary_source':True,'all_output_hashes_checked':True,'MCP_Docker_only':True},'rounding_disclosure':{'ambiguous_speed_coordinates':ambiguous,'all_intervals_reported':True,'six_decimal_output_is_nominal_when_ambiguous':True,'max_displayed_error_bound_m_s':5e-7+report['max_speed_enclosure_error_m_s'],'no_claim_ambiguous_last_digits_unique':True},'selected_handles':[{'handle_index_zero_based':i,'speed_interval_m_s':[float(sl[i]),float(su[i])]} for i in [0,1,51,101,151,201,223]],'not_user_approval':True}
    write(folder/'precision-supplement.json',final)
    print(json.dumps({'status':'PASS','max_speed_error':report['max_speed_enclosure_error_m_s'],'ambiguous_speed_count':len(ambiguous),'denominator_lower_bound':report['denominator_lower_bound_m2']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
