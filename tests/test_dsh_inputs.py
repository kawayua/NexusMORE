"""Native question intake never accepts a model-selected file or user approval."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from modelcrew import dsh_inputs as native
from modelcrew.business_contract import BusinessContractError
from modelcrew.config import ROOT
from modelcrew.dsh_decisions import adapter_sha256
from modelcrew.workflow import Workflow

@pytest.fixture(scope='module')
def url():
    value=os.environ.get('MODELCREW_BUSINESS_TEST_URL')
    if not value:pytest.skip('Explicit disposable PostgreSQL probe required')
    with Workflow(value) as w:w.setup()
    return value


def frame(project):
    return {'protocol':native.PROTOCOL,'project_id':project,'host':{'instance_id':'intake-test','session_id':'session-'+uuid.uuid4().hex,'pid':os.getppid(),'adapter_sha256':adapter_sha256(),'engineering_only':False},'message':{'id':'message-'+uuid.uuid4().hex,'rpc_id':'rpc-'+uuid.uuid4().hex,'text':'给定三个无量纲数 2、4、6，求算术平均值。'}}


def test_private_intake_rejects_ordinary_shell_before_database():
    p=subprocess.run([sys.executable,'-m','modelcrew.dsh_inputs','--private-stdio'],input='{}\n',capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert p.returncode==1 and json.loads(p.stdout)['code']=='untrusted_user_event'


@pytest.mark.parametrize('change',['file','approval','host','blank','oversized'])
def test_intake_frame_does_not_accept_paths_decisions_or_wrong_host(change):
    v=frame('p')
    if change=='file':v['message']['file']='C:/private/secret.txt'
    elif change=='approval':v['decision']='approve'
    elif change=='host':v['host']['pid']=0
    elif change=='blank':v['message']['text']=' '
    else:v['message']['text']='x'*65537
    with pytest.raises(BusinessContractError):native.validate_input(v)


def test_native_text_is_owner_bound_immutable_idempotent_and_not_approval(url):
    project='native-input-test-'+uuid.uuid4().hex
    with Workflow(url) as w:w.create_project(project,'Synthetic native text intake')
    v=frame(project);workflow=lambda:Workflow(url)
    first=native.prepare(v,workflow,ROOT);second=native.prepare(copy.deepcopy(v),workflow,ROOT)
    assert first==second and first['user_approval_created'] is False
    assert first['input']['owner']==first['owner'] and first['owner']['version']==1
    assert first['input_observation']['observed']=={'format':'txt','pages':[{'page':1,'text':v['message']['text']}]}
    from modelcrew.inputs import inspect_file
    from modelcrew.business_artifacts import ArtifactRegistry
    with Workflow(url) as w:
        original,_=ArtifactRegistry(w,ROOT).resolve_input('artifact:'+first['input']['artifact_id'],first['owner'])
    assert Path(original).name=='content.txt'
    assert inspect_file(original,kind='document')['structure']['observed']==first['input_observation']['observed']
    changed=copy.deepcopy(v);changed['message']['text']='different facts'
    with pytest.raises(BusinessContractError):native.prepare(changed,workflow,ROOT)
    changed=copy.deepcopy(v);changed['project_id']='other'
    with pytest.raises(BusinessContractError):native.prepare(changed,workflow,ROOT)
    with Workflow(url) as w:
        row=w.db.execute('SELECT path FROM mc_business_artifacts WHERE artifact_id=%s',(first['input']['artifact_id'],)).fetchone()
        assert (ROOT/row['path']).read_text(encoding='utf-8')==v['message']['text']
        assert w.db.execute('SELECT 1 FROM mc_tasks WHERE id=%s',(first['owner']['task_id'],)).fetchone() is None
        assert w.db.execute('SELECT 1 FROM mc_events WHERE task_id=%s',(first['owner']['task_id'],)).fetchone() is None
