import copy
import pytest
from scripts.resolve_q2_review_aliases import resolve_aliases

def review(selector='/certificate_summary/code_sha256'):
    return {'checks':[{'check_id':'execution','status':'FAIL','evidence':[{'artifact_id':'speed_precision','selector':selector}],'explanation':'Original independent judgment'}],'issues':[{'reason':'keep original issue'}]}

def test_recorded_equal_view_alias_preserves_fail_and_issue():
    original=review();before=copy.deepcopy(original)
    corrected,maps=resolve_aliases(original,{'speed_precision':{'certificate':{'code_sha256':'same'}}},{'speed_precision':{'certificate_summary':{'code_sha256':'same'}}})
    assert original==before
    assert corrected['checks'][0]['status']=='FAIL' and corrected['issues']==before['issues']
    assert corrected['checks'][0]['evidence'][0]['selector']=='/certificate/code_sha256'
    assert len(maps)==1 and maps[0]['equal_verified']

def test_alias_different_frozen_value_rejected():
    with pytest.raises(ValueError,match='does not equal'):
        resolve_aliases(review(),{'speed_precision':{'certificate':{'code_sha256':'actual'}}},{'speed_precision':{'certificate_summary':{'code_sha256':'other'}}})

def test_unknown_invalid_pointer_not_repaired():
    with pytest.raises(ValueError,match='Unmapped'):
        resolve_aliases(review('/imagined'),{'speed_precision':{}},{'speed_precision':{}})
