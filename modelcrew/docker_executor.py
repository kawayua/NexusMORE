"""Immutable local jobs, Docker-only execution, bounded outputs and restart-safe receipts."""
import argparse,base64,hashlib,json,os,re,subprocess,threading,time,uuid
from contextlib import contextmanager
import portalocker
from pathlib import Path,PurePosixPath
from pydantic import BaseModel,ConfigDict,Field
from .config import ROOT
from .contracts import digest

RUNNER=ROOT/'execution/sandbox_runner.py'
DEFAULT_ROOT=ROOT/'stage-c/execution'
ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')

class ExecutorError(RuntimeError):
    def __init__(self,code,message):super().__init__(message);self.code=code

class Limits(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    timeout_s:int=Field(default=10,ge=1,le=180)
    memory_mb:int=Field(default=256,ge=64,le=1024)
    max_file_bytes:int=Field(default=1024*1024,ge=1024,le=2*1024*1024)
    max_total_bytes:int=Field(default=4*1024*1024,ge=1024,le=4*1024*1024)
    max_log_bytes:int=Field(default=256*1024,ge=1024,le=256*1024)
    max_files:int=Field(default=16,ge=1,le=32)

def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ExecutorError('invalid_request','Invalid job/run identifier')
    return value
def relative_name(value):
    if not isinstance(value,str) or not value or len(value)>200 or '\\' in value or ':' in value or '\x00' in value:raise ExecutorError('invalid_request','Invalid artifact path')
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in ('','..','.') for x in value.split('/')):raise ExecutorError('invalid_request','Artifact path escapes output directory')
    return p

def register_job(root,job_id,code_path,inputs,authorization,limits=None):
    root=Path(root).resolve();job_id=identifier(job_id);limits=Limits.model_validate(limits or {}).model_dump()
    if Path(code_path).stat().st_size>256*1024:raise ExecutorError('invalid_request','Code exceeds byte limit')
    code=Path(code_path).read_bytes()
    if not code or len(code)>256*1024:raise ExecutorError('invalid_request','Code requires 1 to 262144 bytes')
    prepared=[];names=set();total=0
    for item in inputs:
        name=str(relative_name(item['name']))
        if name in names or len(prepared)>=32:raise ExecutorError('invalid_request','Duplicate or excessive input files')
        names.add(name);source=Path(item['path'])
        if source.is_symlink() or source.is_junction() or not source.is_file():raise ExecutorError('invalid_request','Input must be a regular file')
        if source.stat().st_size>8*1024*1024:raise ExecutorError('invalid_request','Input exceeds byte limit')
        data=source.read_bytes();total+=len(data)
        if sha(data)!=item['sha256'] or len(data)>8*1024*1024 or total>16*1024*1024:raise ExecutorError('invalid_request','Input hash or size invalid')
        prepared.append((name,data,item.get('input_id')))
    if authorization.get('mode') not in ('verification','workflow'):raise ExecutorError('authorization_error','Unknown authorization mode')
    job=root/'jobs'/job_id;job.mkdir(parents=True,exist_ok=False)
    (job/'solver.py').write_bytes(code);runner=RUNNER.read_bytes();(job/'runner.py').write_bytes(runner)
    for name,data,input_id in prepared:
        p=job/'input'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    (job/'input').mkdir(exist_ok=True)
    value={'job_version':'1.0.0','job_id':job_id,'run_id':job_id,'code_sha256':sha(code),'runner_sha256':sha(runner),
        'inputs':[{'name':name,'sha256':sha(data),'size_bytes':len(data),'input_id':input_id} for name,data,input_id in prepared],
        'authorization':authorization,'limits':limits}
    value['job_sha256']=digest(value);atomic(job/'job.json',value)
    return value

class DockerExecutor:
    def __init__(self,root=DEFAULT_ROOT,*,image='modelcrew-reference:py311',allow_test_jobs=False):
        self.root=Path(root).resolve();self.image=image;self.allow_test_jobs=allow_test_jobs;self.lock=threading.Lock()
    @contextmanager
    def guard(self,job_id):
        path=self.root/'locks'/(identifier(job_id)+'.lock')
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(self.root/'locks'):raise ExecutorError('invalid_request','Invalid operation lock path')
        try:
            with portalocker.Lock(str(path),mode='a',timeout=1):yield
        except portalocker.exceptions.LockException as exc:raise ExecutorError('execution_busy','Run operation is in progress; query status later') from exc
    def verify_artifacts(self,result):
        for item in result.get('artifacts',[]):
            path=self.root/item['path']
            if not path.resolve().is_relative_to(self.root/'runs') or path.is_symlink() or path.is_junction() or not path.is_file() or path.stat().st_size!=item.get('size_bytes') or sha(path.read_bytes())!=item['sha256']:raise ExecutorError('infrastructure_error','Archived artifact missing or changed')
    def docker(self,*args,timeout=15,allow_missing=False):
        try:r=subprocess.run(['docker',*args],capture_output=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as exc:raise ExecutorError('infrastructure_error','Docker command unavailable or timed out') from exc
        if r.returncode and not allow_missing:raise ExecutorError('infrastructure_error','Docker command failed')
        return r
    def job(self,job_id):
        job_id=identifier(job_id);folder=self.root/'jobs'/job_id
        if not folder.resolve().is_relative_to(self.root/'jobs') or folder.is_symlink() or folder.is_junction():raise ExecutorError('invalid_request','Job path invalid')
        if not (folder/'job.json').is_file():raise ExecutorError('not_found','Registered job not found')
        value=read(folder/'job.json');saved=value.pop('job_sha256',None)
        if digest(value)!=saved:raise ExecutorError('invalid_request','Job manifest changed')
        value['job_sha256']=saved
        if value['job_id']!=job_id or value['run_id']!=job_id:raise ExecutorError('invalid_request','Job identity mismatch')
        Limits.model_validate(value['limits'])
        for name,expected in [('solver.py',value['code_sha256']),('runner.py',value['runner_sha256'])]+[('input/'+i['name'],i['sha256']) for i in value['inputs']]:
            relative_name(name);p=folder/name
            if not p.resolve().is_relative_to(folder.resolve()) or p.is_symlink() or p.is_junction() or not p.is_file() or sha(p.read_bytes())!=expected:raise ExecutorError('invalid_request','Job file missing or changed')
        return folder,value
    def authorize(self,job):
        auth=job['authorization']
        if auth['mode']=='verification':
            if not self.allow_test_jobs:raise ExecutorError('authorization_error','Verification jobs disabled on this server')
            return
        if auth['mode']!='workflow':raise ExecutorError('authorization_error','Unsupported authorization')
        from .workflow import Workflow
        try:
            with Workflow() as w:
                # One committed MVCC snapshot: do not acquire the caller's task lock.
                # C5 holds that lock while waiting on this independent MCP process.
                row=w.db.execute('SELECT t.model_approved,t.current_version,t.executor_key,t.executor_config,c.sha256,c.content FROM mc_tasks t JOIN mc_contracts c ON c.task_id=t.id AND c.version=%s WHERE t.id=%s',
                                 (auth['version'],auth['task_id'])).fetchone()
                if not row or not row['model_approved'] or row['current_version']!=auth['version'] or row['sha256']!=auth['contract_sha256']:
                    raise ExecutorError('authorization_error','Durable current model approval required')
                if row['executor_key']=='mcp-code-executor' and row['executor_config']!={'job_id':job['job_id'],'job_sha256':job['job_sha256']}:
                    raise ExecutorError('authorization_error','Job is not the approved execution configuration')
                expected={i['id']:i['sha256'] for i in row['content']['inputs']}
                actual={i.get('input_id'):i['sha256'] for i in job['inputs']}
                if actual!=expected or len(job['inputs'])!=len(expected):raise ExecutorError('authorization_error','Execution input snapshot differs from approved contract')
        except ExecutorError:raise
        except Exception as exc:raise ExecutorError('infrastructure_error','Approval database unavailable') from exc
    def inspect(self,name,job):
        r=self.docker('container','inspect',name,allow_missing=True)
        if r.returncode:
            # Verify daemon health before classifying a container as absent.
            self.docker('version','--format','{{.Server.Version}}')
            return None
        value=json.loads(r.stdout)[0]
        labels=value['Config'].get('Labels') or {}
        if labels.get('com.modelcrew.executor.job')!=job['job_sha256']:raise ExecutorError('infrastructure_error','Container identity mismatch; refusing cleanup')
        return value
    def execute(self,job_id):
        self.job(job_id)
        with self.lock,self.guard(job_id):
            folder,job=self.job(job_id);run=self.root/'runs'/job_id
            if not run.resolve().is_relative_to(self.root/'runs') or run.is_symlink() or run.is_junction():raise ExecutorError('invalid_request','Invalid run path')
            if run.exists():return self._recover(run,job)
            self.authorize(job)
            image=json.loads(self.docker('image','inspect',self.image).stdout)[0]['Id']
            try:run.mkdir(parents=True,exist_ok=False)
            except FileExistsError:return self._recover(run,job)
            name='mc-exec-'+digest({'root':str(self.root),'run_id':job_id})[:24]
            claim={'job_sha256':job['job_sha256'],'container_name':name,'image_id':image,'started_at':time.time()}
            atomic(run/'claim.json',claim)
            limits=job['limits'];memory=str(limits['memory_mb'])+'m'
            args=['create','--name',name,'--label','com.modelcrew.executor.job='+job['job_sha256'],'--network','none',
                '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','32','--cpus','1',
                '--memory',memory,'--memory-swap',memory,'--user','10001:10001','--log-driver','local','--log-opt','max-size=16m','--log-opt','max-file=1','--log-opt','compress=false',
                '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16m,uid=10001,gid=10001,mode=0700',
                '--tmpfs','/work/output:rw,noexec,nosuid,nodev,size=32m,uid=10001,gid=10001,mode=0700',
                '--mount',f'type=bind,source={folder},target=/work/job,readonly','--workdir','/work/output',
                '--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=1','--env','MODELCREW_INPUT_DIR=/work/job/input',
                '--env','MODELCREW_OUTPUT_DIR=/work/output','--entrypoint','python',image,'-I','-B','/work/job/runner.py']
            try:
                self.docker(*args);self.authorize(job);self.docker('start',name)
                while True:
                    info=self.inspect(name,job)
                    if info is None:raise ExecutorError('outcome_unknown','Execution container disappeared; do not redispatch')
                    if not info['State']['Running']:return self._finish(run,job,info)
                    if time.time()-claim['started_at']>limits['timeout_s']+15:
                        self.docker('kill',name,allow_missing=True)
                        info=self.inspect(name,job)
                        return self._finish(run,job,info,forced_status='timeout')
                    time.sleep(.1)
            except ExecutorError as exc:
                # If Docker confirms it never started, clean up and preserve that failure.
                info=self.inspect(name,job)
                if info is not None and info['State']['Status']=='created' and (info['State'].get('Error') or exc.code=='authorization_error'):
                    self.docker('rm','-f',name)
                    atomic(run/'dispatch-error.json',{'code':exc.code,'message':'Container was not started; dispatch failure retained','cleanup_removed':True})
                # An ambiguous start remains query-only; never blindly dispatch again.
                raise
    def status(self,run_id):
        self.job(run_id)
        with self.lock,self.guard(run_id):
            _,job=self.job(run_id);run=self.root/'runs'/identifier(run_id)
            if not run.resolve().is_relative_to(self.root/'runs') or run.is_symlink() or run.is_junction():raise ExecutorError('invalid_request','Invalid run path')
            if not run.exists():raise ExecutorError('not_found','Execution has not been dispatched')
            return self._recover(run,job)
    def _recover(self,run,job):
        if (run/'result.json').exists():
            result=read(run/'result.json')
            if result.get('job_sha256')!=job['job_sha256']:raise ExecutorError('invalid_request','Receipt belongs to different job bytes')
            self.verify_artifacts(result)
            return result
        if (run/'dispatch-error.json').exists():
            error=read(run/'dispatch-error.json');raise ExecutorError(error['code'],error['message'])
        if not (run/'claim.json').exists():raise ExecutorError('outcome_unknown','Incomplete dispatch claim; manual recovery required')
        claim=read(run/'claim.json')
        if claim['job_sha256']!=job['job_sha256']:raise ExecutorError('invalid_request','Run belongs to different job bytes')
        if (run/'pending-result.json').exists():return self._publish(run,job,read(run/'pending-result.json'))
        info=self.inspect(claim['container_name'],job)
        if info is None:raise ExecutorError('outcome_unknown','Execution outcome unknown; no automatic redispatch')
        if info['State']['Running']:
            # The original monitor may have died. Recovery owns the same wall deadline.
            if time.time()-claim['started_at']>job['limits']['timeout_s']+15:
                self.docker('kill',claim['container_name'])
                return self._finish(run,job,self.inspect(claim['container_name'],job),forced_status='timeout')
            return {'run_id':job['run_id'],'job_sha256':job['job_sha256'],'status':'running','artifacts':[]}
        if info['State']['Status']=='created':
            if info['State'].get('Error'):
                self.docker('rm','-f',claim['container_name'])
                atomic(run/'dispatch-error.json',{'code':'infrastructure_error','message':'Container was not started; dispatch failure retained','cleanup_removed':True})
                raise ExecutorError('infrastructure_error','Container did not start; cleaned up without retry')
            raise ExecutorError('outcome_unknown','Container created but start outcome unknown; no automatic redispatch')
        return self._finish(run,job,info)
    def _finish(self,run,job,info,forced_status=None):
        if info is None:raise ExecutorError('outcome_unknown','Missing execution container')
        claim=read(run/'claim.json');raw=self.docker('logs',claim['container_name'],allow_missing=False).stdout
        limits=job['limits'];packet={};status=forced_status or 'code_error'
        if len(raw)<=8*1024*1024:
            try:packet=json.loads(raw)
            except (ValueError,UnicodeDecodeError,RecursionError):pass
        if info['State'].get('OOMKilled'):status='memory_limit'
        elif forced_status:pass
        elif len(raw)>8*1024*1024:status='output_limit'
        elif isinstance(packet,dict) and packet.get('packet_version')=='1.0.0' and packet.get('status') in ['succeeded','code_error','timeout','memory_limit','output_limit','unsafe_artifact']:
            status=packet['status']
            if status=='succeeded' and info['State']['ExitCode']!=0:status='code_error'
        if not isinstance(packet,dict):packet={}
        stdout=str(packet.get('stdout','')).encode('utf-8')[:limits['max_log_bytes']].decode('utf-8',errors='ignore');stderr=str(packet.get('stderr','')).encode('utf-8')[:limits['max_log_bytes']].decode('utf-8',errors='ignore')
        artifacts=[]
        if status=='succeeded':
            try:artifacts=self._archive(run,packet.get('artifacts',[]),limits)
            except (ExecutorError,ValueError,TypeError,KeyError,OSError):status='unsafe_artifact';artifacts=[]
        atomic(run/'stdout.json',{'text':stdout});atomic(run/'stderr.json',{'text':stderr})
        host=info['HostConfig'];restriction={'network':host['NetworkMode'],'read_only':host['ReadonlyRootfs'],
            'cap_drop':host.get('CapDrop'),'security_opt':host.get('SecurityOpt'),'pids_limit':host.get('PidsLimit'),
            'memory_bytes':host.get('Memory'),'memory_swap_bytes':host.get('MemorySwap'),'nano_cpus':host.get('NanoCpus'),
            'user':info['Config']['User'],'mounts':[{'destination':m['Destination'],'writable':m['RW'],'type':m['Type']} for m in info['Mounts']],
            'tmpfs':host.get('Tmpfs'),'log_config':host.get('LogConfig')}
        result={'receipt_version':'1.0.0','run_id':job['run_id'],'job_sha256':job['job_sha256'],'code_sha256':job['code_sha256'],
            'authorization':job['authorization'],'image_id':claim['image_id'],'status':status,'failure_domain':None if status=='succeeded' else 'code',
            'exit_code':packet.get('exit_code') if isinstance(packet.get('exit_code'),int) else info['State']['ExitCode'],
            'container_exit_code':info['State']['ExitCode'],'stdout':stdout,'stderr':stderr,'error_kind':packet.get('error_kind'),
            'elapsed_s':round(time.time()-claim['started_at'],6),'artifacts':artifacts,'limits':limits,'restrictions':restriction,
            'oom_killed':info['State'].get('OOMKilled',False),'oom_kill_observed':packet.get('oom_kill_observed',False),
            'mathematical_review':'not_performed','cleanup':{'removed':False}}
        atomic(run/'pending-result.json',result)
        return self._publish(run,job,result)
    def _archive(self,run,items,limits):
        if not isinstance(items,list) or len(items)>limits['max_files']:raise ValueError('Artifact count invalid')
        decoded=[];total=0;names=set()
        for item in items:
            name=str(relative_name(item['name']))
            if name in names:raise ValueError('Duplicate output path')
            names.add(name);data=base64.b64decode(item['base64'],validate=True);total+=len(data)
            if len(data)!=item['size_bytes'] or len(data)>limits['max_file_bytes'] or total>limits['max_total_bytes']:raise ValueError('Artifact size invalid')
            decoded.append((name,data))
        artifacts=[]
        archive=run/'artifacts'
        if archive.is_symlink() or archive.is_junction():raise ValueError('Unsafe archive root')
        for name,data in decoded:
            path=archive/name
            if not path.resolve().is_relative_to(archive.absolute()):raise ValueError('Unsafe archive parent')
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.resolve().is_relative_to((run/'artifacts').resolve()) or path.is_symlink() or path.is_junction():raise ValueError('Unsafe archive path')
            if path.exists():
                if sha(path.read_bytes())!=sha(data):raise ValueError('Existing archive differs')
            else:
                with path.open('xb') as stream:stream.write(data)
            artifacts.append({'name':name,'path':path.relative_to(self.root).as_posix(),'sha256':sha(data),'size_bytes':len(data),'role':'execution_output'})
        return artifacts
    def _publish(self,run,job,result):
        if any(result.get(key)!=value for key,value in {'job_sha256':job['job_sha256'],'run_id':job['run_id'],'code_sha256':job['code_sha256'],'authorization':job['authorization']}.items()):
            raise ExecutorError('infrastructure_error','Pending receipt differs from registered job')
        self.verify_artifacts(result)
        claim=read(run/'claim.json');info=self.inspect(claim['container_name'],job)
        if info is not None:self.docker('rm','-f',claim['container_name'])
        if self.inspect(claim['container_name'],job) is not None:raise ExecutorError('infrastructure_error','Execution cleanup incomplete')
        result['cleanup']={'removed':True};atomic(run/'result.json',result)
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('register');c.add_argument('job_id');c.add_argument('--code',type=Path,required=True);c.add_argument('--inputs',type=Path)
    c.add_argument('--verification',action='store_true');c.add_argument('--task');c.add_argument('--version',type=int);c.add_argument('--contract-sha256');c.add_argument('--limits',type=Path)
    a=p.parse_args()
    if a.verification:auth={'mode':'verification','actor':'TEST_SIMULATED_USER','not_independent_modeling':True}
    else:
        if not a.task or not a.version or not a.contract_sha256:p.error('Workflow jobs require task, version and contract-sha256')
        auth={'mode':'workflow','task_id':a.task,'version':a.version,'contract_sha256':a.contract_sha256}
    value=register_job(a.root,a.job_id,a.code,read(a.inputs) if a.inputs else [],auth,read(a.limits) if a.limits else None)
    print(json.dumps(value,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
