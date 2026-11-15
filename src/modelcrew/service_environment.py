"""Workspace-owned Docker services. Never touch legacy projects or delete data volumes."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import urllib.request
import uuid
from . import config
from .package_resources import resource
from .repository_migration import relative_path


class EnvironmentError(RuntimeError):
    pass


def _root(root=None):
    return config.workspace_path(root if root is not None else config.ROOT)


def _path(root,name):
    return relative_path(root,'configs/local/'+name,strict_root=False)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


@contextmanager
def _lock(root):
    path=_path(root,'service-operation.lock');path.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise EnvironmentError('Service operation already locked; inspect the prior process before removing its lock') from None
    try:
        os.write(fd,str(os.getpid()).encode());os.close(fd);yield
    finally:path.unlink()


def _project(root):
    return 'nexusmore-'+hashlib.sha256(str(root).casefold().encode()).hexdigest()[:16]


def _port(preferred):
    with socket.socket() as connection:
        try:connection.bind(('127.0.0.1',preferred))
        except OSError:connection.bind(('127.0.0.1',0))
        return connection.getsockname()[1]


def _docker(args,*,timeout=120):
    try:
        result=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.SubprocessError):
        raise EnvironmentError('Docker command unavailable or timed out; inspect service status before retrying') from None
    if result.returncode:
        reason='permission_denied' if any(text in result.stderr.lower() for text in ['permission denied','access is denied']) else 'command_failed'
        raise EnvironmentError('Docker '+reason+'; check engine, network, port conflicts and current process permissions')
    return result.stdout


def _engine():
    if _docker(['info','--format','{{.OSType}}'],timeout=20).strip()!='linux':
        raise EnvironmentError('Docker Linux containers are required')


def _compose(root,state,args,timeout=180):
    return _docker(['compose','-p',state['project'],'--env-file',_path(root,'database.env'),
        '-f',_path(root,'managed-services.compose.json'),*args],timeout=timeout)


def _state(root):
    path=_path(root,'managed-services.json')
    if not path.is_file():raise EnvironmentError('Managed services are not prepared; run environment prepare')
    try:state=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,OSError):raise EnvironmentError('Invalid managed-service manifest') from None
    if not isinstance(state,dict) or state.get('schema_version')!='1.0.0' or state.get('project')!=_project(root):
        raise EnvironmentError('Service ownership/workspace mismatch; do not reuse another workspace manifest')
    if not isinstance(state.get('files'),dict) or set(state['files'])!={'managed-services.compose.json','database.env'} or any(type(state.get(key)) is not int or not 1<=state[key]<=65535 for key in ['postgres_port','qdrant_port']):
        raise EnvironmentError('Invalid service ownership/configuration manifest')
    for name in ['managed-services.compose.json','database.env']:
        if _sha(_path(root,name))!=state['files'][name]:
            raise EnvironmentError('Managed-service configuration changed; recover its original files, never replace credentials automatically')
    return state


def prepare(root=None):
    from .user_workspace import initialize
    root=_root(root);initialize(root)
    with _lock(root):
        if _path(root,'managed-services.json').exists():
            state=_state(root)
            return {'status':'prepared','project':state['project'],'retained':True,'services_started':False}
        # Existing user/legacy databases are not automatically adopted or overwritten.
        for name in ['database.env','managed-services.compose.json']:
            if _path(root,name).exists():raise EnvironmentError('Existing/partial service configuration; use a new workspace or recover the original manifest')
        if 'MODELCREW_DATABASE_URL' in os.environ:raise EnvironmentError('Explicit database URL cannot be replaced')
        try:config.database_url(root)
        except RuntimeError:pass
        else:raise EnvironmentError('An existing database URL is configured; choose an unconfigured workspace for managed services')
        if os.environ.get('MODELCREW_DATABASE_CONFIG') or config.load_settings(root)['database']['url_env']!='MODELCREW_DATABASE_URL':
            raise EnvironmentError('Explicit database configuration cannot be overwritten by managed services')
        if os.environ.get('MODELCREW_CONFIG'):
            raise EnvironmentError('Managed preparation requires the workspace settings file, not an external configuration')
        settings_path=config.settings_path(root);settings=config.load_settings(root)
        if os.environ.get('MODELCREW_QDRANT_URL') or settings['retrieval']['qdrant_url']!='http://127.0.0.1:56333':
            raise EnvironmentError('Explicit Qdrant endpoint cannot be silently replaced; choose a new workspace')
        spec=json.loads(resource('deployment/managed-services.json').read_text(encoding='utf-8'))
        pg_port=_port(spec['postgres']['preferred_host_port']);q_port=_port(spec['qdrant']['preferred_host_port'])
        if pg_port==q_port:q_port=_port(0)
        project=_project(root);password=secrets.token_hex(32)
        url=f'postgresql://modelcrew:{password}@127.0.0.1:{pg_port}/modelcrew'
        compose={'services':{
            'postgres':{'image':spec['postgres']['image'],'platform':'linux/amd64','restart':'unless-stopped',
                'environment':{'POSTGRES_DB':'modelcrew','POSTGRES_USER':'modelcrew','POSTGRES_PASSWORD':'${MODELCREW_DB_PASSWORD:?local password required}'},
                'ports':[f'127.0.0.1:{pg_port}:5432'],'volumes':['postgres-data:/var/lib/postgresql/data'],
                'healthcheck':{'test':['CMD-SHELL','pg_isready -U modelcrew -d modelcrew'],'interval':'3s','timeout':'3s','retries':30}},
            'qdrant':{'image':spec['qdrant']['image'],'platform':'linux/amd64','restart':'unless-stopped',
                'ports':[f'127.0.0.1:{q_port}:6333'],'volumes':['qdrant-data:/qdrant/storage']}},
            'volumes':{'postgres-data':{},'qdrant-data':{}}}
        _write(_path(root,'database.env'),'MODELCREW_DB_PASSWORD='+password+'\nMODELCREW_DATABASE_URL='+url+'\n')
        _write(_path(root,'managed-services.compose.json'),compose)
        # Preserve the original user settings before the single declared endpoint change.
        _write(_path(root,'settings.before-services.json'),settings_path.read_text(encoding='utf-8'))
        settings['retrieval']['qdrant_url']=f'http://127.0.0.1:{q_port}'
        temp=_path(root,'settings.services.tmp');_write(temp,settings);os.replace(temp,settings_path)
        state={'schema_version':'1.0.0','project':project,'postgres_port':pg_port,'qdrant_port':q_port,
            'spec_sha256':hashlib.sha256(resource('deployment/managed-services.json').read_bytes()).hexdigest(),
            'images':{name:spec[name]['image'] for name in ['postgres','qdrant']},
            'files':{name:_sha(_path(root,name)) for name in ['database.env','managed-services.compose.json']}}
        _write(_path(root,'managed-services.json'),state)
    return {'status':'prepared','project':project,'retained':False,'services_started':False,
        'ports':{'postgres':pg_port,'qdrant':q_port},'credentials':'generated_locally_not_displayed'}


def _database(root,state):
    local=config.env_file_values(_path(root,'database.env'))['MODELCREW_DATABASE_URL']
    if config.database_url(root)!=local:raise EnvironmentError('Active database configuration differs from the managed database; refusing migration or probe')
    return local


def status(root=None):
    root=_root(root);state=_state(root);checks={}
    try:_engine();checks['docker_linux']={'status':'passed'}
    except EnvironmentError as exc:checks['docker_linux']={'status':'blocked','reason':str(exc)}
    try:
        import psycopg
        with psycopg.connect(_database(root,state),connect_timeout=3) as connection:
            row=connection.execute("SELECT current_setting('server_version_num')::int").fetchone()
        checks['postgres']={'status':'passed' if 160000<=row[0]<170000 else 'wrong_version','server_version_num':row[0]}
    except Exception:checks['postgres']={'status':'unavailable','reason':'Check owned PostgreSQL, URL binding, credentials and workflow dependency'}
    try:
        endpoint=f'http://127.0.0.1:{state["qdrant_port"]}'
        with urllib.request.urlopen(endpoint+'/healthz',timeout=3) as response: healthy=response.status==200
        with urllib.request.urlopen(endpoint+'/',timeout=3) as response:version=json.load(response)['version']
        checks['qdrant']={'status':'passed' if healthy and version=='1.19.1' else 'wrong_version','version':version}
    except Exception:checks['qdrant']={'status':'unavailable','reason':'Check owned Qdrant endpoint'}
    return {'status':'passed' if all(v['status']=='passed' for v in checks.values()) else 'incomplete','project':state['project'],
        'checks':checks,'volumes_deleted':False,'scope':'Service versions/connectivity; index content, approvals and restore remain separate'}


def operate(action,root=None,*,timeout=180,offline=False):
    if action not in {'up','restart','stop','migrate'}:raise ValueError('Unknown managed-service action')
    root=_root(root)
    with _lock(root):
        state=_state(root);_engine()
        if action!='stop':
            import importlib.util
            if importlib.util.find_spec('psycopg') is None:raise EnvironmentError('Install nexusmore[workflow] before starting or migrating managed services')
        if action=='migrate':
            from .workflow import Workflow
            with Workflow(url=_database(root,state)) as workflow:
                workflow.setup()
                versions=[row['version'] for row in workflow.db.execute('SELECT version FROM mc_migrations ORDER BY version').fetchall()]
            return {'status':'migrated','versions':versions,'project':state['project'],'user_approval':False}
        if action=='stop':
            _compose(root,state,['stop'],timeout=timeout)
            return {'status':'stopped','project':state['project'],'volumes_deleted':False}
        _compose(root,state,['config','--quiet'],timeout=30)
        _compose(root,state,['up','-d',*(['--pull','never'] if offline else []),'--wait','--wait-timeout',str(timeout-15)] if action=='up' else ['restart'],timeout=timeout)
        deadline=time.monotonic()+min(timeout,90)
        while True:
            report=status(root)
            if report['status']=='passed':return report
            if time.monotonic()>=deadline:raise EnvironmentError('Managed services did not become healthy; keep volumes/configuration and inspect status')
            time.sleep(1)


def executor(root=None,*,offline=False):
    root=_root(root);_engine()
    image=config.configured('MODELCREW_EXECUTION_IMAGE','modelcrew-reference:py313',root=root)
    try:raw=_docker(['image','inspect',image,'--format','{{.Id}}'])
    except EnvironmentError:
        if offline:raise EnvironmentError('Executor image missing in offline mode') from None
        if image!='modelcrew-reference:py313':raise EnvironmentError('Custom image missing; refusing to replace it with a default') from None
        folder=_path(root,'executor-build');folder.mkdir(exist_ok=False)
        _write(folder/'Dockerfile',resource('deployment/Dockerfile.runtime').read_text(encoding='utf-8'))
        _docker(['build','--pull=false','--platform','linux/amd64','-t',image,'-f',folder/'Dockerfile',folder],timeout=600)
        raw=_docker(['image','inspect',image,'--format','{{.Id}}'])
    return {'status':'available','image':image,'image_id':raw.strip(),'fallback':False}
