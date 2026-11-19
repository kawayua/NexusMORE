"""Live PostgreSQL/standard MCP tests with synthetic inputs; never LLM approvals."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
import pytest

from modelcrew.business_adapter import BusinessAdapter, IMPLEMENTED, clean
from modelcrew.business_artifacts import ArtifactRegistry, read_verified, register_input
from modelcrew.business_contract import BusinessContractError, validate_response
from modelcrew.config import ROOT
from modelcrew.workflow import Workflow
from modelcrew.workflow_mcp import definitions, input_schema


@pytest.fixture(scope='module')
def url():
    value=os.environ.get('MODELCREW_BUSINESS_TEST_URL')
    if not value:pytest.skip('Run the explicit isolated PostgreSQL business-MCP probe')
    with Workflow(value) as w:w.setup()
    return value


@pytest.fixture
def adapter(url):
    return BusinessAdapter(lambda:Workflow(url))


def request(op,args,*,key=None,bound=None):
    value={'contract_version':'1.0.0','operation':op,'arguments':args}
    if key is not None:value['request_id']=key
    if bound is not None:value['expected_binding']=bound
    return value


def project(adapter):
    key='g2-'+uuid.uuid4().hex
    command=request('project_create',{'body':{'id':key,'title':'Synthetic G2 project'}},key='create-project')
    response=adapter.invoke('project_create',command)
    assert response['status']=='ok',response
    return key,command


def contract(artifact):
    return {'schema_version':'1.0.0','problem':{'case_id':'SYNTHETIC_G2','subproblem_id':'Q1','title':'G2 engineering fixture','scope':'Scalar identity only; no solve requested','objective':{'kind':'analysis','description':'Check x=a'}},
        'sources':[{'id':'statement','kind':'problem_statement','locator':'Synthetic local input','sha256':artifact['sha256']}],
        'inputs':[{'id':'input','source_id':'statement','path':'artifact:'+artifact['artifact_id'],'sha256':artifact['sha256'],'role':'dataset'}],
        'conventions':{'length_unit':'m','time_unit':'s','coordinate_system':'scalar','time_origin':'zero','direction':'positive','indexing':'zero'},
        'parameters':[{'id':'a','value':1,'unit':'1','source_id':'statement','origin':'given','derivation':None}],
        'variables':[{'id':'x','meaning':'scalar result','unit':'1','domain':'real'}],
        'assumptions':[{'id':'exact','statement':'Synthetic exact scalar','source_id':'statement'}],
        'constraints':[{'id':'identity','expression':'x=a','meaning':'identity','check_id':'check'}],
        'method':{'steps':['Return a after explicit approval and independent gates'],'root_selection':'unique scalar','allowed_equivalent_changes':['numeric representation'],'requires_new_confirmation':['change equation']},
        'outputs':[{'id':'result','path':'result.json','format':'json','fields':[{'name':'x','shape':[1],'unit':'1'}],'decimal_places':6}],
        'checks':[{'id':'check','description':'identity check','method':'independent subtraction','tolerance':0,'unit':'1','evidence_required':'numeric report','initial_status':'unknown'}],
        'risks':['Engineering fixture; no mathematical review performed'],'alternatives':['independent direct computation']}


def task(adapter,url,tmp_path):
    p,_=project(adapter);t='task-'+uuid.uuid4().hex;source=tmp_path/'input.json';source.write_text('{"a":1}',encoding='utf-8')
    with Workflow(url) as w:
        artifact=register_input(w,ROOT,{'project_id':p,'task_id':t,'version':1},source)
    command=request('task_create',{'project_id':p,'body':{'id':t,'contract':contract(artifact),'executor_key':'pending-code'}},key='create-task')
    response=adapter.invoke('task_create',command)
    assert response['status']=='needs_user_input',response
    return p,t,artifact,command,response


def test_discovery_has_only_implemented_model_tools():
    from jsonschema import Draft202012Validator
    tools=definitions();assert len(tools)==40
    assert {t.name for t in tools}==IMPLEMENTED
    for name in ['task_decide','hand_decide','assembly_decide','final_decide','hand_repair','figures_select','question_import']:
        assert name not in IMPLEMENTED
    for tool in tools:
        Draft202012Validator.check_schema(tool.inputSchema)
        Draft202012Validator.check_schema(tool.outputSchema)
    assert len(json.dumps(input_schema('hand_advance')))<5000


def test_capabilities_need_no_database():
    a=BusinessAdapter(lambda:pytest.fail('Database must not open'))
    response=a.invoke('capabilities_read',request('capabilities_read',{}))
    assert response['status']=='ok' and len(response['data']['operations'])==40


def test_project_replay_conflict_and_durable_ledger(adapter,url):
    p,command=project(adapter)
    replay=adapter.invoke('project_create',command)
    assert replay['replayed'] is True
    assert replay['receipt']['state']=='succeeded'
    changed=copy.deepcopy(command);changed['arguments']['body']['title']='Other'
    assert adapter.invoke('project_create',changed)['error']['code']=='idempotency_conflict'
    with Workflow(url) as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_business_operations WHERE resource_key=%s',('project:'+p,)).fetchone()['n']==1
        with pytest.raises(Exception):
            w.db.execute('DELETE FROM mc_business_operation_events WHERE request_id=%s',('create-project',))


def test_task_creation_pending_and_inputs_are_owner_scoped(adapter,url,tmp_path):
    p,t,a,command,state=task(adapter,url,tmp_path)
    assert state['binding']['task_id']==t and state['pending'][0]['kind']=='model'
    assert state['data']['task']['model_approved'] is False
    replay=BusinessAdapter(lambda:Workflow(url)).invoke('task_create',command)
    assert replay['replayed'] and replay['binding']==state['binding']
    query=request('pending_list',{'project_id':p,'task_id':t})
    assert adapter.invoke('pending_list',query)['pending']==state['pending']
    listing=adapter.invoke('artifacts_list',request('artifacts_list',{'task_id':t,'version':1}))
    assert a['artifact_id'] in {x['artifact_id'] for x in listing['artifacts']}
    read={'owner':a['owner'],'artifact_id':a['artifact_id'],'sha256':a['sha256'],'offset':0,'max_bytes':4}
    response=adapter.invoke('artifact_read',request('artifact_read',read))
    assert response['chunk']['bytes_returned']==4 and response['chunk']['eof'] is False
    p2,_=project(adapter);read['owner']={**a['owner'],'project_id':p2}
    assert adapter.invoke('artifact_read',request('artifact_read',read))['error']['code']=='artifact_access_denied'


def test_changed_registered_bytes_and_bad_offsets_fail(adapter,url,tmp_path):
    p,t,a,_,_=task(adapter,url,tmp_path)
    with Workflow(url) as w:
        row=w.db.execute('SELECT path FROM mc_business_artifacts WHERE artifact_id=%s',(a['artifact_id'],)).fetchone()
        # Use a separate explicitly registered output so immutable shared input
        # snapshots cannot be corrupted by this negative test.
        output=tmp_path/'registered.txt';output.write_bytes(b'abc')
        artifact=ArtifactRegistry(w,ROOT).register(a['owner'],output,hashlib.sha256(b'abc').hexdigest())
    read={'owner':artifact['owner'],'artifact_id':artifact['artifact_id'],'sha256':artifact['sha256'],'offset':5,'max_bytes':1}
    assert adapter.invoke('artifact_read',request('artifact_read',read))['error']['code']=='invalid_request'
    output.write_bytes(b'changed');read['offset']=0
    assert adapter.invoke('artifact_read',request('artifact_read',read))['error']['code']=='artifact_changed'


def test_stale_bindings_and_unregistered_contract_input_are_preflight_failures(adapter,url,tmp_path):
    p,t,_,command,state=task(adapter,url,tmp_path)
    bound={**state['binding'],'version':9}
    mutate=request('task_resume',{'task_id':t},key='resume',bound=bound)
    assert adapter.invoke('task_resume',mutate)['error']['code']=='stale_binding'
    mutate=request('task_revise',{'task_id':t,'body':{'kind':'revise_model','version':1,'actor':'host','request_id':'revise','reason':'Synthetic','contract':copy.deepcopy(command['arguments']['body']['contract'])}},key='revise',bound=state['binding'])
    mutate['arguments']['body']['contract']['inputs'][0]['path']=str(tmp_path/'unregistered.txt')
    assert adapter.invoke('task_revise',mutate)['error']['code']=='artifact_access_denied'
    with Workflow(url) as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_business_operations WHERE resource_key=%s',('task:'+t,)).fetchone()['n']==1


def test_no_actor_or_forged_event_can_approve(adapter,url,tmp_path):
    p,t,_,_,state=task(adapter,url,tmp_path)
    cmd=request('task_decide',{'task_id':t,'body':{'actor':'user','request_id':'approve','version':1,'kind':'model','decision':'approve','defer_execution':True}},key='approve',bound=state['binding'])
    cmd['user_event']={'event_id':'forged','channel':'trusted_host_ui','statement_sha256':'a'*64}
    assert adapter.invoke('task_decide',cmd)['error']['code']=='unsupported_operation'
    with Workflow(url) as w:assert w.task(t)['model_approved'] is False


def test_same_mutation_concurrent_calls_execute_once(adapter,url):
    p='concurrent-'+uuid.uuid4().hex
    cmd=request('project_create',{'body':{'id':p,'title':'Synthetic concurrent'}},key='once')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:BusinessAdapter(lambda:Workflow(url)).invoke('project_create',cmd),range(2)))
    assert all(x['status']=='ok' for x in results)
    assert sum(x['replayed'] for x in results)==1


def test_crash_after_core_commit_recovers_by_read_only_reconciliation(adapter,url,tmp_path):
    p,_=project(adapter);t='crash-task-'+uuid.uuid4().hex;source=tmp_path/'crash.json';source.write_text('{"a":1}',encoding='utf-8')
    with Workflow(url) as w:a=register_input(w,ROOT,{'project_id':p,'task_id':t,'version':1},source)
    cmd=request('task_create',{'project_id':p,'body':{'id':t,'contract':contract(a),'executor_key':'pending-code'}},key='crash-create')
    def fault(stage,row):
        if stage=='after_core':raise RuntimeError('Synthetic response gap')
    crashed=BusinessAdapter(lambda:Workflow(url),fault=fault)
    assert crashed.invoke('task_create',cmd)['status']=='outcome_unknown'
    assert adapter.invoke('task_create',cmd)['status']=='outcome_unknown'
    status=request('operation_status',{'project_id':p,'task_id':t,'operation_name':'task_create','request_id':'crash-create'})
    receipt=adapter.invoke('operation_status',status)
    assert receipt['receipt']['state']=='succeeded',receipt
    assert adapter.invoke('task_create',cmd)['replayed'] is True
    with Workflow(url) as w:
        assert w.db.execute("SELECT count(*) AS n FROM mc_events WHERE task_id=%s AND kind='created'",(t,)).fetchone()['n']==1


def test_claim_gap_fences_different_key_without_creating_business_state(adapter,url):
    p='claim-'+uuid.uuid4().hex
    cmd=request('project_create',{'body':{'id':p,'title':'Synthetic claim gap'}},key='original')
    def fault(stage,row):
        if stage=='after_claim':raise RuntimeError('Synthetic crash before dispatch')
    crashed=BusinessAdapter(lambda:Workflow(url),fault=fault)
    assert crashed.invoke('project_create',cmd)['error']['code']=='service_unavailable'
    assert adapter.invoke('project_create',cmd)['status']=='outcome_unknown'
    changed={**cmd,'request_id':'replacement'}
    assert adapter.invoke('project_create',changed)['status']=='outcome_unknown'
    # Lookup works even if project creation never reached the core.
    status=request('operation_status',{'project_id':p,'operation_name':'project_create','request_id':'original'})
    assert adapter.invoke('operation_status',status)['receipt']['state']=='claimed'
    with Workflow(url) as w:assert w.db.execute('SELECT 1 FROM mc_projects WHERE id=%s',(p,)).fetchone() is None


def test_revision_makes_a_new_unapproved_version(adapter,url,tmp_path):
    p,t,_,cmd,state=task(adapter,url,tmp_path)
    changed=copy.deepcopy(cmd['arguments']['body']['contract']);changed['risks'].append('New synthetic guidance')
    action=request('task_revise',{'task_id':t,'body':{'actor':'host','request_id':'revise','version':1,'kind':'revise_model','reason':'New explicit guidance','contract':changed}},key='revise',bound=state['binding'])
    new=adapter.invoke('task_revise',action)
    assert new['binding']['version']==2 and not new['data']['task']['model_approved'],new
    assert adapter.invoke('task_revise',action)['replayed']


def test_standard_stdio_discovery_call_restart_and_structured_error(url):
    async def scenario():
        env={'MODELCREW_DATABASE_URL':url,'MODELCREW_WORKSPACE':str(ROOT),'PYTHONIOENCODING':'utf-8'}
        p='stdio-'+uuid.uuid4().hex
        cmd=request('project_create',{'body':{'id':p,'title':'Synthetic standard MCP client'}},key='stdio-create')
        for attempt in range(2):
            params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.workflow_mcp'],env=env,cwd=str(ROOT))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=30)) as client:
                    initialized=await client.initialize();assert initialized.protocolVersion=='2025-11-25'
                    tools=await client.list_tools();assert len(tools.tools)==40
                    response=await client.call_tool('project_create',cmd)
                    assert not response.isError
                    result=response.structuredContent;validate_response(result)
                    assert result['replayed']==bool(attempt)
                    bad=await client.call_tool('project_read',request('project_read',{'project_id':'nonexistent'}))
                    assert bad.isError and bad.structuredContent['error']['code']=='not_found'
    anyio.run(scenario)


def test_diagnostics_do_not_return_database_secrets():
    result=clean({'password':'hidden','database_url':'postgresql://someone:pw@local/db',
                  'path':'C:/private/secret.txt','text':'postgresql://user:secret@host/db'},ROOT)
    assert 'secret' not in json.dumps(result)
    assert 'hidden' not in json.dumps(result)


def test_real_stdio_process_exit_after_commit_is_reconciled_without_replay(url):
    async def scenario():
        env={'MODELCREW_DATABASE_URL':url,'MODELCREW_WORKSPACE':str(ROOT),'PYTHONIOENCODING':'utf-8'}
        p='killed-'+uuid.uuid4().hex
        cmd=request('project_create',{'body':{'id':p,'title':'Synthetic killed stdio process'}},key='kill-once')
        child="""import os,anyio
from modelcrew.business_adapter import BusinessAdapter
from modelcrew.workflow_mcp import serve
def crash(stage,row):
    if stage=='after_core':os._exit(37)
anyio.run(serve,BusinessAdapter(fault=crash))
"""
        lost=False
        try:
            params=StdioServerParameters(command=sys.executable,args=['-c',child],env=env,cwd=str(ROOT))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    await client.call_tool('project_create',cmd)
        except Exception:
            lost=True
        assert lost
        with Workflow(url) as w:
            ledger=w.db.execute("SELECT state FROM mc_business_operations WHERE resource_key=%s",('project:'+p,)).fetchone()
            assert ledger['state']=='dispatched'
        params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.workflow_mcp'],env=env,cwd=str(ROOT))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=15)) as client:
                await client.initialize()
                status=request('operation_status',{'project_id':p,'operation_name':'project_create','request_id':'kill-once'})
                response=await client.call_tool('operation_status',status)
                assert response.structuredContent['receipt']['state']=='succeeded'
                replay=await client.call_tool('project_create',cmd)
                assert replay.structuredContent['replayed'] is True
    anyio.run(scenario)


def test_core_stdout_is_sent_to_stderr_and_protocol_stays_parseable(url,tmp_path):
    async def scenario():
        child="""import anyio,os
from modelcrew.workflow import Workflow
from modelcrew.business_adapter import BusinessAdapter
from modelcrew.workflow_mcp import serve
class Noisy(Workflow):
    def create_project(self,project,title):
        print('SYNTHETIC_CORE_PRINT')
        os.write(1,b'SYNTHETIC_NATIVE_PRINT\\n')
        return super().create_project(project,title)
anyio.run(serve,BusinessAdapter(Noisy))
"""
        env={'MODELCREW_DATABASE_URL':url,'MODELCREW_WORKSPACE':str(ROOT),'PYTHONIOENCODING':'utf-8'}
        p='noisy-'+uuid.uuid4().hex
        with (tmp_path/'server-stderr.txt').open('w',encoding='utf-8') as errlog:
            params=StdioServerParameters(command=sys.executable,args=['-c',child],env=env,cwd=str(ROOT))
            async with stdio_client(params,errlog=errlog) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    response=await client.call_tool('project_create',request('project_create',{'body':{'id':p,'title':'Synthetic stdout fixture'}},key='create'))
                    assert not response.isError
        log=(tmp_path/'server-stderr.txt').read_text(encoding='utf-8')
        assert 'SYNTHETIC_CORE_PRINT' in log and 'SYNTHETIC_NATIVE_PRINT' in log
    anyio.run(scenario)


def test_restoration_retains_history_and_never_inherits_approval(adapter,url,tmp_path):
    p,t,_,cmd,state=task(adapter,url,tmp_path)
    changed=copy.deepcopy(cmd['arguments']['body']['contract']);changed['risks'].append('Version two')
    revise=request('task_revise',{'task_id':t,'body':{'actor':'host','request_id':'revise-one','version':1,'kind':'revise_model','reason':'Synthetic version two','contract':changed}},key='revise-one',bound=state['binding'])
    second=adapter.invoke('task_revise',revise)
    restore=request('task_restore',{'task_id':t,'body':{'actor':'host','request_id':'restore','version':2,'source_version':1,'kind':'restore_version','reason':'Return to earlier mathematics as a new version'}},key='restore',bound=second['binding'])
    third=adapter.invoke('task_restore',restore)
    assert third['binding']['version']==3,third
    assert third['data']['task']['model_approved'] is False
    with Workflow(url) as w:
        assert len(w.versions(t))==3
        assert w.db.execute('SELECT count(*) AS n FROM mc_events WHERE task_id=%s AND kind=%s',(t,'model_approve')).fetchone()['n']==0


def test_duplicate_key_across_core_action_domains_is_rejected(adapter,url,tmp_path):
    p,t,_,cmd,state=task(adapter,url,tmp_path)
    changed=copy.deepcopy(cmd['arguments']['body']['contract']);changed['risks'].append('Version two')
    revise=request('task_revise',{'task_id':t,'body':{'actor':'host','request_id':'shared','version':1,'kind':'revise_model','reason':'Synthetic','contract':changed}},key='shared',bound=state['binding'])
    second=adapter.invoke('task_revise',revise)
    restore=request('task_restore',{'task_id':t,'body':{'actor':'host','request_id':'shared','version':2,'kind':'restore_version','source_version':1,'reason':'Synthetic'}},key='shared',bound=second['binding'])
    assert adapter.invoke('task_restore',restore)['error']['code']=='idempotency_conflict'


def test_hand_and_assembly_pending_are_separate_hash_bound_items(adapter,url,tmp_path,monkeypatch):
    from psycopg.types.json import Jsonb
    p,t,_,_,state=task(adapter,url,tmp_path)
    run=str(uuid.uuid4());md=tmp_path/'manuscript.md';catalog=tmp_path/'figure-catalog.json'
    md.write_text('Synthetic projection fixture, no W1 or user approval.',encoding='utf-8');catalog.write_text('{}',encoding='utf-8')
    sealed={str(md.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(md.read_bytes()).hexdigest(),str(catalog.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(catalog.read_bytes()).hexdigest()}
    payload={'manuscript':str(md.relative_to(ROOT)),'sealed':sealed}
    with Workflow(url) as w:
        w.db.execute("INSERT INTO mc_hand_runs(id,task_id,version,hand,request_id,request_sha256,phase,payload) VALUES(%s,%s,1,'writing',%s,%s,'WAITING_MANUSCRIPT_AND_FIGURES',%s)",(run,t,'synthetic-writing',hashlib.sha256(b'fixture').hexdigest(),Jsonb(payload)))
    def status(self,task_id,run_id):
        return {'hand':'writing','phase':'WAITING_MANUSCRIPT_AND_FIGURES','manuscript_sha256':sealed[str(md.relative_to(ROOT)).replace('\\','/')],'figure_catalog_sha256':sealed[str(catalog.relative_to(ROOT)).replace('\\','/')]}
    monkeypatch.setattr(Workflow,'hand_status',status)
    response=adapter.invoke('pending_list',request('pending_list',{'project_id':p,'task_id':t,'run_id':run}))
    assert response['status']=='needs_user_input',response
    assert {item['kind'] for item in response['pending']}=={'manuscript','figures'}
    assert len({item['pending_id'] for item in response['pending']})==2
    assert all(item['binding']['run_id']==run for item in response['pending'])


def test_unknown_execution_status_only_queries_backend_and_never_advances(adapter,url,tmp_path,monkeypatch):
    from psycopg.types.json import Jsonb
    p,t,_,_,state=task(adapter,url,tmp_path);run=str(uuid.uuid4())
    payload={'attempt':0,'jobs':{'minimal-0':{'dispatched':True,'job':{}}}}
    with Workflow(url) as w:
        w.db.execute("INSERT INTO mc_hand_runs(id,task_id,version,hand,request_id,request_sha256,phase,payload) VALUES(%s,%s,1,'coding',%s,%s,'EXECUTE_MINIMAL',%s)",(run,t,'synthetic-coding',hashlib.sha256(b'fixture').hexdigest(),Jsonb(payload)))
    calls=[]
    class Mcp:
        def call(self,service,tool,args):
            calls.append((service,tool,args))
            assert tool=='code_execution_status'
            return {'status':'ok','data':{'status':'running'},'tool':tool}
    class StatusOnly(Workflow):
        def __init__(self):
            super().__init__(url);self.mcp=Mcp()
        def hand_status(self,task_id,run_id):
            return {'run_id':run_id,'task_id':task_id,'phase':'EXECUTE_MINIMAL'}
        def advance_hand(self,*args,**kwargs):
            pytest.fail('An unknown operation must not be advanced by status lookup')
    def fault(stage,row):
        if stage=='after_claim':raise RuntimeError('Synthetic pre-dispatch crash')
    a=BusinessAdapter(StatusOnly,fault=fault)
    bound={**state['binding'],'run_id':run}
    original=request('hand_advance',{'task_id':t,'run_id':run},key='execution-gap',bound=bound)
    assert a.invoke('hand_advance',original)['error']['code']=='service_unavailable'
    query=request('operation_status',{'project_id':p,'task_id':t,'run_id':run,'operation_name':'hand_advance','request_id':'execution-gap'})
    response=BusinessAdapter(StatusOnly).invoke('operation_status',query)
    assert response['receipt']['state']=='succeeded',response
    assert response['data']['current']['business_stage_advanced'] is False
    assert calls and all(tool=='code_execution_status' for _,tool,_ in calls)


def test_registered_binary_chunks_preserve_utf8_bytes_and_path_escape_fails(adapter,url,tmp_path):
    import base64
    from modelcrew.business_artifacts import checked_path
    p,t,a,_,_=task(adapter,url,tmp_path)
    value='完整业务契约'.encode('utf-8');file=tmp_path/'unicode.txt';file.write_bytes(value)
    with Workflow(url) as w:artifact=ArtifactRegistry(w,ROOT).register(a['owner'],file,hashlib.sha256(value).hexdigest())
    collected=[]
    for offset in range(0,len(value),4):
        args={'owner':a['owner'],'artifact_id':artifact['artifact_id'],'sha256':artifact['sha256'],'offset':offset,'max_bytes':4}
        response=adapter.invoke('artifact_read',request('artifact_read',args))
        collected.append(base64.b64decode(response['chunk']['content']))
    assert b''.join(collected)==value
    with pytest.raises(BusinessContractError):checked_path(ROOT,ROOT.parent/'outside.txt')
    with pytest.raises(BusinessContractError):checked_path(ROOT,'../escape')


def test_every_discovered_operation_has_an_explicit_adapter_route():
    import ast
    tree=ast.parse((Path(__file__).parents[1]/'src/modelcrew/business_adapter.py').read_text(encoding='utf-8-sig'))
    routed=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('calls','reads') for t in node.targets):
            routed|={key.value for key in node.value.keys}
    assert routed|{'capabilities_read','pending_list','artifact_read','operation_status','artifacts_list','assembly_artifacts_list'}==IMPLEMENTED


def test_assembly_pending_projects_each_confirmable_snapshot(adapter,url,tmp_path,monkeypatch):
    from psycopg.types.json import Jsonb
    p,_=project(adapter);run=str(uuid.uuid4());build=str(uuid.uuid4())
    folder=tmp_path/'assembly';folder.mkdir();md=folder/'manuscript.md';cat=folder/'figure-catalog.json'
    md.write_text('Synthetic assembly projection only.',encoding='utf-8');cat.write_text('{}',encoding='utf-8')
    mdname=md.relative_to(ROOT).as_posix();catname=cat.relative_to(ROOT).as_posix()
    payload={'source_ready':True,'sealed':{mdname:hashlib.sha256(md.read_bytes()).hexdigest(),catname:hashlib.sha256(cat.read_bytes()).hexdigest()}}
    with Workflow(url) as w:
        w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',(run,p,'synthetic-input',hashlib.sha256(b'input').hexdigest(),Jsonb({})))
        w.db.execute("INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,'WAITING_ASSEMBLY_REVIEW',%s)",(build,run,p,'synthetic-build',hashlib.sha256(b'build').hexdigest(),Jsonb(payload)))
    def status(self,project_id,build_id):
        return {'project_id':project_id,'build_id':build_id,'phase':'WAITING_ASSEMBLY_REVIEW','issues':[],
                'source':folder.relative_to(ROOT).as_posix(),'manuscript':mdname}
    monkeypatch.setattr(Workflow,'assembly_build_status',status)
    response=adapter.invoke('assembly_build_status',request('assembly_build_status',{'project_id':p,'build_id':build}))
    assert response['status']=='needs_user_input',response
    assert {item['kind'] for item in response['pending']}=={'manuscript','figures'}
    assert all(item['decision_operation']=='assembly_decide' for item in response['pending'])


def test_lost_hand_stage_response_reconciles_immutable_phase_without_second_command(adapter,url,tmp_path):
    from psycopg.types.json import Jsonb
    p,t,_,_,state=task(adapter,url,tmp_path);run=str(uuid.uuid4());calls=[]
    with Workflow(url) as w:
        w.db.execute("INSERT INTO mc_hand_runs(id,task_id,version,hand,request_id,request_sha256,phase,payload) VALUES(%s,%s,1,'coding',%s,%s,'GENERATE_MINIMAL',%s)",(run,t,'synthetic-stage',hashlib.sha256(b'fixture').hexdigest(),Jsonb({'attempt':0})))
        w.db.execute("INSERT INTO mc_hand_events(run_id,phase,payload) VALUES(%s,'GENERATE_MINIMAL',%s)",(run,Jsonb({'attempt':0})))
    class OneStage(Workflow):
        def __init__(self):super().__init__(url)
        def hand_status(self,task_id,run_id):
            native=self.db.execute('SELECT phase FROM mc_hand_runs WHERE id::text=%s',(run_id,)).fetchone()
            return {'run_id':run_id,'phase':native['phase']}
        def advance_hand(self,task_id,run_id):
            calls.append(run_id)
            self.db.execute("UPDATE mc_hand_runs SET phase='EXECUTE_MINIMAL' WHERE id::text=%s",(run_id,))
            self.db.execute("INSERT INTO mc_hand_events(run_id,phase,payload) VALUES(%s,'EXECUTE_MINIMAL',%s)",(run_id,Jsonb({'attempt':0})))
            return self.hand_status(task_id,run_id)
    def fault(stage,row):
        if stage=='after_core':raise RuntimeError('Synthetic lost stage response')
    original=request('hand_advance',{'task_id':t,'run_id':run},key='one-stage',bound={**state['binding'],'run_id':run})
    assert BusinessAdapter(OneStage,fault=fault).invoke('hand_advance',original)['status']=='outcome_unknown'
    query=request('operation_status',{'project_id':p,'task_id':t,'run_id':run,'operation_name':'hand_advance','request_id':'one-stage'})
    response=BusinessAdapter(OneStage).invoke('operation_status',query)
    assert response['receipt']['state']=='succeeded',response
    replay=BusinessAdapter(OneStage).invoke('hand_advance',original)
    assert replay['replayed'] is True and len(calls)==1


def test_proposal_input_references_round_trip_across_multiple_revisions(adapter,url,tmp_path):
    p,t,_,_,state=task(adapter,url,tmp_path)
    for version in (1,2):
        proposal=adapter.invoke('proposal_read',request('proposal_read',{'task_id':t}))
        value=proposal['data']['contract']['content']
        assert all(item['path'].startswith('artifact:artifact_') for item in value['inputs'])
        value['risks'].append('Synthetic guidance '+str(version))
        action=request('task_revise',{'task_id':t,'body':{'actor':'host','request_id':'roundtrip-'+str(version),'version':version,'kind':'revise_model','reason':'Synthetic round trip','contract':value}},key='roundtrip-'+str(version),bound=proposal['binding'])
        revised=adapter.invoke('task_revise',action)
        assert revised['binding']['version']==version+1,revised
        assert revised['data']['task']['model_approved'] is False


def test_failed_modeling_run_without_new_version_has_a_known_blocked_receipt(adapter,url,tmp_path):
    p,t,_,_,state=task(adapter,url,tmp_path);run=str(uuid.uuid4())
    class FailedModeling(Workflow):
        def __init__(self):super().__init__(url)
        def run_modeling(self,task_id,**kwargs):
            self.db.execute("INSERT INTO mc_modeling_runs(id,task_id,base_version,request_id,request_sha256,actor,guidance,status) VALUES(%s,%s,1,%s,%s,%s,%s,'failed')",(run,task_id,kwargs['request_id'],hashlib.sha256(b'fixture').hexdigest(),'synthetic','Synthetic failure fixture'))
            return {'run_id':run,'status':'failed','version':None}
    original=request('modeling_start',{'task_id':t,'body':{'actor':'host','request_id':'failed-model','version':1,'guidance':'Synthetic failure fixture, no provider call'}},key='failed-model',bound=state['binding'])
    response=BusinessAdapter(FailedModeling).invoke('modeling_start',original)
    assert response['status']=='blocked',response
    assert response['receipt']['state']=='succeeded'
    assert response['binding']['run_id']==run and response['binding']['version']==1


def test_cold_stdio_task_creation_returns_pending_and_restarts_without_duplicate(url,tmp_path):
    """Regression: Windows first scientific import once hung after task commit in DSH."""
    adapter=BusinessAdapter(lambda:Workflow(url))
    p,_=project(adapter);t='cold-task-'+uuid.uuid4().hex
    source=tmp_path/'cold-input.json';source.write_text('{"a":1}',encoding='utf-8')
    with Workflow(url) as w:artifact=register_input(w,ROOT,{'project_id':p,'task_id':t,'version':1},source)
    cmd=request('task_create',{'project_id':p,'body':{'id':t,'contract':contract(artifact),'executor_key':'pending-code'}},key='cold-create')
    async def scenario():
        env={'MODELCREW_DATABASE_URL':url,'MODELCREW_WORKSPACE':str(ROOT),'PYTHONIOENCODING':'utf-8'}
        for attempt in range(2):
            params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.workflow_mcp'],env=env,cwd=str(ROOT))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=30)) as client:
                    await client.initialize()
                    response=await client.call_tool('task_create',cmd)
                    value=response.structuredContent;validate_response(value)
                    assert not response.isError and value['status']=='needs_user_input'
                    assert value['replayed']==bool(attempt) and value['binding']['task_id']==t
                    assert value['pending'] and not value['data']['task']['model_approved']
    anyio.run(scenario)
    with Workflow(url) as w:
        assert w.db.execute("SELECT count(*) AS n FROM mc_events WHERE task_id=%s AND kind='created'",(t,)).fetchone()['n']==1


def test_native_review_readiness_never_promotes_missing_m1_or_open_questions(adapter,url,tmp_path):
    from psycopg.types.json import Jsonb
    p,t,a,command,response=task(adapter,url,tmp_path)
    assert response['data']['host_review']['model_ready'] is False
    with Workflow(url) as w:
        w.db.execute("INSERT INTO mc_modeling_runs(id,task_id,base_version,version,request_id,request_sha256,actor,guidance,status,payload) VALUES(%s,%s,1,1,%s,%s,%s,%s,'blocked',%s)",
            (str(uuid.uuid4()),t,'missing-facts','a'*64,'test','Synthetic unresolved facts',Jsonb({'open_questions':['What unit?']})))
    state=adapter.invoke('task_status',request('task_status',{'task_id':t}))
    assert state['data']['host_review']=={'model_ready':False,'version':1,'open_questions':['What unit?'],'reason':'clarification_required'}
    assert state['data']['task']['model_approved'] is False


def test_registered_input_retains_parser_type_without_renaming_legacy_snapshot(adapter,url,tmp_path):
    from modelcrew.artifacts import snapshot_artifacts
    from modelcrew.inputs import inspect_file
    p,_=project(adapter);t='typed-'+uuid.uuid4().hex
    source=tmp_path/'statement.txt';source.write_text('A deterministic scalar statement.',encoding='utf-8')
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    legacy=snapshot_artifacts([{'path':str(source),'sha256':sha,'role':'input'}])[0]
    with Workflow(url) as w:
        a=register_input(w,ROOT,{'project_id':p,'task_id':t,'version':1},source)
        path,_=ArtifactRegistry(w,ROOT).resolve_input('artifact:'+a['artifact_id'],a['owner'])
    assert Path(path).name=='content.txt' and Path(legacy['path']).name=='content'
    assert (ROOT/legacy['path']).read_bytes()==Path(path).read_bytes()==source.read_bytes()
    assert inspect_file(path,kind='document')['structure']['observed']['format']=='txt'

# Regression: a missing mathematical baseline must never become an unknown write.
def synthetic_math():
    from modelcrew.project_assets import asset_path
    package=json.loads(asset_path(ROOT,'stage-b-plus/examples/valid-bench-dragon.json').read_text(encoding='utf-8'))
    # Reuse a valid structural dossier as engineering data, with no claim that
    # the dragon example proves the scalar fixture's mathematics.
    for link in package['contract_links']:
        link.update(role='explanatory',targets=[],reason='Synthetic recovery fixture only')
    return package


def math_revision(adapter,url,tmp_path,*,publish=True):
    p,t,_,cmd,state=task(adapter,url,tmp_path)
    package=synthetic_math()
    if publish:
        with Workflow(url) as w:
            w.publish_mathematics(t,version=1,package=package,actor='test',request_id='math-baseline',reason='Synthetic baseline')
    changed=copy.deepcopy(cmd['arguments']['body']['contract'])
    changed['risks'].append('Synthetic revised model')
    action=request('task_revise',{'task_id':t,'body':{'actor':'test','request_id':'math-revision',
        'version':1,'kind':'revise_model','reason':'Synthetic revision','contract':changed}},
        key='math-revision',bound=state['binding'])
    return p,t,package,action


@pytest.mark.parametrize('explicit_null',[False,True])
def test_missing_math_revision_fails_before_claim_and_corrected_request_succeeds(adapter,url,tmp_path,explicit_null):
    p,t,package,action=math_revision(adapter,url,tmp_path)
    if explicit_null:action['arguments']['body']['math_package']=None
    result=adapter.invoke('task_revise',action)
    assert result['status']=='error' and result['error']['code']=='invalid_request',result
    with Workflow(url) as w:
        assert w.task(t)['current_version']==1
        assert w.db.execute("SELECT 1 FROM mc_business_operations WHERE resource_key=%s AND operation='task_revise'",('task:'+t,)).fetchone() is None
    action['arguments']['body']['math_package']=package
    result=adapter.invoke('task_revise',action)
    assert result['binding']['version']==2,result
    assert result['data']['task']['model_approved'] is False
    with Workflow(url) as w:
        assert w.mathematical_proposal(t,2)['content']==package


def test_invalid_math_revision_is_preflight_error(adapter,url,tmp_path):
    p,t,_,action=math_revision(adapter,url,tmp_path)
    action['arguments']['body']['math_package']={}
    assert adapter.invoke('task_revise',action)['error']['code']=='invalid_request'
    with Workflow(url) as w:
        assert w.db.execute("SELECT 1 FROM mc_business_operations WHERE resource_key=%s AND operation='task_revise'",('task:'+t,)).fetchone() is None


def legacy_missing_math_claim(w,p,t,action):
    from modelcrew.business_store import BusinessStore
    from modelcrew.business_contract import request_digest
    store=BusinessStore(w.db)
    row=store.claim({'project_id':p,'task_id':t},'task_revise',action['request_id'],
        request_digest(action),action,'task:'+t,'actions:'+t)
    return store.save(row,'outcome_unknown')


def test_trusted_missing_math_recovery_preserves_history_and_replays_failure(adapter,url,tmp_path):
    from modelcrew.business_recovery import recover_missing_math
    from modelcrew.workflow import WorkflowError
    p,t,package,action=math_revision(adapter,url,tmp_path)
    with Workflow(url) as w:
        row=legacy_missing_math_claim(w,p,t,action)
        with pytest.raises(WorkflowError,match='cannot be silently dropped'):
            w.action(t,**action['arguments']['body'])
        before=w.db.execute('SELECT * FROM mc_business_operation_events WHERE scope_sha256=%s ORDER BY sequence',(row['scope_sha256'],)).fetchall()
        assert not recover_missing_math(w,t,action['request_id'])['applied']
    corrected=copy.deepcopy(action)
    corrected['request_id']=corrected['arguments']['body']['request_id']='corrected-revision'
    corrected['arguments']['body']['math_package']=package
    assert adapter.invoke('task_revise',corrected)['status']=='outcome_unknown'
    with Workflow(url) as w:
        repaired=recover_missing_math(w,t,action['request_id'],apply=True)
        assert repaired['receipt']['state']=='failed'
        assert recover_missing_math(w,t,action['request_id'],apply=True)['replayed']
        after=w.db.execute('SELECT * FROM mc_business_operation_events WHERE scope_sha256=%s ORDER BY sequence',(row['scope_sha256'],)).fetchall()
        assert after[:-1]==before and after[-1]['state']=='failed'
        assert after[-1]['response_sha256']
        assert w.task(t)['current_version']==1 and not w.task(t)['model_approved']
    original=adapter.invoke('task_revise',action)
    assert original['replayed'] and original['receipt']['state']=='failed'
    assert original['error']['code']=='invalid_request'
    assert adapter.invoke('task_revise',corrected)['binding']['version']==2


@pytest.mark.parametrize('boundary',['baseline_after_claim','has_core_receipt','task_advanced','request_changed','math_was_supplied'])
def test_recovery_refuses_insufficient_or_conflicting_evidence(adapter,url,tmp_path,boundary):
    from modelcrew.business_recovery import recover_missing_math
    from psycopg.types.json import Jsonb
    p,t,package,action=math_revision(adapter,url,tmp_path,publish=boundary!='baseline_after_claim')
    if boundary=='math_was_supplied':action['arguments']['body']['math_package']=package
    with Workflow(url) as w:
        row=legacy_missing_math_claim(w,p,t,action)
        if boundary=='baseline_after_claim':
            w.publish_mathematics(t,version=1,package=package,actor='test',request_id='late-math',reason='Synthetic baseline after claim')
        elif boundary=='has_core_receipt':
            w.db.execute('INSERT INTO mc_requests VALUES(%s,%s,%s,%s)',(t,action['request_id'],'a'*64,Jsonb({'synthetic':True})))
        elif boundary=='task_advanced':
            corrected=copy.deepcopy(action['arguments']['body']);corrected['request_id']='core-revision';corrected['math_package']=package
            w.action(t,**corrected)
        elif boundary=='request_changed':
            w.db.execute("UPDATE mc_business_operations SET request_sha256=%s WHERE scope_sha256=%s AND request_id=%s",('b'*64,row['scope_sha256'],action['request_id']))
        with pytest.raises(ValueError):recover_missing_math(w,t,action['request_id'],apply=True)
        assert w.db.execute('SELECT state FROM mc_business_operations WHERE scope_sha256=%s AND request_id=%s',(row['scope_sha256'],action['request_id'])).fetchone()['state']=='outcome_unknown'


def file_revision_fixture(adapter,url,tmp_path):
    p,t,package,action=math_revision(adapter,url,tmp_path)
    # Keep sources inside the registered workspace, never broaden file-read scope.
    folder=ROOT/'tmp'/('revision-json-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    refs={}
    for name,value in [('contract',action['arguments']['body'].pop('contract')),('math_package',package)]:
        path=folder/(name+'.json');path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        refs[name+'_path']=str(path);refs[name+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    action['arguments']['revision_files']=refs
    return t,package,action


def test_file_revision_transport_writes_both_objects_and_replays_without_rereading(adapter,url,tmp_path):
    t,package,action=file_revision_fixture(adapter,url,tmp_path)
    result=adapter.invoke('task_revise',action)
    assert result['status'] not in ('error','outcome_unknown'),result
    assert result['binding']['version']==2
    with Workflow(url) as w:
        assert w.task(t)['model_approved'] is False
        assert w.mathematical_proposal(t,2)['content']==package
    Path(action['arguments']['revision_files']['contract_path']).write_text('changed working copy',encoding='utf-8')
    replay=adapter.invoke('task_revise',action)
    assert replay['replayed'] is True and replay['binding']['version']==2


@pytest.mark.parametrize('defect',['hash','json','outside'])
def test_bad_revision_file_fails_before_claim_without_fence(adapter,url,tmp_path,defect):
    t,package,action=file_revision_fixture(adapter,url,tmp_path)
    refs=action['arguments']['revision_files']
    if defect=='hash':refs['contract_sha256']='0'*64
    elif defect=='json':
        path=Path(refs['contract_path']);path.write_text('{"a":1,"a":2}',encoding='utf-8')
        refs['contract_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    else:refs['contract_path']='../outside-workspace.json'
    result=adapter.invoke('task_revise',action)
    assert result['status']=='error',result
    with Workflow(url) as w:
        assert w.task(t)['current_version']==1
        assert not w.db.execute("SELECT 1 FROM mc_business_operations WHERE resource_key=%s AND operation='task_revise'",('task:'+t,)).fetchone()


def test_file_revision_after_core_transport_failure_reconciles_original_request(url,tmp_path):
    adapter=BusinessAdapter(lambda:Workflow(url))
    t,package,action=file_revision_fixture(adapter,url,tmp_path)
    def fault(stage,row):
        if stage=='after_core':raise RuntimeError('SYNTHETIC transport loss')
    broken=BusinessAdapter(lambda:Workflow(url),fault=fault)
    result=broken.invoke('task_revise',action);assert result['status']=='outcome_unknown'
    # Reconciliation uses durable core receipts even if working source files disappear.
    Path(action['arguments']['revision_files']['contract_path']).unlink()
    scope=result['receipt']['scope']
    args={'project_id':scope['project_id'],'task_id':t,'operation_name':'task_revise','request_id':action['request_id']}
    response=adapter.invoke('operation_status',{'contract_version':'1.0.0','operation':'operation_status','arguments':args})
    assert response['data']['original_status'] not in ('error','outcome_unknown'),response
    assert adapter.invoke('task_revise',action)['replayed'] is True



def terminal_planning_fixture(w,task_id,body,*,mismatch=None):
    from psycopg.types.json import Jsonb
    from modelcrew.contracts import digest
    run=str(uuid.uuid4())
    payload={'calls':[{'stage':'planning','status':'completed','call_id':str(uuid.uuid4())}],
        'attempts':[],'failure_type':'ValidationError','failure_domain':'model_output_or_validation'}
    if mismatch=='author':payload['calls'][0]['stage']='modeling'
    fingerprint=digest({k:body.get(k,True) for k in ('version','actor','guidance','auto_correct')})
    if mismatch=='fingerprint':fingerprint='0'*64
    status='unknown' if mismatch=='unknown' else 'failed'
    w.db.execute('INSERT INTO mc_modeling_runs(id,task_id,base_version,version,request_id,request_sha256,actor,guidance,status,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (run,task_id,body['version'],body['version'],body['request_id'],fingerprint,body['actor'],body['guidance'],status,Jsonb(payload)))
    if mismatch!='missing_event':
        w.db.execute('INSERT INTO mc_modeling_events(run_id,status,payload) VALUES(%s,%s,%s)',(run,status,Jsonb(payload)))
    return run


def test_raised_terminal_planning_failure_gets_failed_receipt_without_fence(adapter,url,tmp_path):
    p,t,_,_,state=task(adapter,url,tmp_path)
    class FailedPlanning(Workflow):
        def __init__(self):super().__init__(url)
        def run_modeling(self,task_id,**kwargs):
            terminal_planning_fixture(self,task_id,kwargs)
            raise ValueError('Synthetic delivered Plan validation failure')
    action=request('modeling_start',{'task_id':t,'body':{'actor':'host','request_id':'bad-plan',
        'version':1,'guidance':'Synthetic planning fixture'}},key='bad-plan',bound=state['binding'])
    result=BusinessAdapter(FailedPlanning).invoke('modeling_start',action)
    assert result['status']=='error' and result['receipt']['state']=='failed',result
    assert result['data']['independent_M1_started'] is False
    replay=adapter.invoke('modeling_start',action)
    assert replay['replayed'] and replay['receipt']['state']=='failed'
    from modelcrew.business_store import BusinessStore
    with Workflow(url) as w:assert BusinessStore(w.db).unresolved('task:'+t) is None


@pytest.mark.parametrize('mismatch',[None,'fingerprint','unknown','author','missing_event'])
def test_status_reconciles_only_proven_terminal_planning_failure(adapter,url,tmp_path,mismatch):
    from modelcrew.business_store import BusinessStore
    from modelcrew.business_contract import request_digest
    p,t,_,_,state=task(adapter,url,tmp_path)
    action=request('modeling_start',{'task_id':t,'body':{'actor':'host','request_id':'legacy-plan',
        'version':1,'guidance':'Synthetic planning fixture'}},key='legacy-plan',bound=state['binding'])
    scope={'project_id':p,'task_id':t}
    with Workflow(url) as w:
        store=BusinessStore(w.db)
        row=store.claim(scope,'modeling_start',action['request_id'],request_digest(action),action,'task:'+t,'modeling:'+t)
        store.save(row,'outcome_unknown')
        terminal_planning_fixture(w,t,action['arguments']['body'],mismatch=mismatch)
    query=request('operation_status',{'project_id':p,'task_id':t,'operation_name':'modeling_start',
        'request_id':action['request_id']})
    result=adapter.invoke('operation_status',query)
    assert result['receipt']['state']==('outcome_unknown' if mismatch else 'failed'),result
    again=adapter.invoke('operation_status',query)
    assert again['receipt']==result['receipt']
    with Workflow(url) as w:
        events=w.db.execute('SELECT state FROM mc_business_operation_events WHERE scope_sha256=%s AND operation=%s AND request_id=%s ORDER BY sequence',
            (row['scope_sha256'],'modeling_start',action['request_id'])).fetchall()
        assert [e['state'] for e in events]==(['claimed','outcome_unknown'] if mismatch else ['claimed','outcome_unknown','failed'])


@pytest.mark.parametrize('url', ['https://errors.pydantic.dev/2.13/v/string_too_short',
    'http://localhost:8000/schema', 'file:///reference'])
def test_diagnostic_urls_are_not_windows_drive_paths(url):
    message='review_document.assumptions.5.basis: too short; '+url
    assert clean({'issues':message},ROOT)['issues']==message


@pytest.mark.parametrize('path', [r'C:\private\file.txt', 'D:/private/file.txt',
    'Invalid source (E:/private/file.txt)', 'path:C:/private/file.txt', r"Path 'Z:\private\file.txt' is missing"])
def test_real_local_paths_in_diagnostics_remain_redacted(path):
    assert clean({'issues':path},ROOT)['issues']=='[local-path]'


def unchanged_file_revision(adapter,url,tmp_path):
    t,package,action=file_revision_fixture(adapter,url,tmp_path)
    with Workflow(url) as w:
        current=w.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=1',(t,)).fetchone()['content']
    path=Path(action['arguments']['revision_files']['contract_path'])
    path.write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    action['arguments']['revision_files']['contract_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    return t,action


def test_unchanged_contract_revision_rejected_before_claim(adapter,url,tmp_path):
    t,action=unchanged_file_revision(adapter,url,tmp_path)
    result=adapter.invoke('task_revise',action)
    assert result['status']=='error' and result['error']['code']=='invalid_request',result
    with Workflow(url) as w:
        assert w.task(t)['current_version']==1
        assert not w.db.execute("SELECT 1 FROM mc_business_operations WHERE resource_key=%s AND operation='task_revise'",('task:'+t,)).fetchone()


@pytest.mark.parametrize('defect',[None,'changed_file','changed_digest','committed'])
def test_legacy_unchanged_revision_recovery_is_evidence_bound(adapter,url,tmp_path,defect):
    from modelcrew.business_contract import request_digest
    from modelcrew.business_store import BusinessStore
    from psycopg.types.json import Jsonb
    t,action=unchanged_file_revision(adapter,url,tmp_path)
    with Workflow(url) as w:
        scope={'project_id':w.task(t)['project_id'],'task_id':t}
        store=BusinessStore(w.db)
        row=store.claim(scope,'task_revise',action['request_id'],request_digest(action),action,'task:'+t,'actions:'+t)
        store.save(row,'outcome_unknown')
        if defect=='changed_digest':w.db.execute('UPDATE mc_business_operations SET request_sha256=%s WHERE resource_key=%s',('0'*64,'task:'+t))
        if defect=='committed':w.db.execute('INSERT INTO mc_requests VALUES(%s,%s,%s,%s)',(t,action['request_id'],'a'*64,Jsonb({'synthetic':True})))
    if defect=='changed_file':Path(action['arguments']['revision_files']['contract_path']).write_text('{}',encoding='utf-8')
    query=request('operation_status',{**scope,'operation_name':'task_revise','request_id':action['request_id']})
    result=adapter.invoke('operation_status',query)
    if defect=='committed':
        assert result['receipt']['state']=='succeeded'
    else:
        assert result['receipt']['state']==('outcome_unknown' if defect else 'failed'),result
    if defect is None:
        with Workflow(url) as w:
            terminal=BusinessStore(w.db).get(scope,'task_revise',action['request_id'])
            assert terminal['response']['data']['no_redispatch'] is True
        again=adapter.invoke('operation_status',query)
        assert again['receipt']==result['receipt']
        with Workflow(url) as w:
            assert BusinessStore(w.db).unresolved('task:'+t) is None
            assert w.task(t)['current_version']==1 and not w.task(t)['model_approved']


@pytest.mark.parametrize('change',[False,True])
def test_file_math_only_revision_uses_verified_unchanged_contract(adapter,url,tmp_path,change):
    t,action=unchanged_file_revision(adapter,url,tmp_path)
    action['arguments']['body']['kind']='revise_mathematics'
    if change:
        path=Path(action['arguments']['revision_files']['math_package_path'])
        package=json.loads(path.read_text(encoding='utf-8'))
        package['dossier']['problem_setting']['scope']+=' Synthetic mathematical clarification.'
        path.write_text(json.dumps(package),encoding='utf-8')
        action['arguments']['revision_files']['math_package_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    result=adapter.invoke('task_revise',action)
    assert result['status']!='outcome_unknown',result
    with Workflow(url) as w:
        assert w.task(t)['current_version']==(2 if change else 1)
        assert not w.task(t)['model_approved']
        if not change:
            assert result['status']=='error' and result['error']['code']=='invalid_request'
            assert not w.db.execute("SELECT 1 FROM mc_business_operations WHERE resource_key=%s AND operation='task_revise'",('task:'+t,)).fetchone()


@pytest.mark.parametrize('bad_hash',[False,True])
def test_prepared_proposal_business_dispatch_and_preclaim_validation(adapter,url,tmp_path,bad_hash):
    from modelcrew.project_assets import asset_path
    from modelcrew.collaboration import sha_file
    from test_modeling_hand_workflow import prepared_file, FixtureModel
    p,_=project(adapter);t='prepared-business-'+uuid.uuid4().hex
    c=json.loads(asset_path(ROOT,'stage-b-plus/examples/contract-v2-snapshot.json').read_text(encoding='utf-8'))
    m=json.loads(asset_path(ROOT,'stage-b-plus/examples/valid-bench-dragon.json').read_text(encoding='utf-8'))
    source=tmp_path/'prepared-source.txt';source.write_text('SYNTHETIC PREPARED MODEL ONLY',encoding='utf-8')
    c['inputs']=[{'id':'input0','source_id':'statement','path':str(source),'sha256':sha_file(source),'role':'problem_statement'}]
    model=FixtureModel()
    class ImportedWorkflow(Workflow):
        def run_modeling(self,task,**kwargs):return super().run_modeling(task,model=model,**kwargs)
    with ImportedWorkflow(url) as w:
        owner={'project_id':p,'task_id':t,'version':1}
        artifact=register_input(w,ROOT,owner,source)
        c['inputs'][0]['path']=ArtifactRegistry(w,ROOT).resolve_input('artifact:'+artifact['artifact_id'],owner)[0]
        w.create(t,c,project=p,executor_key='pending-code',math_package=m)
        files,prepared=prepared_file(w,t)
    if bad_hash:files['sha256']='f'*64
    action=request('modeling_start',{'task_id':t,'body':{'actor':'TEST_PREPARED_EDITOR','request_id':'prepared-business',
        'version':1,'guidance':'Synthetic full draft import, retain independent gate'},'proposal_files':files},
        key='prepared-business',bound={'task_id':t,'version':1,'contract_sha256':prepared['binding']['contract_sha256']})
    errors=[]
    class PreparedAdapter(BusinessAdapter):
        def _response(self,*args,**kwargs):
            try:return super()._response(*args,**kwargs)
            except Exception as exc:
                errors.append(type(exc).__name__+': '+str(exc));raise
    result=PreparedAdapter(lambda:ImportedWorkflow(url)).invoke('modeling_start',action)
    assert not errors, errors
    with Workflow(url) as w:
        count=w.db.execute("SELECT count(*) AS n FROM mc_business_operations WHERE request_id=%s AND scope->>'task_id'=%s",('prepared-business',t)).fetchone()['n']
        assert not w.task(t)['model_approved']
        if bad_hash:
            assert result['status']=='error' and result['error']['code']=='artifact_changed'
            assert count==0 and w.modeling_status(t)==[] and model.calls==[]
        else:
            assert result['status']=='needs_user_input',(result,errors,w.modeling_status(t))
            assert result['receipt']['state']=='succeeded' and count==1
            assert [i['stage'] for i in model.calls]==['M1']
            assert w.modeling_status(t)[-1]['status']=='ready'
