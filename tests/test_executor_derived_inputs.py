"""Only successful same-model checkpoint artifacts may augment frozen inputs."""
import copy,json,hashlib
from pathlib import Path
import pytest
from modelcrew.docker_executor import DockerExecutor,ExecutorError

@pytest.fixture
def checkpoint(tmp_path,monkeypatch):
    ex=object.__new__(DockerExecutor);ex.root=tmp_path
    f=tmp_path/'runs/parent/artifacts/state.npz';f.parent.mkdir(parents=True);f.write_bytes(b'exact-synthetic-state')
    sha=hashlib.sha256(f.read_bytes()).hexdigest();auth={'mode':'workflow','task_id':'fixture','version':6,'contract_sha256':'a'*64}
    parent={'job_id':'parent','job_sha256':'b'*64,'code_sha256':'c'*64,'authorization':dict(auth)}
    artifact={'path':'runs/parent/artifacts/state.npz','sha256':sha,'size_bytes':f.stat().st_size}
    receipt={'status':'succeeded','job_sha256':'b'*64,'code_sha256':'c'*64,'artifacts':[artifact]}
    saved=tmp_path/'runs/parent/result.json';saved.write_text(json.dumps(receipt),encoding='utf-8')
    monkeypatch.setattr(ex,'job',lambda key:(None,parent))
    auth['derived_inputs']=[{'input_id':'derived:checkpoint','job_id':'parent','artifact_path':artifact['path'],'sha256':sha}]
    job={'job_id':'child','authorization':auth,'inputs':[{'input_id':'original','sha256':'d'*64},{'input_id':'derived:checkpoint','sha256':sha}]}
    return ex,job,parent,receipt,saved,f

def test_verified_checkpoint_extends_but_does_not_replace_frozen_inputs(checkpoint):
    ex,job,*_=checkpoint;ex.approved_inputs(job,{'original':'d'*64})

@pytest.mark.parametrize('mutation',['changed_input','missing_original','wrong_model','wrong_code','failed_parent','missing_receipt','tampered_state','undeclared_extra','duplicate_derived','same_job'])
def test_invalid_checkpoint_link_is_rejected(checkpoint,mutation):
    ex,job,parent,receipt,saved,f=checkpoint
    if mutation=='changed_input':job['inputs'][0]['sha256']='e'*64
    if mutation=='missing_original':job['inputs'].pop(0)
    if mutation=='wrong_model':parent['authorization']['version']=5
    if mutation=='wrong_code':receipt['code_sha256']='e'*64;saved.write_text(json.dumps(receipt))
    if mutation=='failed_parent':receipt['status']='timeout';saved.write_text(json.dumps(receipt))
    if mutation=='missing_receipt':saved.unlink()
    if mutation=='tampered_state':f.write_bytes(b'changed')
    if mutation=='undeclared_extra':job['authorization']['derived_inputs']=[]
    if mutation=='duplicate_derived':job['authorization']['derived_inputs']*=2
    if mutation=='same_job':job['job_id']='parent'
    with pytest.raises(ExecutorError):ex.approved_inputs(job,{'original':'d'*64})

def test_legacy_exact_frozen_inputs_still_work(checkpoint):
    ex,job,*_=checkpoint;job['authorization'].pop('derived_inputs');job['inputs']=job['inputs'][:1]
    ex.approved_inputs(job,{'original':'d'*64})
