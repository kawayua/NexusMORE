"""Independent code-executor MCP; only host-registered jobs can be dispatched."""
import argparse,json,os,threading,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Literal
import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .config import ROOT
from .docker_executor import DEFAULT_ROOT,DockerExecutor,ExecutorError

class ExecuteRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    job_id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
class StatusRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    run_id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
class Artifact(BaseModel):
    name:str
    path:str
    sha256:str
    size_bytes:int=Field(ge=0)
    role:Literal['execution_output']
class ExecutionResult(BaseModel):
    model_config=ConfigDict(extra='allow')
    run_id:str
    job_sha256:str
    status:Literal['running','succeeded','code_error','timeout','memory_limit','output_limit','unsafe_artifact']
    artifacts:list[Artifact]

class Failure(BaseModel):
    code:str
    message:str
class Envelope(BaseModel):
    schema_version:Literal['1.0.0']='1.0.0'
    tool:str
    call_id:str
    status:Literal['ok','error']
    elapsed_ms:float
    data:ExecutionResult|None=None
    error:Failure|None=None

def definitions():
    return [types.Tool(name=name,description=description,inputSchema=schema.model_json_schema(),outputSchema=Envelope.model_json_schema(),
        annotations=types.ToolAnnotations(readOnlyHint=readonly,destructiveHint=False,idempotentHint=True,openWorldHint=False))
        for name,description,schema,readonly in [
            ('code_execute','Execute an immutable host-registered job in restricted Docker. No code, file paths, image or approval flags accepted from the tool caller.',ExecuteRequest,False),
            ('code_execution_status','Recover/read a known run without launching or retrying code. Infrastructure errors are distinct from solver failures.',StatusRequest,True)]]

class ExecutionTools:
    def __init__(self,executor,*,log_path):self.executor=executor;self.log_path=Path(log_path);self.lock=threading.Lock()
    def audit(self,value):
        self.log_path.parent.mkdir(parents=True,exist_ok=True)
        with self.log_path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),**value},ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
    def invoke(self,name,arguments):
        started=time.monotonic();call_id=str(uuid.uuid4());data=None;error=None;request=None
        with self.lock:
            try:
                schema={'code_execute':ExecuteRequest,'code_execution_status':StatusRequest}.get(name)
                if schema is None:raise ExecutorError('unknown_tool','Unknown tool')
                request=schema.model_validate(arguments)
                self.audit({'call_id':call_id,'tool':name,'phase':'started','parameters':request.model_dump()})
                value=self.executor.execute(request.job_id) if name=='code_execute' else self.executor.status(request.run_id)
                try:data=ExecutionResult.model_validate(value).model_dump(mode='json')
                except ValidationError as exc:raise ExecutorError('infrastructure_error','Invalid execution receipt') from exc
            except ValidationError:error=Failure(code='invalid_request',message='Arguments do not match tool schema')
            except ExecutorError as exc:error=Failure(code=exc.code,message=str(exc))
            except OSError:error=Failure(code='audit_or_storage_unavailable',message='Audit or execution storage unavailable; query run status before retry')
            except Exception:error=Failure(code='internal_error',message='Executor failed; query run status before retry')
            elapsed=round((time.monotonic()-started)*1000,3)
            envelope=Envelope(tool=name,call_id=call_id,status='error' if error else 'ok',elapsed_ms=elapsed,data=data if error is None else None,error=error)
            try:self.audit({'call_id':call_id,'tool':name,'phase':'completed','status':envelope.status,'error_code':error.code if error else None,
                'elapsed_ms':elapsed,'run_id':data.get('run_id') if data else None,'execution_status':data.get('status') if data else None,
                'job_sha256':data.get('job_sha256') if data else None,'artifact_hashes':[a['sha256'] for a in data.get('artifacts',[])] if data else []})
            except OSError:envelope=Envelope(tool=name,call_id=call_id,status='error',elapsed_ms=elapsed,error=Failure(code='audit_or_storage_unavailable',message='Audit unavailable; query run status before retry'))
            payload=envelope.model_dump(mode='json')
            return types.CallToolResult(isError=envelope.status=='error',structuredContent=payload,content=[types.TextContent(type='text',text=json.dumps(payload,ensure_ascii=False))])

def create_server(adapter):
    server=Server('modelcrew-code-executor',version='0.1.0',instructions='Docker-only registered-job execution. Tool errors are infrastructure/authorization failures. Solver errors are returned as structured execution outcomes. Never redispatch an unknown outcome.')
    @server.list_tools()
    async def list_tools():return definitions()
    @server.call_tool(validate_input=False)
    async def call_tool(name,arguments):return await anyio.to_thread.run_sync(adapter.invoke,name,arguments)
    return server

async def serve(adapter):
    server=create_server(adapter)
    async with stdio_server() as (read,write):await server.run(read,write,server.create_initialization_options())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=DEFAULT_ROOT);parser.add_argument('--image',default='modelcrew-reference:py311')
    parser.add_argument('--allow-test-jobs',action='store_true');parser.add_argument('--log',type=Path)
    args=parser.parse_args();log=args.log or ROOT/'stage-c/runs/mcp'/('code-executor-'+uuid.uuid4().hex+'.jsonl')
    anyio.run(serve,ExecutionTools(DockerExecutor(args.root,image=args.image,allow_test_jobs=args.allow_test_jobs),log_path=log))
if __name__=='__main__':main()
