import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import pytest
from modelcrew import config,service_environment as service,environment_tools as tools
from modelcrew.package_resources import resource,verify_resources


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in list(os.environ):
        if name.startswith('MODELCREW_') or name=='TECTONIC_CACHE_DIR':monkeypatch.delenv(name)


def test_prepare_is_owned_idempotent_and_does_not_print_password(tmp_path):
    first=service.prepare(tmp_path)
    files={p.name:p.read_bytes() for p in (tmp_path/'configs/local').iterdir() if p.is_file()}
    second=service.prepare(tmp_path)
    assert first['project']==second['project'] and second['retained']
    assert files=={p.name:p.read_bytes() for p in (tmp_path/'configs/local').iterdir() if p.is_file()}
    credential=config.env_file_values(tmp_path/'configs/local/database.env')
    assert credential['MODELCREW_DB_PASSWORD'] not in json.dumps(first)
    assert len(credential['MODELCREW_DB_PASSWORD'])==64
    assert credential['MODELCREW_DB_PASSWORD'] in config.database_url(tmp_path)
    compose=json.loads(files['managed-services.compose.json'])
    assert 'container_name' not in str(compose)
    assert all(row['ports'][0].startswith('127.0.0.1:') for row in compose['services'].values())
    assert all('@sha256:' in row['image'] for row in compose['services'].values())


@pytest.mark.parametrize('value',['postgresql://private:FAKE_SECRET@localhost/db',''])
def test_existing_environment_database_is_not_adopted(tmp_path,monkeypatch,value):
    monkeypatch.setenv('MODELCREW_DATABASE_URL',value)
    with pytest.raises(service.EnvironmentError) as exc:service.prepare(tmp_path)
    assert 'FAKE_SECRET' not in str(exc.value)
    assert not (tmp_path/'configs/local/database.env').exists()


def test_existing_database_file_preserved(tmp_path):
    path=tmp_path/'configs/local/database.env';path.parent.mkdir(parents=True);path.write_bytes(b'old database bytes')
    with pytest.raises(service.EnvironmentError):service.prepare(tmp_path)
    assert path.read_bytes()==b'old database bytes'


def test_distinct_workspaces_never_share_project(tmp_path):
    first=service.prepare(tmp_path/'one');second=service.prepare(tmp_path/'two')
    assert first['project']!=second['project']
    assert first['project'].startswith('nexusmore-')


def test_project_tamper_blocks_docker_commands(tmp_path,monkeypatch):
    service.prepare(tmp_path);path=tmp_path/'configs/local/managed-services.json';value=json.loads(path.read_text());value['project']='stage-b';path.write_text(json.dumps(value))
    monkeypatch.setattr(service,'_docker',lambda *a,**k:pytest.fail('Must not invoke Docker after ownership tamper'))
    with pytest.raises(service.EnvironmentError,match='ownership'):service.operate('stop',tmp_path)


@pytest.mark.parametrize('filename',['database.env','managed-services.compose.json'])
def test_modified_managed_config_refuses_overwrite(tmp_path,filename):
    service.prepare(tmp_path);path=tmp_path/'configs/local'/filename;path.write_text('changed')
    with pytest.raises(service.EnvironmentError,match='changed'):service.prepare(tmp_path)
    assert path.read_text()=='changed'


def test_stop_keeps_volumes_and_never_uses_down(tmp_path,monkeypatch):
    service.prepare(tmp_path);calls=[]
    monkeypatch.setattr(service,'_engine',lambda:None)
    monkeypatch.setattr(service,'_compose',lambda root,state,args,**kw:calls.append(args))
    assert service.operate('stop',tmp_path)['volumes_deleted'] is False
    assert calls==[['stop']]


def test_operation_lock_excludes_another_process(tmp_path):
    service.prepare(tmp_path)
    with service._lock(tmp_path):
        with pytest.raises(service.EnvironmentError,match='locked'):service.prepare(tmp_path)
    assert not (tmp_path/'configs/local/service-operation.lock').exists()


def test_docker_errors_are_stable_and_redacted(monkeypatch):
    monkeypatch.setattr(service.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a,1,'','permission denied FAKE_SECRET'))
    with pytest.raises(service.EnvironmentError,match='permission_denied') as exc:service._engine()
    assert 'FAKE_SECRET' not in str(exc.value)


def test_changed_active_database_cannot_be_migrated(tmp_path,monkeypatch):
    service.prepare(tmp_path);state=service._state(tmp_path)
    monkeypatch.setenv('MODELCREW_DATABASE_URL','postgresql://other:FAKE_SECRET@localhost/other')
    with pytest.raises(service.EnvironmentError,match='differs') as exc:service._database(tmp_path,state)
    assert 'FAKE_SECRET' not in str(exc.value)


def test_explicit_qdrant_not_overwritten(tmp_path,monkeypatch):
    monkeypatch.setenv('MODELCREW_QDRANT_URL','http://127.0.0.1:6333')
    with pytest.raises(service.EnvironmentError,match='Qdrant'):service.prepare(tmp_path)
    assert not (tmp_path/'configs/local/database.env').exists()


def test_offline_missing_default_executor_never_builds(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'_engine',lambda:None)
    def missing(*a,**kw):raise service.EnvironmentError('missing')
    monkeypatch.setattr(service,'_docker',missing)
    with pytest.raises(service.EnvironmentError,match='offline'):service.executor(tmp_path,offline=True)
    assert not (tmp_path/'configs/local/executor-build').exists()


def test_missing_custom_executor_never_falls_back(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'_engine',lambda:None);monkeypatch.setenv('MODELCREW_EXECUTION_IMAGE','user:custom')
    def missing(*a,**kw):raise service.EnvironmentError('missing')
    monkeypatch.setattr(service,'_docker',missing)
    with pytest.raises(service.EnvironmentError,match='Custom'):service.executor(tmp_path)


@pytest.mark.parametrize('line,name,version',[('pandoc.exe 3.6.4','pandoc','3.6.4'),('Tectonic 0.17.0','tectonic','0.17.0')])
def test_actual_windows_version_forms(monkeypatch,line,name,version):
    monkeypatch.setattr(tools.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a,0,line+'\n',''))
    assert tools._version('unused',name,version)==line


def test_nearby_native_version_is_not_supported(monkeypatch):
    monkeypatch.setattr(tools.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a,0,'Tectonic 0.17.01',''))
    with pytest.raises(service.EnvironmentError,match='Unsupported'):tools._version('unused','tectonic','0.17.0')


@pytest.mark.parametrize('member',['../escape','C:/escape','file:stream'])
def test_archive_paths_cannot_escape(tmp_path,member):
    archive=tmp_path/'test.zip'
    with zipfile.ZipFile(archive,'w') as package:package.writestr(member,b'bad')
    with pytest.raises(service.EnvironmentError,match='Unsafe'):tools._extract(archive,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_archive_link_rejected(tmp_path):
    archive=tmp_path/'test.zip';info=zipfile.ZipInfo('link');info.external_attr=(0o120777<<16)
    with zipfile.ZipFile(archive,'w') as package:package.writestr(info,b'../../outside')
    with pytest.raises(service.EnvironmentError,match='Unsafe'):tools._extract(archive,tmp_path/'output')


def test_download_hash_failure_does_not_publish_cache(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'archive.zip').write_bytes(b'bad')
    destination=tmp_path/'downloads';destination.mkdir()
    with pytest.raises(service.EnvironmentError,match='SHA256'):tools._download({'filename':'archive.zip','bytes':3,'sha256':'0'*64},destination,offline=True,archives=source)
    assert not list(destination.iterdir())


def test_resource_catalog_and_synthetic_contract_are_real():
    from modelcrew.contracts import validate
    validate(json.loads(resource('environment/example-contract.json').read_text()))
    spec=json.loads(resource('environment/native-tools.json').read_text())
    assert spec['downloads']['python-embedded']['version']=='3.13.5'
    assert spec['embedding']['revision']=='f03589ceff5aac7111bd60cfc7d497ca17ecac65'
    assert verify_resources()['files']>=223


def test_offline_up_never_pulls_images(tmp_path,monkeypatch):
    service.prepare(tmp_path);calls=[]
    monkeypatch.setattr(service,'_engine',lambda:None)
    monkeypatch.setattr(service,'_compose',lambda root,state,args,**kw:calls.append(args))
    monkeypatch.setattr(service,'status',lambda root:{'status':'passed'})
    service.operate('up',tmp_path,offline=True)
    assert '--pull' in calls[1] and calls[1][calls[1].index('--pull')+1]=='never'


def test_model_preparation_copy_is_private_and_tampering_is_rejected(tmp_path,monkeypatch):
    from modelcrew import environment_retrieval
    from modelcrew.user_workspace import initialize
    from modelcrew import retrieval
    from types import SimpleNamespace
    initialize(tmp_path);source=tmp_path/'provided-model';source.mkdir()
    spec=json.loads(resource('environment/native-tools.json').read_text())['embedding']
    for name in spec['files']:
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'synthetic unit-test file')
    monkeypatch.setattr(retrieval,'LocalBge',lambda path:SimpleNamespace(signature='unit-test-signature',dimension=3))
    first=environment_retrieval.embedding(tmp_path,source=source,offline=True)
    assert first['source_kind']=='explicit_local_directory_not_upstream_attestation'
    assert first['semantic_quality_verified'] is False
    destination=Path(first['model_directory']);assert destination.is_relative_to(tmp_path/'configs/local')
    assert environment_retrieval.embedding(tmp_path,offline=True)['retained']
    (destination/'config.json').write_bytes(b'changed')
    with pytest.raises(service.EnvironmentError,match='changed'):environment_retrieval.embedding(tmp_path,offline=True)
