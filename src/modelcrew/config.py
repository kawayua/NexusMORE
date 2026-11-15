"""Versioned user settings. Secrets and connection strings must never be printed."""
from pathlib import Path
import copy
import json
import os
import sys
from jsonschema import Draft202012Validator

_PACKAGE = Path(__file__).resolve().parent
_SOURCE_ROOT = _PACKAGE.parents[1] if _PACKAGE.parent.name == 'src' else None


def workspace_path(explicit=None):
    value = explicit if explicit is not None else os.environ.get('MODELCREW_WORKSPACE')
    if value is not None:
        if not str(value).strip():
            raise ValueError('MODELCREW_WORKSPACE must not be empty')
        path = Path(value).expanduser().absolute()
    elif _SOURCE_ROOT is not None:
        path = _SOURCE_ROOT  # Existing checkout/history remains an explicit development path.
    else:
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')
        path = base/'NexusMORE/workspace'
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved.is_relative_to(_PACKAGE):
        raise ValueError('Workspace must be a dedicated user directory outside the package')
    if resolved.is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError('Workspace must be outside the Python installation')
    if path.exists() and not path.is_dir():
        raise ValueError('Workspace must be a directory')
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Workspace must not pass through a link or junction')
    return resolved


ROOT = workspace_path()
DEFAULTS = {
    'schema_version': '1.0.0',
    'paths': {'data_dir': 'runs'},
    'model': {'provider': '', 'base_url': '', 'name': '', 'api_key_env': 'MODELCREW_LLM_API_KEY',
              'm1_model': '', 'w2_model': '', 'w2_response_format': 'json_object'},
    'database': {'url_env': 'MODELCREW_DATABASE_URL'},
    'retrieval': {'paper_config': '', 'algorithm_config': '', 'qdrant_url': 'http://127.0.0.1:56333',
                  'model_path': ''},
    'execution': {'root': '', 'image': 'modelcrew-reference:py313'},
    'export': {'pandoc': '', 'tectonic': '', 'tex_cache': '', 'cjk_font': ''},
}
SCHEMA = {'type':'object', 'additionalProperties':False, 'required':['schema_version'],
          'properties':{'schema_version':{'const':'1.0.0'}}}
for _section, _values in DEFAULTS.items():
    if isinstance(_values, dict):
        SCHEMA['properties'][_section] = {'type':'object','additionalProperties':False,
            'properties':{key:{'type':'string'} for key in _values}}
SCHEMA['properties']['model']['properties']['w2_response_format'] = {'enum':['json_object','json_schema']}
for _section, _key in [('model','api_key_env'),('database','url_env')]:
    SCHEMA['properties'][_section]['properties'][_key] = {'type':'string','pattern':'^[A-Z][A-Z0-9_]*$'}
SCHEMA['properties']['paths']['properties']['data_dir']['minLength'] = 1
SCHEMA['properties']['execution']['properties']['image']['minLength'] = 1
for _section, _key in [('model','base_url'),('retrieval','qdrant_url')]:
    SCHEMA['properties'][_section]['properties'][_key]['pattern'] = r'^$|^https?://[^\s]+$'
ENV_SETTINGS = {
    'MODELCREW_DATA_DIR': ('paths','data_dir'),
    'MODELCREW_LLM_PROVIDER': ('model','provider'), 'MODELCREW_LLM_BASE_URL': ('model','base_url'),
    'MODELCREW_LLM_MODEL': ('model','name'), 'MODELCREW_M1_MODEL': ('model','m1_model'),
    'MODELCREW_W2_MODEL': ('model','w2_model'), 'MODELCREW_W2_RESPONSE_FORMAT': ('model','w2_response_format'),
    'MODELCREW_RETRIEVAL_CONFIG': ('retrieval','paper_config'),
    'MODELCREW_ALGORITHM_CONFIG': ('retrieval','algorithm_config'),
    'MODELCREW_QDRANT_URL': ('retrieval','qdrant_url'), 'MODELCREW_EMBEDDING_MODEL': ('retrieval','model_path'),
    'MODELCREW_EXECUTION_ROOT': ('execution','root'), 'MODELCREW_EXECUTION_IMAGE': ('execution','image'),
    'MODELCREW_PANDOC': ('export','pandoc'), 'MODELCREW_TECTONIC': ('export','tectonic'),
    'TECTONIC_CACHE_DIR': ('export','tex_cache'), 'MODELCREW_CJK_FONT': ('export','cjk_font'),
}


def settings_path(root=None):
    root = Path(root) if root is not None else ROOT
    explicit = os.environ.get('MODELCREW_CONFIG')
    if explicit is not None:
        if not explicit.strip():
            raise ValueError('MODELCREW_CONFIG must not be empty')
        path = Path(explicit).expanduser()
        path = path if path.is_absolute() else root/path
        if not path.is_file():
            raise RuntimeError('Explicit user configuration file is missing')
        return path
    return root/'configs/local/settings.json'


def load_settings(root=None):
    path = settings_path(root)
    result = copy.deepcopy(DEFAULTS)
    if path.exists():
        try:
            def unique(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj: raise ValueError('Duplicate configuration field')
                    obj[key] = value
                return obj
            raw = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique)
            if list(Draft202012Validator(SCHEMA).iter_errors(raw)):
                raise ValueError('Configuration does not match schema 1.0.0')
        except (ValueError, OSError):
            raise ValueError('Invalid user configuration; check schema version and field names') from None
        for section, values in raw.items():
            if isinstance(values, dict): result[section].update(values)
    return result


def configured(name, default=None, *, root=None):
    if name in os.environ:
        value = os.environ[name]
        if not value.strip(): raise ValueError('Explicit environment setting is empty: '+name)
        if name in ENV_SETTINGS:
            section, key = ENV_SETTINGS[name]
            if list(Draft202012Validator(SCHEMA['properties'][section]['properties'][key]).iter_errors(value)):
                raise ValueError('Invalid environment setting: '+name)
        return value
    if name in ENV_SETTINGS:
        section, key = ENV_SETTINGS[name]
        value = load_settings(root)[section][key]
        return value if value else default
    return default


def env_file_values(path):
    values = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=',1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def model_environment(root=None):
    root = Path(root) if root is not None else ROOT
    # Read-only legacy compatibility; init never copies or modifies old credentials.
    values = env_file_values(root/'.env')
    values.update(env_file_values(root/'configs/local/secrets.env'))
    for name in ENV_SETTINGS:
        value = configured(name, root=root)
        if value is not None: values[name] = value
    values.update(os.environ)
    key_name = load_settings(root)['model']['api_key_env']
    values['MODELCREW_LLM_API_KEY'] = values.get(key_name, '')
    return values


def database_env_file(root=None):
    root = Path(root) if root is not None else ROOT
    explicit = os.environ.get('MODELCREW_DATABASE_CONFIG')
    if explicit is not None:
        if not explicit.strip(): raise ValueError('MODELCREW_DATABASE_CONFIG must not be empty')
        path = Path(explicit).expanduser()
        path = path if path.is_absolute() else root/path
        if not path.is_file(): raise RuntimeError('Configured database environment file is missing')
        return path
    current, legacy = root/'configs/local/database.env', root/'stage-b/.env'
    if current.exists() and legacy.exists():
        raise RuntimeError('Conflicting current and historical database configuration files')
    return legacy if legacy.exists() else current


def database_url(root=None):
    root = Path(root) if root is not None else ROOT
    name = load_settings(root)['database']['url_env']
    if name in os.environ:
        if not os.environ[name].strip(): raise RuntimeError('Configured database URL is empty')
        return os.environ[name]
    values = env_file_values(root/'configs/local/secrets.env')
    if values.get(name): return values[name]
    values = env_file_values(database_env_file(root))
    if values.get(name): return values[name]
    raise RuntimeError('Database URL missing; set the configured URL environment variable or local secrets file')
