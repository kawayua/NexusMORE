from pathlib import Path
import uuid
import pytest
from modelcrew.runtime_paths import run_directory, data_root


def test_new_runs_are_function_named_and_legacy_runs_remain_readable(tmp_path):
    key=str(uuid.uuid4())
    assert run_directory(tmp_path,'hands',key)==tmp_path/'runs/hands'/key
    legacy=tmp_path/'stage-d/runs/runtime'/key
    legacy.mkdir(parents=True)
    assert run_directory(tmp_path,'hands',key)==legacy
    with pytest.raises(FileExistsError):
        run_directory(tmp_path,'hands',key,new=True)
    current=tmp_path/'runs/hands'/key;current.mkdir(parents=True)
    with pytest.raises(ValueError,match='Conflicting'):
        run_directory(tmp_path,'hands',key)


def test_configured_data_root_and_scope(tmp_path,monkeypatch):
    monkeypatch.setenv('MODELCREW_DATA_DIR','local-data')
    key=str(uuid.uuid4())
    assert run_directory(tmp_path,'assembly-inputs',key)==tmp_path/'local-data/assembly-inputs'/key
    for unsafe in ['..','modelcrew/private','src/private','.']:
        monkeypatch.setenv('MODELCREW_DATA_DIR',unsafe)
        with pytest.raises(ValueError):
            data_root(tmp_path)


@pytest.mark.parametrize('kind', ['hands','modeling','assembly-inputs','assembly-builds'])
def test_all_new_run_kinds_stay_outside_stage_directories(tmp_path,kind):
    assert run_directory(tmp_path,kind,uuid.uuid4(),new=True).relative_to(tmp_path).parts[0]=='runs'


def test_unsafe_runtime_identifiers_and_kinds_rejected(tmp_path):
    with pytest.raises(ValueError):
        run_directory(tmp_path,'hands','../outside')
    with pytest.raises(ValueError):
        run_directory(tmp_path,'unknown',uuid.uuid4())
