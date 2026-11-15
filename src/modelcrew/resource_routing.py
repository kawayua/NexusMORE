"""Program-owned, version-bound resource routing and read-only document execution.

No model-supplied commands, external skills, implicit approvals or unknown retries.
Old business runs without a routing snapshot retain their original inputs.
"""
from contextlib import contextmanager
import hashlib
from importlib.resources import as_file, files
import importlib.util
from importlib.metadata import distribution, PackageNotFoundError
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from .package_resources import resource, verify_resources

REGISTRY = 'capabilities/routing.json'
SNAPSHOT = 'resource-routing.json'


class RoutingError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def implementation_identity():
    return digest({name:hashlib.sha256(files('modelcrew').joinpath(name).read_bytes()).hexdigest()
        for name in ['resource_routing.py','document_tools.py','algorithm_knowledge.py','mathematical_knowledge.py']})


def registry():
    try:
        verify_resources()
    except FileNotFoundError as error:
        raise RoutingError('resource_missing','Installed routing resource is missing') from error
    except ValueError as error:
        raise RoutingError('resource_changed','Installed routing resource hash changed') from error
    value = json.loads(resource(REGISTRY).read_text(encoding='utf-8'))
    if value.get('routing_version') != '1.0.0' or value.get('backend') != 'python':
        raise RoutingError('resource_changed', 'Unsupported routing registry')
    return value


@contextmanager
def lock(folder):
    path = Path(folder)/'.routing.lock'
    if path.is_symlink() or path.is_junction():
        raise RoutingError('unsafe_path', 'Routing lock cannot be a link')
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RoutingError('busy', 'Routing request is active; query status later') from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def inside(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise RoutingError('unsafe_path', 'Expected an input-root-relative file name')
    pieces = relative.split('/')
    if any(p in {'', '.', '..'} for p in pieces) or Path(relative).is_absolute():
        raise RoutingError('unsafe_path', 'Input path escapes its declared root')
    path = Path(root)/relative
    if not path.resolve().is_relative_to(Path(root).resolve()) or path.is_symlink() or path.is_junction():
        raise RoutingError('unsafe_path', 'Input/receipt path cannot escape or be a link')
    return path


def normalize(request, input_root, config):
    required = {'task_id', 'question_id', 'version', 'role', 'stage', 'request_id', 'contract_sha256', 'query'}
    optional = {'inputs', 'algorithm_ids', 'math_ids', 'category'}
    if not isinstance(request, dict) or set(request)-required-optional or required-set(request):
        raise RoutingError('invalid_request', 'Routing requires exact task/question/version/role/stage/request/contract/query binding')
    value = json.loads(json.dumps(request, allow_nan=False))
    for name in ['task_id', 'question_id', 'request_id']:
        if not isinstance(value[name], str) or not value[name].strip() or len(value[name])>200 or re.search(r'[\x00-\x1f]',value[name]):
            raise RoutingError('invalid_request', 'Invalid routing identity: '+name)
    if type(value['version']) is not int or value['version'] < 1:
        raise RoutingError('invalid_request', 'Positive contract version required')
    if not isinstance(value['contract_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['contract_sha256']):
        raise RoutingError('invalid_request', 'Contract SHA256 required')
    if value['role'] not in config['roles'] or value['stage'] not in config['roles'][value['role']]:
        raise RoutingError('permission_denied', 'Role/stage is not a registered routing scope')
    if not isinstance(value['query'], str) or not value['query'].strip() or len(value['query']) > 20000:
        raise RoutingError('invalid_request', 'Bounded routing query required')
    for key in ['algorithm_ids', 'math_ids']:
        selected = value.setdefault(key, [])
        if not isinstance(selected, list) or len(selected) > config['limits']['max_sections'] or len(set(selected)) != len(selected) or any(not isinstance(x,str) for x in selected):
            raise RoutingError('invalid_request', 'Invalid bounded section selection')
    names = value.get('inputs', [])
    if not isinstance(names, list) or len(names) > config['limits']['max_inputs'] or any(not isinstance(n,str) for n in names) or len(names) != len(set(names)):
        raise RoutingError('invalid_request', 'Duplicate or excessive input files')
    if value['role'] == 'quality' and names:
        raise RoutingError('permission_denied', 'Independent reviews only receive their existing approved evidence snapshots; no tool execution')
    attachments = []
    for name in names:
        path = inside(input_root, name)
        if not path.is_file():
            raise RoutingError('missing_input', 'Routing input is missing')
        if path.stat().st_size > config['limits']['max_input_bytes']:
            raise RoutingError('input_limit', 'Input exceeds routing byte bound')
        attachments.append({'path':name, 'sha256':sha(path), 'bytes':path.stat().st_size, 'suffix':path.suffix.lower()})
    value['inputs'] = attachments
    value['input_root'] = str(Path(input_root).resolve())
    return value


def select(value, config):
    from .algorithm_knowledge import load_catalog, read_algorithm
    from .mathematical_knowledge import load_catalog as math_catalog, read_topic
    manifest_raw = resource('resource-manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    entries = {r['path']:r for r in manifest['files']}
    documents = []
    def add(path, reason, *, text=None, scope='whole_file'):
        if any(d['path']==path and d['scope']==scope for d in documents):
            return
        if path not in entries:
            raise RoutingError('resource_missing', 'Resource is not registered: '+path)
        raw = resource(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entries[path]['sha256']:
            raise RoutingError('resource_changed', 'Selected resource changed')
        content = raw.decode('utf-8') if text is None else text
        documents.append({'path':path,'source_sha256':entries[path]['sha256'],'scope':scope,
            'text_sha256':hashlib.sha256(content.encode('utf-8')).hexdigest(),'text':content,'reason':reason})
    # Always perform this read before selecting category/algorithm sections.
    add('algorithms/index.md', 'Read algorithm index before matching sections')
    catalog = load_catalog()
    cards = {c['id']:c for c in catalog['algorithms']}
    query = value['query'].casefold()
    ids = list(value['algorithm_ids'])
    if any(key not in cards for key in ids):
        raise RoutingError('no_matching_method', 'Suggested algorithm is not in the installed canonical catalog')
    if not ids:
        hits = [c for c in cards.values() if c['name'].casefold() in query or re.search(r'(?<![a-z0-9-])'+re.escape(c['id'])+r'(?![a-z0-9-])', query)]
        hits.sort(key=lambda c:(-len(c['name']),c['id']))
        ids = [c['id'] for c in hits[:config['limits']['max_sections']]]
    category = value.get('category')
    categories = {c['id']:c for c in catalog['categories']}
    if category is not None and category not in categories and category != 'geometry':
        raise RoutingError('no_matching_method', 'Unknown problem category; no fallback method selected')
    if category is None:
        category = next((key for key,terms in config['category_terms'].items() if any(t.casefold() in query for t in terms)), None)
    if category is None and ids:
        category = cards[ids[0]]['categories'][0]
    if category == 'geometry':
        add('algorithms/numerical-geometry.md', 'Existing geometry supplement, outside seven-category canonical coverage')
    elif category and not ids:
        path = categories[category]['path']
        text = resource(path).read_text(encoding='utf-8').split('<a id="',1)[0]
        add(path, 'Category introduction only; algorithm premises still unknown', text=text, scope='before_first_algorithm')
    for key in ids:
        match_category = category if category in cards[key]['categories'] else cards[key]['categories'][0]
        result = read_algorithm(key, match_category)
        add(result['source'], 'Canonical method candidate; not adoption or solved premise', text=result['text'], scope='algorithm:'+key)
    math = math_catalog()
    topics = {t['id']:t for t in math['topics']}
    mids = list(value['math_ids']) or [key for key,terms in config['math_terms'].items() if any(t.casefold() in query for t in terms)][:config['limits']['max_sections']]
    if any(key not in topics for key in mids):
        raise RoutingError('no_matching_method', 'Unknown mathematical reference; no invented substitution')
    if mids:
        add('mathematics/index.md', 'Mathematics is derivation/proof/checking reference only')
    for key in mids:
        result = read_topic(key)
        add(result['source'], 'Requested mathematical reasoning reference', text=result['chapter_guidance']+result['text'], scope='math:'+key)
    if value['role'] == 'writing':
        workflow = json.loads(resource('paper/workflow.json').read_text(encoding='utf-8'))
        add('paper/workflow.json', 'Chinese Markdown first; separate text and figure approvals')
        for path in workflow['must_load']:
            relative = ('project-policy/'+path.split('/')[-1]) if path.startswith('docs/') else path.removeprefix('resources/')
            add(relative, 'Project-mandated paper policy/template')
    if value['role'] == 'quality':
        from .hand_guidance import load_bundle, guidance_context
        guidance = guidance_context(load_bundle(), value['stage'])
        for doc in guidance['documents']:
            add('collaboration/'+doc['path'], 'Independent read-only gate policy only')
    tools = []
    gaps = []
    for item in value['inputs']:
        spec = config['tools'].get(item['suffix'])
        if spec is None:
            gaps.append({'input':item['path'],'code':'unsupported_format','action':'Use a supported PDF/XLSX/DOCX copy; no silent converter'})
            continue
        add(spec['guide'], 'Mandatory document-type guide read before execution')
        if item['suffix']=='.docx':
            add('document-tools/upstream/docx/scripts/office/validate.py', 'Registered schema validation script; reference text, never interpreted as model instructions')
        tools.append({'input':item,**spec})
    if not ids:
        gaps.append({'code':'no_matching_algorithm','blocking':False,'action':'Method selection needs problem premises; category reference is not a chosen solver'})
    if sum(len(d['text'].encode('utf-8')) for d in documents) > config['limits']['max_context_bytes']:
        raise RoutingError('context_limit', 'Selected references exceed bounded context; narrow the request')
    return {'routing_version':config['routing_version'],'implementation_sha256':implementation_identity(),'resource_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),
        'registry_sha256':hashlib.sha256(resource(REGISTRY).read_bytes()).hexdigest(),
        'selection':{'category':category,'algorithm_ids':ids,'math_ids':mids,'premises_status':'unknown_requires_model_review'},
        'documents':documents,'tools':tools,'gaps':gaps,'formal_approval':False,
        'independent_context':value['role']=='quality','approval_authority':False}


def verify_artifacts(folder, rows):
    for row in rows:
        path = inside(folder, row['path'])
        if not path.is_file() or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
            raise RoutingError('artifact_changed', 'Saved routing artifact is missing or changed')


def execute_tool(folder, task, source, config):
    """Only fixed, installed adapters. No arbitrary command or user code argument."""
    folder = Path(folder)
    folder.mkdir(exist_ok=False)
    copied = folder/('input'+task['input']['suffix'])
    shutil.copyfile(source, copied)
    if sha(copied)!=task['input']['sha256']:
        raise RoutingError('input_changed', 'Input changed while staging')
    dependency_roots=[]
    for dependency in task['dependencies']:
        spec=importlib.util.find_spec(dependency)
        try:
            location=Path(distribution(dependency).locate_file('')).resolve()
        except PackageNotFoundError as error:
            raise RoutingError('missing_dependencies','Declared dependency has no installed distribution metadata') from error
        if spec is None or spec.origin is None or not Path(spec.origin).resolve().is_relative_to(location):
            raise RoutingError('missing_dependencies','Dependency import is not bound to its installed distribution')
        if str(location) not in dependency_roots:
            dependency_roots.append(str(location))
    # Extraction stays alive until the child exits (also supports packaged dirs).
    with as_file(files('modelcrew')) as package:
        bootstrap = 'import sys,json;sys.path.insert(0,sys.argv.pop(1));sys.path.extend(json.loads(sys.argv.pop(1)));from modelcrew.resource_routing import worker;worker()'
        command = [sys.executable,'-I','-X','utf8','-c',bootstrap,str(Path(package).parent),json.dumps(dependency_roots),
                   task['adapter'],str(copied),str(folder/'tool-output'),str(folder/'worker-result.json')]
        try:
            proc = subprocess.run(command,cwd=folder,capture_output=True,timeout=config['limits']['timeout_seconds'],shell=False)
            (folder/'stdout.txt').write_bytes(proc.stdout)
            (folder/'stderr.txt').write_bytes(proc.stderr)
            code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            (folder/'stdout.txt').write_bytes(exc.stdout or b'')
            (folder/'stderr.txt').write_bytes(exc.stderr or b'')
            code = None
    if sha(source)!=task['input']['sha256'] or sha(copied)!=task['input']['sha256']:
        raise RoutingError('input_changed', 'Original or staged attachment changed')
    result_path = folder/'worker-result.json'
    result = read(result_path) if result_path.is_file() else {'status':'failed','code':'tool_timeout' if code is None else 'tool_failure'}
    if code != 0:
        result['status']='failed'
    artifacts=[];total=0
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(folder.resolve()):
            raise RoutingError('unsafe_path', 'Tool artifact escaped its private directory')
        if path.is_file():
            total+=path.stat().st_size
            if total>config['limits']['max_artifact_bytes']:
                raise RoutingError('output_limit', 'Tool artifacts exceed bounded output')
            artifacts.append({'path':path.relative_to(folder).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size})
    return {'status':result.get('status','failed'),'returncode':code,'tool':task['id'],'input':task['input'],
        'result':result,'artifacts':artifacts,'executor':{'kind':'installed_python_subprocess','python':sys.executable,
        'dependency_roots':dependency_roots,'mapped_input':str(copied),'mapped_output':str(folder/'tool-output')},'formal_approval':False}


def worker():
    from .document_tools import run, TOOLS
    tool, source, output, result_path = sys.argv[1:]
    if tool not in {'pdf_read','xlsx_read','docx_validate'} or tool not in TOOLS:
        raise RoutingError('permission_denied','Unregistered routing worker adapter')
    try:
        result = run(tool, source, output, timeout=60)
    except Exception as error:
        result = {'status':'failed','code':'tool_failure','error_type':type(error).__name__}
    atomic(result_path,result)
    raise SystemExit(0 if result.get('status')=='passed' else 1)


def route(root, request, input_root, *, execute=True):
    """Trusted orchestrator entry. Identity labels do not grant business approval."""
    config = registry()
    value = normalize(request, input_root, config)
    key = digest({k:value[k] for k in ['task_id','question_id','version','role','request_id']})
    root = Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    folder = inside(root,key);folder.mkdir(exist_ok=True)
    with lock(folder):
        saved = folder/'route.json'
        if saved.exists():
            state = read(saved)
            if digest({'request':state['request'],'plan':state['plan']})!=state['snapshot_sha256']:
                raise RoutingError('resource_changed','Saved routing plan was changed')
            if state['request_sha256']!=digest(value):
                raise RoutingError('request_conflict','Idempotency key reused with changed task input or plan')
            if state['plan'].get('implementation_sha256')!=implementation_identity():
                raise RoutingError('resource_changed','Registered adapter implementation changed; preserve this record and start a new request')
            if state['plan']['resource_manifest_sha256']!=hashlib.sha256(resource('resource-manifest.json').read_bytes()).hexdigest():
                raise RoutingError('resource_changed','Installed resources differ; keep old evidence and start a new request')
            for number,op in enumerate(state['operations']):
                verify_artifacts(folder/f'tool-{number}',op['artifacts'])
            if state['status']=='claimed':
                if len(state['operations'])==len(state['plan']['tools']) and all(op['status']=='passed' for op in state['operations']):
                    state.update(status='completed',recovered_from_saved_receipts=True)
                    atomic(saved,state)
                    return state
                # Query durable worker results without executing or inventing a
                # missing parent exit status/log. Ambiguity is not success.
                observed=[]
                for number,_ in enumerate(state['plan']['tools']):
                    result=folder/f'tool-{number}'/'worker-result.json'
                    if result.is_file():
                        observed.append({'tool_index':number,'saved_result':read(result),'sha256':sha(result)})
                return {**state,'status':'outcome_unknown','saved_worker_results':observed,
                    'recovery':'Parent receipt incomplete; saved worker results queried only. Never redispatch this request.'}

            if state['status']!='planned' or not execute:
                return state
        else:
            plan = select(value,config)
            state = {'schema_version':'1.0.0','request':value,'request_sha256':digest(value),'plan':plan,
                'status':'planned','operations':[],'route_path':str(saved),'formal_approval':False}
            state['snapshot_sha256']=digest({'request':value,'plan':plan})
            atomic(saved,state)
        if not execute:
            return state
        unsupported=[g for g in state['plan']['gaps'] if g['code']=='unsupported_format']
        missing=sorted({dep for task in state['plan']['tools'] for dep in task['dependencies'] if importlib.util.find_spec(dep) is None})
        if unsupported or missing:
            state.update(status='blocked',code='unsupported_format' if unsupported else 'missing_dependencies',missing_dependencies=missing,
                recovery='Prepare supported input or install the declared documents dependency group outside this run; use a new request. No runtime download or fallback performed.')
            atomic(saved,state);return state
        state['status']='claimed';atomic(saved,state)
        try:
            for number,task in enumerate(state['plan']['tools']):
                op=execute_tool(folder/f'tool-{number}',task,inside(input_root,task['input']['path']),config)
                state['operations'].append(op);atomic(saved,state)
                if op['status']!='passed':
                    state.update(status='failed',code='tool_failure',recovery='Read logs and preserve this failed request; repair inputs/environment before a new request')
                    atomic(saved,state);return state
        except Exception as error:
            state.update(status='failed',code=getattr(error,'code','tool_failure'),error_type=type(error).__name__)
            atomic(saved,state);raise
        state['status']='completed';atomic(saved,state)
        return state


def freeze(folder, state):
    if state['status']!='completed':
        raise RoutingError(state.get('code','routing_incomplete'),'Routing did not complete; no business model call permitted')
    value={'schema_version':'1.0.0','request':state['request'],'plan':state['plan'],'operations':state['operations'],
        'snapshot_sha256':state['snapshot_sha256'],'route_path':state['route_path'],'formal_approval':False}
    path=Path(folder)/SNAPSHOT
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
    return sha(path)


def frozen_context(folder, expected_sha256):
    path=Path(folder)/SNAPSHOT
    if sha(path)!=expected_sha256:
        raise RoutingError('resource_changed','Frozen routing context changed')
    state=read(path)
    if digest({'request':state['request'],'plan':state['plan']})!=state['snapshot_sha256']:
        raise RoutingError('resource_changed','Routing snapshot binding changed')
    for doc in state['plan']['documents']:
        if hashlib.sha256(doc['text'].encode('utf-8')).hexdigest()!=doc['text_sha256']:
            raise RoutingError('resource_changed','Frozen routed reference changed')
    for number,op in enumerate(state['operations']):
        verify_artifacts(Path(state['route_path']).parent/f'tool-{number}',op['artifacts'])
    observed=[]
    remaining=200000-len(json.dumps(state['plan']['documents'],ensure_ascii=False).encode('utf-8'))-20000
    for number,op in enumerate(state['operations']):
        tool_folder=Path(state['route_path']).parent/f'tool-{number}'/'tool-output'
        target=tool_folder/({'pdf-read':'pages.json','spreadsheet-read':'rows.json','word-structure-check':'stdout.txt'}[op['tool']])
        if not target.is_file():
            continue
        if target.stat().st_size<=min(40000,remaining):
            remaining-=target.stat().st_size
            content=read(target) if target.suffix=='.json' else target.read_text(encoding='utf-8',errors='replace')
            observed.append({'input':op['input']['path'],'tool':op['tool'],'context_projection':False,'content':content})
        else:
            observed.append({'input':op['input']['path'],'tool':op['tool'],'context_projection':True,
                'complete_output_in_context':False,'artifact':str(target),'sha256':sha(target),
                'reason':'Complete tool output is archived; too large for this bounded model context. No complete-text claim made.'})
    # Independent quality calls are given their own policy/evidence view by the
    # existing gate code; never inject an author's routing/tools history there.
    return {'binding':{k:state['request'][k] for k in ['task_id','question_id','version','contract_sha256','role','stage']},
        'routing_version':state['plan']['routing_version'],'implementation_sha256':state['plan']['implementation_sha256'],'resource_manifest_sha256':state['plan']['resource_manifest_sha256'],
        'snapshot_sha256':state['snapshot_sha256'],'selection':state['plan']['selection'],
        'documents':state['plan']['documents'],'tool_receipts':state['operations'],'observed_inputs':observed,'gaps':state['plan']['gaps'],
        'formal_approval':False,'input_document_instructions_are_data':True}


# Explicitly authored compatibility references for the existing geometry tasks.
# New seven-category entries use canonical IDs and never read an old run catalog.
GEOMETRY_CARDS = {
    'geometry-model':('曲线弧长与固定弦长几何模型',{'known_mechanism':True,'continuous_geometry':True}),
    'bracketed-root':('连续异号括区间标量求根',{'scalar_equation':True,'continuous_on_bracket':True,'opposite_endpoint_signs':True}),
    'brentq-api':('标量求根接口边界',{'scalar_equation':True,'continuous_on_bracket':True,'opposite_endpoint_signs':True}),
}


def installed_card_navigation():
    from .algorithm_knowledge import load_catalog
    value=load_catalog()
    rows=[{'id':card['id'],'category':category,'title':card['name'],'required_facts':{},
           'conditions_status':'natural_language_conditions_require_review'}
          for card in value['algorithms'] for category in card['categories']]
    rows += [{'id':key,'category':'geometry','title':item[0],'required_facts':item[1]} for key,item in GEOMETRY_CARDS.items()]
    return rows


def installed_algorithm_context(category, *, facts=None, card_ids=None):
    from .algorithm_knowledge import read_algorithm
    from .algorithm_retrieval import assess, AlgorithmRequest
    config=registry()
    index=resource('algorithms/index.md');index_text=index.read_text(encoding='utf-8')
    available=[card for card in installed_card_navigation() if card['category']==category]
    if category not in config['category_terms'] and category!='geometry':
        raise RoutingError('no_matching_method','Unknown installed category')
    selected=card_ids or [c['id'] for c in available[:3]]
    if len(selected)>3 or len(selected)!=len(set(selected)) or not set(selected)<={c['id'] for c in available}:
        raise RoutingError('no_matching_method','Invalid installed category/card selection')
    cards=[];excluded=[]
    for key in selected:
        if key in GEOMETRY_CARDS:
            path='algorithms/numerical-geometry.md';raw=resource(path).read_bytes();text=raw.decode('utf-8')
            title,premises=GEOMETRY_CARDS[key]
            card={'id':key,'title':title,'category':'geometry','required_facts':premises,
                  'max_variables':1 if key!='geometry-model' else None,'dependencies':[]}
            applicability=assess(card,AlgorithmRequest(query='installed geometry reference',facts=facts or {}))
            profile={'scope':'Project-authored geometry supplement; root continuity/sign facts do not prove uniqueness or correct branch'}
        else:
            result=read_algorithm(key,category);path=result['source'];raw=resource(path).read_bytes();text=result['text']
            original=result['algorithm']
            card={'id':key,'title':original['name'],'category':category,'required_facts':{},
                  'conditions':original['conditions'],'failure_boundary':original['failure_boundary'],
                  'example_scope':original['example']['scope'],'max_variables':None,'dependencies':[]}
            applicability={'status':'needs_review','reasons':[],
                'unknown_facts':original['conditions'],'premise_source':'Natural-language conditions need task-specific evidence; no boolean truth inferred'}
            profile={'scope':'Canonical mathematical reference, not a registered general solver',
                     'failure_boundary':original['failure_boundary'],'counterexample':original['counterexample']}
        if applicability['status']=='excluded':
            excluded.append({'card_id':key,**applicability});continue
        source={'id':key,'path':'resources/'+path,'sha256':hashlib.sha256(raw).hexdigest(),
                'section_sha256':digest(text),'text':text,'version':'NexusMORE installed knowledge 1.0.0',
                'verification':'reference_and_fixed_educational_checks_not_business_approval'}
        cards.append({'card':card,'card_sha256':digest(card),'profile':profile,'profile_sha256':digest(profile),
            'applicability':applicability,'source_sections':[source],'origin':'builtin_project_reference',
            'citation_id':'algorithm:'+key+':'+digest(card)[:12],'adoption':'pending_modeling_hand_decision'})
    return {'status':'ok' if cards else 'no_applicable_cards','selection_mode':'installed_index_first_bounded_category_card_selection',
        'category':category,'index':{'path':'resources/algorithms/index.md','sha256':sha(index),'text':index_text,'read_first':True},
        'catalog_sha256':sha(resource('algorithms/knowledge/catalog.json')),'catalog_mode':'installed_canonical_and_local_geometry',
        'legacy_runtime_catalog_used':False,'cards':cards,'excluded':excluded,'formal_approval':False,
        'interpretation':'References only. Premises, adaptation, implementation and independent review remain task-specific.'}


def prepare_runtime_context(folder, contract, *, task_id, version, role, stage, request_id, query, category=None):
    """Pre-read trusted registered attachments and freeze a new business context.

    The existing Workflow validates authorizations. This helper only prepares
    references and read-only input evidence; it never approves or runs a solver.
    """
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    input_root=folder/'routing-inputs';input_root.mkdir(exist_ok=True)
    names=[]
    for number,item in enumerate(contract.get('inputs',[])):
        source=Path(item['path'])
        if source.suffix.lower() not in {'.pdf','.xlsx','.docx'}:
            continue  # Existing inspect_file owns JSON/CSV/text/NPY profiles.
        if source.is_symlink() or source.is_junction() or not source.is_file() or sha(source)!=item['sha256']:
            raise RoutingError('input_changed','Approved original input changed before routing')
        name=f'input-{number}'+source.suffix.lower();target=input_root/name
        if target.exists():
            if sha(target)!=item['sha256']:
                raise RoutingError('input_changed','Existing staged routing input changed')
        else:
            shutil.copyfile(source,target)
        names.append(name)
    request={'task_id':task_id,'question_id':contract['problem']['subproblem_id'],
        'version':version,'role':role,'stage':stage,'request_id':request_id,'contract_sha256':digest(contract),
        'query':json.dumps({'problem':contract['problem'],'method':contract.get('method',{}),'request':query},ensure_ascii=False),
        'inputs':names}
    if category is not None:
        request['category']=category
    state=route(folder/'routing-records',request,input_root)
    expected=freeze(folder,state)
    return expected, frozen_context(folder,expected)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--input-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plan-only',action='store_true')
    args=parser.parse_args()
    try:
        result=route(args.output,read(args.request),args.input_root,execute=not args.plan_only)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['status'] in {'planned','completed'} else 1
    except (RoutingError,FileNotFoundError,ValueError) as error:
        print(json.dumps({'status':'blocked','code':getattr(error,'code','resource_missing'),'error':str(error)},ensure_ascii=False))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
