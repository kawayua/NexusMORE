"""Replaceable, version-bound execution boundary. MCP backend execution is implemented in mcp_execution."""
from .project_assets import asset_path
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import hashlib,json
from .config import ROOT
from .contracts import digest
from .inputs import file_hash
from .artifacts import snapshot_artifacts

@dataclass(frozen=True)
class ExecutionRequest:
    task_id:str
    version:int
    contract_sha256:str
    operation_key:str
    backend_key:str
    config:dict
    contract:dict

class ExecutionBackend(Protocol):
    replay_safe:bool
    def execute(self,request:ExecutionRequest)->dict: ...

def receipt(request,artifacts,*,mode='fixture',review=None,details=None,run_id=None):
    return {'receipt_version':'1.0.0','operation_key':request.operation_key,'task_id':request.task_id,
            'version':request.version,'contract_sha256':request.contract_sha256,'backend_key':request.backend_key,
            'status':'succeeded','mode':mode,'run_id':run_id,'artifacts':artifacts,
            'review':review or {'status':'unknown','mode':mode,'note':'Fixed evidence import only; not newly computed under this contract.'},
            'details':details or {}}

def validate_receipt(value,request):
    expected={'operation_key':request.operation_key,'task_id':request.task_id,'version':request.version,'contract_sha256':request.contract_sha256,'backend_key':request.backend_key}
    if not isinstance(value,dict) or any(value.get(k)!=v for k,v in expected.items()):raise ValueError('Execution receipt request binding mismatch')
    if value.get('receipt_version')!='1.0.0' or value.get('status')!='succeeded' or value.get('mode') not in ['fixture','solver']:raise ValueError('Invalid execution receipt status or mode')
    if not isinstance(value.get('details'),dict):raise ValueError('Receipt details must be an object')
    if not isinstance(value.get('artifacts'),list) or not value['artifacts']:raise ValueError('Execution receipt needs artifacts')
    for item in value['artifacts']:
        if not isinstance(item,dict) or not all(isinstance(item.get(k),str) and item[k] for k in ['path','sha256','role']):raise ValueError('Invalid execution receipt artifact')
    review=value.get('review',{})
    if review.get('status') not in ['passed','unknown'] or review.get('mode')!=value['mode']:raise ValueError('Execution receipt needs a nonfailed bound review')
    if value['mode']=='fixture' and review['status']!='unknown':raise ValueError('Fixture cannot claim a passed model review')
    if value['mode']=='solver' and not value.get('run_id'):raise ValueError('Solver receipt needs run_id')
    digest(value)
    return value

class HistoricalFixture:
    replay_safe=True
    def artifacts(self,contract):
        base=asset_path(ROOT,'stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z')
        result=[]
        for name in ['output/result1.xlsx','output/trajectories.npz','comparison.json']:
            path=base/name
            if not path.is_file():raise ValueError('Stage A fixture missing')
            result.append({'path':str(path.relative_to(ROOT)),'sha256':file_hash(path),'role':'historical_fixture'})
        return result
    def execute(self,request):return receipt(request,self.artifacts(request.contract),details={'not_new_solve':True})

class ManifestFixture:
    replay_safe=True
    def execute(self,request):
        path=Path(request.config['manifest_path'])
        if file_hash(path)!=request.config['manifest_sha256']:raise ValueError('Fixture manifest changed')
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        if set(value)!={'contract_sha256','artifacts','description'} or value['contract_sha256']!=request.contract_sha256:raise ValueError('Fixture manifest contract binding mismatch')
        if not isinstance(value['description'],str) or not value['description'].strip():raise ValueError('Fixture description required')
        return receipt(request,value['artifacts'],details={'manifest_sha256':request.config['manifest_sha256'],'description':value['description'],'not_new_solve':True})

class ReviewedRun:
    replay_safe=True
    def execute(self,request):
        # Validate already reviewed/executed artifacts; never dispatch generated code.
        from .solver_validation import validate_run
        run=asset_path(ROOT,request.config['run_dir']).resolve()
        validation,artifacts=validate_run(run,request.contract)
        return receipt(request,artifacts,mode='solver',run_id=run.name,review={'status':'passed','mode':'solver','independent_validation':validation,'user_confirmation':'pending'},details={'new_code_executed':False,'registered_existing_reviewed_run':True})

class PendingCode:
    replay_safe=True
    def execute(self,request):
        raise ValueError('Code is not registered; approved modeling must hand off to controlled Coder/P1 before execution')

def backends():return {'pending-code':PendingCode(),'historical-fixture':HistoricalFixture(),'manifest-fixture':ManifestFixture(),'reviewed-run':ReviewedRun()}

def prepare_config(key,config):
    if not isinstance(config,dict):raise ValueError('Executor config must be an object')
    if key=='pending-code':
        if config:raise ValueError('Pending-code backend takes no config')
    elif key=='historical-fixture':
        if config:raise ValueError('Historical fixture takes no config')
    elif key=='manifest-fixture':
        if set(config)!={'manifest_path','manifest_sha256'}:raise ValueError('Manifest fixture needs manifest_path and manifest_sha256')
        item={'path':config['manifest_path'],'sha256':config['manifest_sha256'],'role':'executor_manifest'}
        saved=snapshot_artifacts([item])[0]
        return {'manifest_path':str(asset_path(ROOT,saved['path'])),'manifest_sha256':saved['sha256']}
    elif key=='mcp-code-executor':
        if set(config)!={'job_id','job_sha256'}:raise ValueError('MCP executor needs job_id and job_sha256')
        from .docker_executor import DockerExecutor
        from .mcp_client import executor_root
        _,job=DockerExecutor(executor_root()).job(config['job_id'])
        if config['job_sha256']!=job['job_sha256']:raise ValueError('MCP job hash mismatch')
        return {'job_id':job['job_id'],'job_sha256':job['job_sha256']}
    elif key=='reviewed-run':
        if set(config)!={'run_dir'}:raise ValueError('Reviewed run needs run_dir')
        return {'run_dir':str(Path(config['run_dir']).resolve())}
    return config
