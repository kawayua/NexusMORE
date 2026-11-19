import copy
from modelcrew.review_projection import project


def test_only_declared_binary_blob_is_omitted_and_original_unchanged():
    evidence={'result':{'checks':[{'id':'chk_dt','status':'FAIL','value':.0084}],
        'trace':{'encoding':'zlib+base64; exact float64 columnar bytes','sha256_uncompressed':'a'*64,'data':'x'*2048,'shape':[1800,7]}}}
    before=copy.deepcopy(evidence);view,omitted=project(evidence)
    assert evidence==before and view['result']['checks']==before['result']['checks']
    assert 'data' not in view['result']['trace'] and view['result']['trace']['shape']==[1800,7]
    assert omitted[0]['pointer']=='/result/trace/data' and omitted[0]['encoded_characters']==2048


def test_no_generic_truncation_of_code_failure_or_undeclared_content():
    evidence={'code':'x'*100000,'failure':{'data':'y'*2000},'status':'FAIL'}
    view,omissions=project(evidence)
    assert view==evidence and not omissions
