"""Tamper and path-boundary checks for Q2 full-result admission."""
import json
from pathlib import Path
import pytest
from modelcrew.collaboration import sha_file
from modelcrew.q2_full_result import verify_q2_frozen_files
import modelcrew.q2_full_result as module

def package(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'ROOT',tmp_path)
    folder=tmp_path/'stage-d/runs/full/case';folder.mkdir(parents=True)
    names=['full-base.py','contract.json','inputs.json','code-evidence.json','execution-evidence.json','result-evidence.json','validation.json','reproduction.json','support-certificate.json','figures.json','results/terminal-state.npz','results/result2.xlsx','results/continuous-certificate.npz','results/selected-handles.json','collision-event.json']
    items=[]
    for name in names:
        p=folder/name;p.parent.mkdir(exist_ok=True);p.write_bytes(b'original bytes')
        items.append({'path':p.relative_to(tmp_path).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size})
    (folder/'frozen-artifacts.json').write_text(json.dumps({'artifacts':items}),encoding='utf-8')
    return folder

def test_q2_frozen_output_tamper_blocks_admission(tmp_path,monkeypatch):
    folder=package(tmp_path,monkeypatch);verify_q2_frozen_files(folder)
    (folder/'results/result2.xlsx').write_bytes(b'changed bytes!')
    with pytest.raises(ValueError,match='changed'):verify_q2_frozen_files(folder)

def test_q2_frozen_manifest_cannot_reference_outside_run(tmp_path,monkeypatch):
    folder=package(tmp_path,monkeypatch);p=folder/'frozen-artifacts.json';data=json.loads(p.read_text())
    other=tmp_path/'outside.bin';other.write_bytes(b'external')
    data['artifacts'].append({'path':'outside.bin','sha256':sha_file(other),'size_bytes':other.stat().st_size});p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='invalid'):verify_q2_frozen_files(folder)

def test_q2_frozen_manifest_must_include_contact_certificate(tmp_path,monkeypatch):
    folder=package(tmp_path,monkeypatch);p=folder/'frozen-artifacts.json';data=json.loads(p.read_text());data['artifacts']=[x for x in data['artifacts'] if not x['path'].endswith('support-certificate.json')];p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='incomplete'):verify_q2_frozen_files(folder)
