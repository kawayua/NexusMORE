"""External reproduction cannot be inferred from stale author self-checks."""
from copy import deepcopy
import json
import pytest
from modelcrew.w2_runtime_evidence import verify_packets,collect
from modelcrew.collaboration import sha_file
from modelcrew.workflow import WorkflowError


@pytest.fixture
def packets(tmp_path):
    outputs=[]
    for n in [1,2]:
        path=tmp_path/f'run{n}/artifacts/result.json';path.parent.mkdir(parents=True);path.write_text('{"chk_reproduce":"PENDING_RUNTIME"}',encoding='utf-8')
        outputs.append({'receipt':{'status':'succeeded','run_id':f'run{n}','artifacts':[{'name':'result.json','path':path.relative_to(tmp_path).as_posix(),'sha256':sha_file(path)}]},
            'job':{'code_sha256':'a'*64,'inputs':[{'sha256':'b'*64}],'authorization':{'task_id':'synthetic','version':1,'contract_sha256':'c'*64}}})
    return outputs,tmp_path


def test_external_outputs_override_only_external_reproduction_status(packets):
    values,root=packets
    result=verify_packets(*values,executor=root)
    assert result['status']=='PASS' and result['actual_files_verified'] and result['artifact_count']==1
    assert 'PENDING_RUNTIME' in (root/'run1/artifacts/result.json').read_text()


@pytest.mark.parametrize('defect',['failed','code','input','binding','changed','empty','duplicate','hashes'])
def test_reproduction_requires_binding_and_actual_matching_bytes(packets,defect):
    values,root=packets;b=values[1]
    if defect=='failed':b['receipt']['status']='failed'
    if defect=='code':b['job']['code_sha256']='different'
    if defect=='input':b['job']['inputs']=[]
    if defect=='binding':b['job']['authorization']['version']=2
    if defect=='changed':(root/'run2/artifacts/result.json').write_text('changed')
    if defect=='empty':b['receipt']['artifacts']=[]
    if defect=='duplicate':b['receipt']['artifacts']*=2
    if defect=='hashes':
        path=root/'run2/artifacts/result.json';path.write_text('different')
        b['receipt']['artifacts'][0]['sha256']=sha_file(path)
    with pytest.raises((WorkflowError,ValueError)):verify_packets(*values,executor=root)


def test_incomplete_numeric_binding_never_infers_a_pass(tmp_path):
    assert collect(None,{'binding':{}},root=tmp_path,executor=tmp_path)['status']=='NOT_AVAILABLE'
