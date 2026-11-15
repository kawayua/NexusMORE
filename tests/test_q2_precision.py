"""Narrow tests for terminal-speed certificate enclosure and mandatory disclosure."""
import json
import numpy as np
import pytest
import modelcrew.q2_full_result as module
from modelcrew.collaboration import sha_file

@pytest.fixture
def precision(tmp_path,monkeypatch):
    folder=tmp_path;sub=folder/'precision-supplement';sub.mkdir();primary=folder/'part-10g-final-bound';primary.mkdir()
    (primary/'generated_solver.py').write_text("def frozen(): pass\nif __name__=='__main__':full_main()",encoding='utf-8')
    (sub/'generated_solver.py').write_text('def frozen(): pass\n\nEVENT_TIME=[1,2]',encoding='utf-8')
    v=np.ones((224,2));s=np.full(224,2**.5);lo=s-1e-9;hi=s+1e-9
    # The first handle straddles a displayed rounding boundary.
    lo[0]=1.4142134;hi[0]=1.4142136
    event={'contract_sha256':'contract','time_interval_s':[1.,2.]}
    receipt={'code_sha256':sha_file(sub/'generated_solver.py')}
    c={'source_primary_sha256':sha_file(primary/'generated_solver.py'),'code_sha256':receipt['code_sha256'],'contract_sha256':'contract','time_interval_s':[1.,2.],'velocity_lower_m_s':(v-1e-9).tolist(),'velocity_upper_m_s':(v+1e-9).tolist(),'speed_lower_m_s':lo.tolist(),'speed_upper_m_s':hi.tolist(),'nominal_velocity_m_s':v.tolist(),'nominal_speed_m_s':s.tolist(),'six_decimal_speed_rounding_ambiguous_handles':[0],'max_speed_enclosure_error_m_s':float(np.max(np.maximum(s-lo,hi-s)))}
    report={'certificate':c,'execution':receipt,'status':'PASS','rounding_disclosure':{'ambiguous_speed_coordinates':[{'handle_index_zero_based':0,'interval_m_s':[float(lo[0]),float(hi[0])],'xlsx_cell':'D2'}],'max_displayed_error_bound_m_s':5e-7+c['max_speed_enclosure_error_m_s']}}
    def save():
        (folder/'precision-supplement.json').write_text(json.dumps(report),encoding='utf-8');(sub/'execution.json').write_text(json.dumps(receipt),encoding='utf-8');(sub/'raw.json').write_text(json.dumps(c),encoding='utf-8')
    save()
    import scripts.validate_q2_full
    monkeypatch.setattr(scripts.validate_q2_full,'artifacts',lambda f,k:{'support-certificate.json':sub/'raw.json'})
    return folder,event,v,s,c,report,save

def test_complete_terminal_speed_certificate(precision):
    f,e,v,s,*_=precision
    assert f/'precision-supplement.json' in module.verify_q2_precision(f,e,v,s)

def test_missing_speed_rounding_disclosure_fails(precision):
    f,e,v,s,c,r,save=precision;r['rounding_disclosure']['ambiguous_speed_coordinates']=[];save()
    with pytest.raises(ValueError,match='disclosure incomplete'):module.verify_q2_precision(f,e,v,s)

def test_nominal_outside_speed_interval_fails(precision):
    f,e,v,s,c,r,save=precision;c['speed_lower_m_s'][2]=float(s[2]+.01);save()
    with pytest.raises(ValueError,match='does not enclose'):module.verify_q2_precision(f,e,v,s)

def test_changed_precision_function_prefix_fails(precision):
    f,e,v,s,c,r,save=precision;(f/'precision-supplement/generated_solver.py').write_text('changed function',encoding='utf-8')
    with pytest.raises(ValueError,match='source differs'):module.verify_q2_precision(f,e,v,s)
