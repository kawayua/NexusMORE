"""Validator rejection tests using copies of the actual v2 artifacts, never changing originals."""
from modelcrew.project_assets import asset_path,local_history
import json,shutil,uuid
from pathlib import Path
import numpy as np
import pytest
from modelcrew.config import ROOT
from modelcrew.solver_validation import validate_run,ResultError

@pytest.fixture
def solver_copy(request):
    if not request.config.getoption('--integration'):pytest.skip('Requires completed real v2 artifacts')
    source=asset_path(ROOT,'stage-b/runs/solver-v2-20261104T131332959555Z')
    if not (source/'output/checks.json').exists():pytest.skip('Real solver evidence not present')
    dest=asset_path(ROOT,'stage-b/runs')/('validator-test-'+uuid.uuid4().hex);dest.mkdir()
    files=['contract.json','generated_solver.py','review.json','execution.json','container-inspect.json','output/checks.json','output/result1.xlsx','output/trajectories.npz','fault-probes/fault-probes.json','fault-probe-execution.json','metadata.json']
    for name in files:
        p=dest/name;p.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(source/name,p)
    # This test fixture models an equivalent mount in a cloned evidence directory.
    p=dest/'container-inspect.json';d=json.loads(p.read_text(encoding='utf-8'))
    for mount in d[0]['Mounts']:
        if mount['Destination']=='/work/solver.py':mount['Source']=str(dest/'generated_solver.py')
    p.write_text(json.dumps(d),encoding='utf-8')
    return dest,json.loads((source/'contract.json').read_text(encoding='utf-8'))

def test_validator_rejects_contract_mismatch(solver_copy):
    run,c=solver_copy;c['risks'].append('Changed contract')
    with pytest.raises(ResultError,match='Contract mismatch'):validate_run(run,c)

def test_validator_rejects_changed_code(solver_copy):
    run,c=solver_copy
    with (run/'generated_solver.py').open('a',encoding='utf-8') as f:f.write('\n# tampered copy\n')
    with pytest.raises(ResultError,match='review binding mismatch'):validate_run(run,c)

def test_validator_rejects_failed_self_report(solver_copy):
    run,c=solver_copy;p=run/'output/checks.json';d=json.loads(p.read_text(encoding='utf-8'));d['checks']['rod_distance']['status']='failed';p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(ResultError,match='not passed'):validate_run(run,c)

def test_validator_rejects_nonfinite_trajectory(solver_copy):
    run,c=solver_copy;p=run/'output/trajectories.npz'
    with np.load(p,allow_pickle=False) as a:data={k:a[k].copy() for k in a.files}
    data['position_m'][0,0,0]=float('nan');np.savez(p,**data)
    with pytest.raises(ResultError,match='Invalid position_m'):validate_run(run,c)
