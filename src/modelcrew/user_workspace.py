"""Initialize and inspect a user workspace without installing tools or calling a model."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request
from . import config


def _safe(root, relative):
    from .repository_migration import relative_path
    return relative_path(root, relative, strict_root=False)


def initialize(root=None):
    root = config.workspace_path(root if root is not None else config.ROOT)
    # Fail before touching files when an existing explicit configuration is invalid.
    config.load_settings(root)
    from .runtime_paths import data_root
    data = data_root(root)
    directories = ['configs/local', data.relative_to(root).as_posix(), 'artifacts', 'output']
    for item in directories: _safe(root, item)
    settings = root/'configs/local/settings.json'
    secrets = root/'configs/local/secrets.env'
    for path in (settings, secrets):
        _safe(root, path.relative_to(root).as_posix())
        if path.exists() and not path.is_file(): raise ValueError('Configuration target is not a regular file')
    root.mkdir(parents=True, exist_ok=True)
    for item in directories: _safe(root,item).mkdir(parents=True, exist_ok=True)
    files = {
        settings: json.dumps(config.DEFAULTS,ensure_ascii=False,indent=2)+'\n',
        secrets: '# Private credentials. Prefer process/user environment variables. Never commit this file.\n'
                 '# MODELCREW_LLM_API_KEY=\n# MODELCREW_DATABASE_URL=\n',
        root/'configs/local/settings.schema.json':json.dumps(config.SCHEMA,indent=2)+'\n',
        root/'.gitignore':'/configs/local/\n/runs/\n/artifacts/\n/output/\n',
    }
    created, retained = [], []
    for path, text in files.items():
        _safe(root,path.relative_to(root).as_posix())
        try:
            fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        except FileExistsError:
            retained.append(path.relative_to(root).as_posix()); continue
        with os.fdopen(fd,'w',encoding='utf-8') as stream: stream.write(text)
        created.append(path.relative_to(root).as_posix())
    return {'status':'initialized','workspace':str(root),'created':created,'retained':retained,
            'services_started':False,'model_called':False,'credentials_generated':False}


def configuration_summary(root=None):
    root = Path(root) if root is not None else config.ROOT
    settings = config.load_settings(root)
    from .runtime_paths import data_root
    from .retrieval_paths import algorithm_config_path, paper_config_path
    from .execution_paths import execution_directory
    model = config.model_environment(root)
    # Only expose presence and paths; never echo endpoints, names, credentials or arbitrary config values.
    return {'schema_version':settings['schema_version'],'workspace':str(root),
        'settings_file':str(config.settings_path(root)), 'data_directory':str(data_root(root)),
        'paper_index_file':str(paper_config_path(root)), 'algorithm_index_file':str(algorithm_config_path(root)),
        'algorithm_retrieval_mode':'explicit_legacy_vector' if config.configured('MODELCREW_ALGORITHM_CONFIG',root=root) is not None else 'installed_literal_lookup',
        'execution_directory':str(execution_directory(root)),
        'model':{key:bool(model.get('MODELCREW_LLM_'+key.upper())) for key in ('provider','base_url','model','api_key')},
        'secrets':'redacted','precedence':'explicit argument > process environment > settings.json > default; secrets.env > legacy .env'}


def _distribution(name):
    try: return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: return None


def doctor(root=None, *, profile='core', services=False):
    if profile not in {'core','workflow','full'}: raise ValueError('Unknown diagnostic profile')
    root = Path(root) if root is not None else config.ROOT
    checks = []
    def add(name, passed, action='', **extra):
        checks.append({'name':name,'status':'passed' if passed else 'missing_or_invalid','action':action if not passed else '',**extra})
    config.workspace_path(root)
    summary = configuration_summary(root)
    add('initialized', (root/'configs/local/settings.json').is_file(), 'Run modelcrew init in this workspace')
    add('workspace_writable',root.is_dir() and os.access(root,os.W_OK), 'Choose a writable user workspace')
    add('release_platform',platform.system()=='Windows' and platform.machine().lower() in {'amd64','x86_64'} and
        platform.python_implementation()=='CPython' and sys.version_info[:2]==(3,13),
        'First release requires Windows x86_64 and CPython 3.13')
    from .package_resources import verify_resources
    verify_resources(); add('package_resources',True)
    dependencies = {'jsonschema':'core'}
    if profile in {'workflow','full'}:
        dependencies.update({'psycopg':'workflow','langgraph':'workflow','mcp':'workflow','httpx':'workflow','pydantic':'workflow'})
        model = config.model_environment(root)
        add('model_configuration', all(model.get('MODELCREW_LLM_'+key) for key in ('API_KEY','BASE_URL','MODEL')),
            'Set API key, endpoint and model explicitly; no provider fallback')
        try: url = config.database_url(root); add('database_configuration',True)
        except (ValueError,RuntimeError,OSError): url = None; add('database_configuration',False,'Set database URL in the configured environment variable or secrets.env')
        add('docker_command',bool(shutil.which('docker')),'Install/start Docker Desktop with Linux containers (F4)')
    if profile=='full':
        dependencies.update({'qdrant-client':'retrieval','sentence-transformers':'retrieval','numpy':'figures',
            'matplotlib':'figures','scipy':'evidence','sympy':'evidence','python-docx':'documents',
            'openpyxl':'documents','pypdf':'documents','pymupdf':'paper'})
        for label, key in [('paper_index','paper_index_file'),('algorithm_index','algorithm_index_file')]:
            if label=='algorithm_index' and summary['algorithm_retrieval_mode']=='installed_literal_lookup':
                try:
                    from .algorithm_knowledge import load_catalog
                    catalog=load_catalog()
                    add(label,True,mode='installed_literal_lookup',algorithms=catalog['canonical_algorithm_count'],embedding_required=False)
                except (ValueError,OSError):
                    add(label,False,'Repair installed algorithm resources; no legacy fallback',mode='installed_literal_lookup')
                continue
            path=Path(summary[key])
            try:
                index=json.loads(path.read_text(encoding='utf-8-sig'))
                required={'model_path','embedding_signature','qdrant_url','collection'} | ({'catalog_path','catalog_sha256'} if label=='algorithm_index' else {'corpus_sha256'})
                ok=all(isinstance(index.get(field),str) and index[field] for field in required)
                if ok and label=='algorithm_index':
                    import hashlib
                    from .retrieval_paths import algorithm_catalog_path
                    from .project_assets import asset_path
                    catalog=json.loads(algorithm_catalog_path(root,index['catalog_path']).read_text(encoding='utf-8-sig'))
                    ok=catalog['catalog_sha256']==index['catalog_sha256'] and hashlib.sha256(asset_path(root,'resources/algorithms/index.md').read_bytes()).hexdigest()==catalog['index']['sha256']
            except (ValueError,KeyError,TypeError,OSError):ok=False
            add(label,ok,'Build a new versioned index when missing or stale; never modify historical index identities')
        model_path = config.configured('MODELCREW_EMBEDDING_MODEL',root=root)
        add('retrieval_weights',bool(model_path and (root/Path(model_path)).is_dir()),'Configure local embedding weights; F3 never downloads weights')
        from .tool_discovery import discover_tool, ToolUnavailable
        for name in ('pandoc','tectonic'):
            try: discover_tool(name,root=root); add(name+'_path',True)
            except (ValueError,RuntimeError,OSError,ToolUnavailable): add(name+'_path',False,'Configure supported native tool path (F4)')
    for package, extra in dependencies.items():
        version = _distribution(package)
        add('dependency:'+package,version is not None,'Install nexusmore['+extra+']' if extra!='core' else 'Reinstall nexusmore',version=version)
    if services:
        if profile=='core': raise ValueError('Service probes require workflow or full profile')
        try:
            run = subprocess.run(['docker','info','--format','{{.OSType}}'],capture_output=True,text=True,timeout=15)
            error=run.stderr.lower()
            category='permission_denied' if 'permission denied' in error or 'access is denied' in error else 'engine_unavailable_or_wrong_mode'
            add('docker_linux',run.returncode==0 and run.stdout.strip()=='linux',
                'Check Docker Linux engine and current process permissions',
                failure_category=None if run.returncode==0 and run.stdout.strip()=='linux' else category)
        except (OSError,subprocess.SubprocessError): add('docker_linux',False,'Check Docker executable, Linux engine and current process permissions',failure_category='probe_unavailable')
        try:
            if not url: raise RuntimeError('No database URL')
            import psycopg
            with psycopg.connect(url,connect_timeout=3) as connection:
                with connection.cursor() as cursor: cursor.execute('SELECT 1'); ok=cursor.fetchone()==(1,)
            add('postgresql_connection',ok,'Check PostgreSQL service and credentials')
        except Exception: add('postgresql_connection',False,'Check PostgreSQL service, credentials and workflow dependencies')
        if profile=='full':
            try:
                endpoint=config.configured('MODELCREW_QDRANT_URL',root=root).rstrip('/')+'/healthz'
                with urllib.request.urlopen(endpoint,timeout=3) as response: ok=response.status==200
                add('qdrant_health',ok,'Check Qdrant service')
            except Exception: add('qdrant_health',False,'Check Qdrant service')
    return {'status':'passed' if all(row['status']=='passed' for row in checks) else 'incomplete',
        'profile':profile,'configuration':summary,'checks':checks,'service_probes':services,
        'model_called':False,'downloads':False,'independent_review':False,
        'deferred_checks':['native tool versions and real rendering (F4)','embedding quality and live index integrity (F6)','Harness end-to-end and independent review nodes (G/H)'],
        'scope':'Configuration/environment diagnosis only; not an end-to-end or paper approval'}
