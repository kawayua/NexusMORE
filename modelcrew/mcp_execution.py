"""MCP-backed execution; known operations recover through status, never redispatch."""
from pathlib import Path
from .contracts import digest
from .docker_executor import DockerExecutor
from .executors import receipt
from .mcp_client import executor_root
from .mcp_workflow import trace_call


class McpExecutionError(ValueError):
    def __init__(self,code,domain,message):
        super().__init__(message);self.code=code;self.failure_domain=domain


def checked_job(task,version,contract,config):
    if not isinstance(config,dict) or set(config)!={'job_id','job_sha256'}:
        raise ValueError('MCP executor config requires job_id and job_sha256')
    _,job=DockerExecutor(executor_root()).job(config['job_id'])
    if job['job_sha256']!=config['job_sha256']:raise ValueError('Registered MCP job hash differs from approved configuration')
    expected={'mode':'workflow','task_id':task,'version':version,'contract_sha256':digest(contract)}
    if job['authorization']!=expected:raise ValueError('MCP job authorization differs from task contract version')
    inputs={i['id']:i['sha256'] for i in contract['inputs']}
    actual={i.get('input_id'):i['sha256'] for i in job['inputs']}
    if inputs!=actual or len(job['inputs'])!=len(inputs):raise ValueError('MCP job inputs differ from contract inputs')
    return job


class McpCodeExecutor:
    replay_safe=False
    def __init__(self,workflow):self.workflow=workflow
    def execute(self,request):return self._invoke(request,False)
    def recover(self,request):return self._invoke(request,True)
    def _invoke(self,request,recovery):
        job=checked_job(request.task_id,request.version,request.contract,request.config)
        tool='code_execution_status' if recovery else 'code_execute'
        args={'run_id' if recovery else 'job_id':job['job_id']}
        trace_id,envelope=trace_call(self.workflow,request.task_id,request.version,'code-executor',tool,args,request.operation_key)
        if envelope['status']!='ok':
            error=envelope['error']
            raise McpExecutionError(error['code'],'authorization' if error['code']=='authorization_error' else 'infrastructure','MCP execution tool failed: '+error['code']+'; inspect status before retry')
        result=envelope['data']
        if result.get('job_sha256')!=job['job_sha256'] or result.get('run_id')!=job['run_id']:
            raise McpExecutionError('receipt_mismatch','infrastructure','MCP execution receipt binding mismatch')
        if result.get('status')=='running':raise McpExecutionError('execution_pending','infrastructure','Execution is still running; resume queries status only')
        if result.get('authorization')!=job['authorization'] or result.get('code_sha256')!=job['code_sha256']:
            raise McpExecutionError('receipt_mismatch','infrastructure','MCP execution authorization or code identity mismatch')
        if result['status']!='succeeded':raise McpExecutionError(result['status'],'code','Registered solver failed: '+result['status']+'; new code requires a new approved model version')
        if not result.get('artifacts'):raise McpExecutionError('missing_artifacts','code','Solver produced no archived output artifacts')
        if result.get('cleanup',{}).get('removed') is not True:
            raise McpExecutionError('cleanup_pending','infrastructure','Execution container cleanup not confirmed')
        artifacts=[];root=executor_root()
        for item in result['artifacts']:
            path=(root/item['path']).resolve()
            if not path.is_relative_to(root/'runs'/job['run_id']/'artifacts'):
                raise McpExecutionError('unsafe_artifact','infrastructure','MCP output path differs from registered run')
            artifacts.append({**item,'path':str(path)})
        # Existing dispatcher validates hashes and snapshots all output bytes before publication.
        return receipt(request,artifacts,mode='solver',run_id=result['run_id'],
            review={'status':'unknown','mode':'solver','kind':'mcp_execution_review','mathematical_review':'not_performed',
                    'user_confirmation':'pending','note':'Docker execution succeeded; model and numerical correctness are not proved.'},
            details={'mcp_trace_id':trace_id,'mcp_call_id':envelope['call_id'],'job_sha256':job['job_sha256'],
                     'code_sha256':job['code_sha256'],'new_code_executed':not recovery,'recovered_via_status':recovery,
                     'image_id':result.get('image_id'),'restrictions':result.get('restrictions'),
                     'cleanup':result['cleanup'],'not_user_approval':True})
