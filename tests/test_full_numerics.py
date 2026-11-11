"""D4 independent numerical and immutable result boundaries; no model or Docker calls."""
import copy,json
from pathlib import Path
import numpy as np
import pytest
from modelcrew import full_result
from modelcrew.full_numerics import numeric_checks,load_arrays
from modelcrew.collaboration import sha_file
from modelcrew.config import ROOT
from scripts.reference_2024_a_q1 import solve


@pytest.fixture(scope='module')
def numerical_fixture():
    contract=json.loads((ROOT/'stage-b-plus/examples/contract-v2-snapshot.json').read_text(encoding='utf-8'))
    parameters=json.loads((ROOT/'stage-a/2024-A-problem-1/parameters.json').read_text(encoding='utf-8'))
    rows=[solve(t,parameters) for t in range(301)]
    arrays={'time_s':np.arange(301,dtype=float),'theta_rad':np.stack([r[0] for r in rows]),'position_m':np.stack([r[1] for r in rows]),'velocity_m_s':np.stack([r[2] for r in rows])}
    arrays['speed_m_s']=np.linalg.norm(arrays['velocity_m_s'],axis=2)
    refined=[{'time_s':t,'xtol':5e-15,'max_position_difference_m':float(np.max(np.linalg.norm(solve(t,parameters,xtol=5e-15)[1]-arrays['position_m'][t],axis=1)))} for t in [0,60,120,180,240,300]]
    return arrays,contract,{'root_refinement':refined}


def test_full_numeric_checks_accept_all_valid_times(numerical_fixture):
    arrays,contract,report=numerical_fixture
    result=numeric_checks(arrays,contract,report,compare_reference=False)
    assert result['passed'] and len(result['series']['rod_distance_error_m'])==301


@pytest.mark.parametrize('key,index,delta,check',[('position_m',(137,90,0),.01,'rod_distance'),('velocity_m_s',(222,30,0),.01,'rigid_velocity'),('speed_m_s',(280,0),.01,'head_speed')])
def test_full_numeric_rejects_errors_outside_old_minimal_samples(numerical_fixture,key,index,delta,check):
    arrays,contract,report=numerical_fixture
    changed={name:a.copy() for name,a in arrays.items()};changed[key][index]+=delta
    result=numeric_checks(changed,contract,report,compare_reference=False)
    assert not result['passed'] and not result['checks'][check]['passed']


def test_full_time_axis_and_missing_refinement_rejected(numerical_fixture):
    arrays,contract,report=numerical_fixture
    changed={name:a.copy() for name,a in arrays.items()};changed['time_s'][137]=136
    with pytest.raises(ValueError,match='time axis'):numeric_checks(changed,contract,report,compare_reference=False)
    with pytest.raises(ValueError,match='refinement'):numeric_checks(arrays,contract,{},compare_reference=False)


def test_full_array_reader_rejects_truncated_time_and_nonfinite(tmp_path,numerical_fixture):
    arrays,_,_=numerical_fixture
    p=tmp_path/'values.npz';np.savez(p,**{k:v[:-1] for k,v in arrays.items()})
    with pytest.raises(ValueError,match='Invalid full arrays'):load_arrays(p)
    bad={k:v.copy() for k,v in arrays.items()};bad['position_m'][250,90,1]=np.nan
    np.savez(p,**bad)
    with pytest.raises(ValueError,match='Invalid full arrays'):load_arrays(p)


@pytest.fixture
def frozen(tmp_path,monkeypatch):
    monkeypatch.setattr(full_result,'ROOT',tmp_path)
    folder=tmp_path/'stage-d/runs/full/test-case';folder.mkdir(parents=True)
    required=['contract.json','generated_solver.py','numerical-core.py','output/trajectories.npz','output/result1.xlsx','output/checks.json','independent-numerics.json','figure-manifest.json','figure-qa.json','visual-review.json','reproduction.json','fault-probes.json']
    files=[]
    for name in required:
        p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('UNIT_FIXTURE_ONLY',encoding='utf-8')
        files.append({'path':p.relative_to(tmp_path).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size})
    manifest={'binding':{'unit_fixture':True},'artifacts':files}
    (folder/'frozen-artifacts.json').write_text(json.dumps(manifest),encoding='utf-8')
    return folder,manifest


def test_full_frozen_file_set_verifies_hashes(frozen):
    folder,_=frozen
    _,paths=full_result.verify_frozen_files(folder)
    assert len(paths)==12


@pytest.mark.parametrize('target',['generated_solver.py','output/trajectories.npz','output/result1.xlsx','figure-manifest.json'])
def test_reviewed_full_artifact_tampering_rejected(frozen,target):
    folder,_=frozen;(folder/target).write_text('CHANGED',encoding='utf-8')
    with pytest.raises(ValueError,match='artifact changed'):full_result.verify_frozen_files(folder)


@pytest.mark.parametrize('mutation',['duplicate','escape','incomplete'])
def test_frozen_manifest_cannot_escape_duplicate_or_omit_required_outputs(frozen,mutation,tmp_path):
    folder,manifest=frozen
    if mutation=='duplicate':manifest['artifacts'].append(manifest['artifacts'][0])
    elif mutation=='escape':
        p=tmp_path/'outside.txt';p.write_text('outside');manifest['artifacts'][0]={'path':'outside.txt','sha256':sha_file(p),'size_bytes':p.stat().st_size}
    else:manifest['artifacts'].pop()
    (folder/'frozen-artifacts.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError):full_result.verify_frozen_files(folder)

def test_frozen_execution_replay_only_reads_existing_receipts(tmp_path,monkeypatch):
    from scripts import run_d4_full as runner
    folder=tmp_path/'frozen';folder.mkdir();(folder/'frozen-artifacts.json').write_text('TEST_MARKER')
    calls=[]
    monkeypatch.setattr(full_result,'verify_frozen_files',lambda path:calls.append('verify'))
    def existing(folder,key):
        calls.append(key)
        return {'status':'code_error' if key.endswith('probe') else 'succeeded'},{}
    monkeypatch.setattr(runner,'read_execution',existing)
    monkeypatch.setattr(runner,'run_job',lambda *a:pytest.fail('Frozen replay must never dispatch or rewrite execution'))
    runner.execute(folder)
    assert calls==['verify','primary','reproduction','guard-probe','bracket-probe','verify']
    assert (folder/'frozen-artifacts.json').read_text()=='TEST_MARKER'
