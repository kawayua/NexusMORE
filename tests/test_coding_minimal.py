"""D3 provenance and numerical rejection boundaries; no model calls or Docker."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import run_d3_minimal as runner
from scripts.reference_2024_a_q1 import solve
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.docker_executor import register_job, ExecutorError
from modelcrew.collaboration import sha_file


@pytest.fixture
def run(tmp_path,monkeypatch):
    root=tmp_path/'executor';folder=tmp_path/'minimal-test';folder.mkdir()
    monkeypatch.setattr(runner,'executor_root',lambda:root)
    code=folder/'generated_solver.py';code.write_text('print("test fixture, not a generated solve")',encoding='utf-8')
    contract=json.loads((ROOT/'stage-b-plus/examples/contract-v2-snapshot.json').read_text(encoding='utf-8'))
    runner.write(folder/'contract.json',contract)
    job=register_job(root,folder.name,code,[],{'mode':'workflow','task_id':'TEST','version':1,'contract_sha256':digest(contract)})
    runner.write(folder/'job.json',job)
    runner.write(folder/'run.json',{'code_sha256':sha_file(code),'contract_sha256':digest(contract)})
    runner.write(folder/'code-evidence.json',{'code':code.read_text(encoding='utf-8'),'code_sha256':sha_file(code)})
    output=root/'runs'/folder.name/'artifacts';output.mkdir(parents=True)
    parameters=runner.read(ROOT/'stage-a/2024-A-problem-1/parameters.json')
    values=[solve(t,parameters) for t in runner.TIMES]
    arrays={'time_s':np.array(runner.TIMES),'theta_rad':np.array([v[0] for v in values]),'position_m':np.array([v[1] for v in values]),'velocity_m_s':np.array([v[2] for v in values])}
    arrays['speed_m_s']=np.linalg.norm(arrays['velocity_m_s'],axis=2)
    np.savez(output/'minimal.npz',**arrays)
    report={'contract_sha256':digest(contract),'code_sha256':sha_file(code),'scope':'minimal_P1','actual_solver_run':True,'fixture':False,'full_contract_checks':{c['id']:'unknown' for c in contract['checks']}}
    runner.write(output/'checks.json',report)
    receipt={'run_id':folder.name,'job_sha256':job['job_sha256'],'code_sha256':job['code_sha256'],'authorization':job['authorization'],'status':'succeeded','cleanup':{'removed':True},'artifacts':[]}
    def freeze():
        receipt['artifacts']=[{'name':p.name,'path':p.relative_to(root).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size} for p in output.iterdir()]
        runner.write(folder/'execution.json',receipt)
    freeze()
    return folder,output,arrays,report,receipt,freeze


def test_recomputation_accepts_consistent_arrays_with_provenance(run):
    folder,*_=run
    result=runner.validate(folder)
    assert result['passed'] and result['fresh_reference_computation']
    assert result['full_contract_checks']=='unknown'


def test_failed_numerical_arrays_cannot_pass_by_self_report(run):
    folder,output,arrays,report,receipt,freeze=run
    arrays['position_m'][3,100,0]+=.01
    np.savez(output/'minimal.npz',**arrays);freeze()
    with pytest.raises(ValueError,match='numerical validation failed'):runner.validate(folder)
    assert not runner.read(folder/'validation.json')['checks']['rod_distance_m']['passed']


@pytest.mark.parametrize('mutation',['code','job','receipt','artifact','scope'])
def test_modified_provenance_or_premature_full_claims_rejected(run,mutation):
    folder,output,arrays,report,receipt,freeze=run
    if mutation=='code':(folder/'generated_solver.py').write_text('print("modified")',encoding='utf-8')
    elif mutation=='job':
        job=runner.read(folder/'job.json');job['code_sha256']='0'*64;runner.write(folder/'job.json',job)
    elif mutation=='receipt':receipt['authorization']['task_id']='ANOTHER_TASK';freeze()
    elif mutation=='artifact':(output/'checks.json').write_text('{}',encoding='utf-8')
    else:
        report['full_contract_checks'][next(iter(report['full_contract_checks']))]='passed'
        runner.write(output/'checks.json',report);freeze()
    with pytest.raises((ValueError,ExecutorError)):runner.validate(folder)


def test_preflight_rejects_network_and_dynamic_execution():
    for code in ['import socket','from subprocess import run','eval("1+1")']:
        with pytest.raises(ValueError):runner.static_check(code)
    assert runner.static_check('import numpy as np')['not_a_security_proof']

def test_failed_execution_records_known_failure_and_next_call_only_queries(run,monkeypatch):
    from contextlib import nullcontext
    folder,output,arrays,report,receipt,freeze=run
    meta=runner.read(folder/'run.json');meta.update(task_id='TEST',contract_version=1)
    runner.write(folder/'run.json',meta)
    class FakeWorkflow:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def lock(self,task):return nullcontext()
    monkeypatch.setattr(runner,'Workflow',FakeWorkflow)
    monkeypatch.setattr(runner,'approved',lambda *a,**k:{'contract':{'content':{'inputs':[]}}})
    calls=[]
    failed={**receipt,'status':'code_error','artifacts':[]}
    def trace(w,task,version,service,tool,args,op):
        calls.append(tool)
        return 'TEST_TRACE',{'status':'ok','data':failed}
    monkeypatch.setattr(runner,'trace_call',trace)
    for _ in range(2):
        with pytest.raises(runner.WorkflowError,match='did not succeed'):runner.execute(folder)
        assert runner.read(folder/'run.json')['status']=='execution_code_error'
    assert calls==['code_execute','code_execution_status']
