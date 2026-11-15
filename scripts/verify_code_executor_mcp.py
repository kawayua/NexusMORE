"""Real MCP -> Docker verification using fixed test programs, not competition solving."""
from modelcrew.project_assets import asset_path
import argparse,json,sys,time
from contextlib import asynccontextmanager
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
from modelcrew.config import ROOT
from modelcrew.docker_executor import register_job,DockerExecutor,ExecutorError,sha

@asynccontextmanager
async def session(root,folder,name,*,allow=True,image=None):
    args=['-m','modelcrew.code_executor_mcp','--root',str(root),'--log',str(folder/(name+'.jsonl'))]
    if allow:args.append('--allow-test-jobs')
    if image:args+=['--image',image]
    params=StdioServerParameters(command=sys.executable,args=args,cwd=str(ROOT),env={'PYTHONIOENCODING':'utf-8'})
    with (folder/(name+'-stderr.log')).open('w',encoding='utf-8') as stderr:
        async with stdio_client(params,errlog=stderr) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=60)) as client:
                await client.initialize();yield client

async def main(output):
    folder=output.resolve();folder.mkdir(exist_ok=False,parents=True);root=folder/'executor';source=folder/'programs';source.mkdir()
    data=source/'input.json';data.write_text('{"values":[1,2,3]}',encoding='utf-8')
    normal='''from pathlib import Path
import json,os,socket,uuid
assert os.getuid()==10001
assert not Path('/var/run/docker.sock').exists()
checks={}
for key,path in [('input_readonly','/work/job/input/input.json'),('root_readonly','/rootfs-write-test')]:
    try:Path(path).write_text('forbidden');checks[key]=False
    except OSError:checks[key]=True
s=socket.socket();s.settimeout(.3)
checks['network_disabled']=s.connect_ex(('1.1.1.1',443))!=0;s.close()
checks['pids_limit']=Path('/sys/fs/cgroup/pids.max').read_text().strip()=='32'
checks['cpu_limit']=Path('/sys/fs/cgroup/cpu.max').read_text().split()[0]=='100000'
checks['no_new_privileges']='NoNewPrivs:\\t1' in Path('/proc/self/status').read_text()
assert all(checks.values()),checks
values=json.loads(Path('/work/job/input/input.json').read_text())['values']
Path('result.json').write_text(json.dumps({'sum_of_squares':sum(x*x for x in values),'checks':checks,'nonce':uuid.uuid4().hex}))
print('fixed-verification-complete')
'''
    cases=[('normal',normal,{},'succeeded'),
        ('syntax','def invalid(:\n pass',{},'code_error'),
        ('dependency','import modelcrew_dependency_deliberately_absent',{},'code_error'),
        ('timeout','while True: pass',{'timeout_s':1},'timeout'),
        ('memory','a=bytearray(512*1024*1024); print(len(a))',{'memory_mb':64},'memory_limit'),
        ('single-output',"from pathlib import Path; Path('big').write_bytes(b'x'*(2*1024*1024))",{},'output_limit'),
        ('total-output',"from pathlib import Path\nfor i in range(6):Path(str(i)).write_bytes(b'x'*800000)",{},'output_limit'),
        ('stdout-output',"print('x'*(1024*1024))",{},'output_limit'),
        ('symlink',"import os; os.symlink('/etc/passwd','leak')",{},'unsafe_artifact'),
        ('directory-link',"import os; os.symlink('/work/job/input','linked-input',target_is_directory=True)",{},'unsafe_artifact'),
        ('file-count',"from pathlib import Path\nfor i in range(40):Path(str(i)).write_text('x')",{},'output_limit')]
    auth={'mode':'verification','actor':'TEST_SIMULATED_USER','not_independent_modeling':True}
    for name,code,limits,expected in cases:
        p=source/(name+'.py');p.write_text(code,encoding='utf-8')
        inputs=[{'name':'input.json','path':str(data),'sha256':sha(data.read_bytes())}] if name=='normal' else []
        register_job(root,'test-'+name,p,inputs,auth,limits)
    checks=[];responses=[]
    async with session(root,folder,'main') as client:
        tools=await client.list_tools();checks.append({'id':'tool_discovery','passed':{t.name for t in tools.tools}=={'code_execute','code_execution_status'}})
        for name,code,limits,expected in cases:
            response=await client.call_tool('code_execute',{'job_id':'test-'+name});responses.append(response.model_dump(mode='json'))
            result=response.structuredContent.get('data') or {}
            checks.append({'id':name,'passed':not response.isError and result.get('status')==expected and result.get('cleanup',{}).get('removed') is True,
                'expected':expected,'observed':result.get('status'),'error':response.structuredContent.get('error')})
            print(json.dumps(checks[-1]),flush=True)
        first=responses[0]['structuredContent']['data']
        repeated=await client.call_tool('code_execute',{'job_id':'test-normal'});responses.append(repeated.model_dump(mode='json'))
        checks.append({'id':'duplicate_execution_reuses_identical_receipt','passed':not repeated.isError and repeated.structuredContent['data']==first})
        artifact=first.get('artifacts',[{}])[0]
        if artifact:
            saved=root/artifact['path'];body=json.loads(saved.read_text())
            ok=sha(saved.read_bytes())==artifact['sha256'] and body['sum_of_squares']==14 and all(body['checks'].values())
        else:ok=False
        checks.append({'id':'archive_hash_and_isolation_checks','passed':ok})
        for name,args,expected in [('code_execute',{'job_id':'../outside'},'invalid_request'),('code_execute',{'job_id':'test-normal','code':'pass'},'invalid_request'),('code_execute',{'job_id':'missing-job'},'not_found'),('unknown',{},'unknown_tool')]:
            response=await client.call_tool(name,args);responses.append(response.model_dump(mode='json'))
            checks.append({'id':'reject_'+expected,'passed':response.isError and response.structuredContent['error']['code']==expected})
    async with session(root,folder,'restart') as client:
        response=await client.call_tool('code_execution_status',{'run_id':'test-normal'});responses.append(response.model_dump(mode='json'))
        checks.append({'id':'new_server_recovers_same_receipt','passed':not response.isError and response.structuredContent['data']==first})
    async with session(root,folder,'default-denial',allow=False) as client:
        # Use a fresh job because completed historical receipts are intentionally readable.
        p=source/'denied.py';p.write_text('print(1)')
        register_job(root,'test-denied',p,[],auth)
        response=await client.call_tool('code_execute',{'job_id':'test-denied'});responses.append(response.model_dump(mode='json'))
        checks.append({'id':'test_job_disabled_by_default','passed':response.isError and response.structuredContent['error']['code']=='authorization_error' and not (root/'runs/test-denied').exists()})
    async with session(root,folder,'infrastructure',image='modelcrew-deliberately-missing:verification') as client:
        response=await client.call_tool('code_execute',{'job_id':'test-denied'});responses.append(response.model_dump(mode='json'))
        checks.append({'id':'missing_image_is_tool_infrastructure_error','passed':response.isError and response.structuredContent['error']['code']=='infrastructure_error'})
    try:register_job(root,'test-illegal-input',source/'denied.py',[{'name':'../secret','path':str(data),'sha256':sha(data.read_bytes())}],auth);blocked=False
    except ExecutorError:blocked=True
    checks.append({'id':'illegal_input_path_rejected_before_dispatch','passed':blocked})
    # A monitor exception after start simulates a lost dispatch response. A fresh engine recovers without restart.
    p=source/'recover.py';p.write_text("import time\nfrom pathlib import Path\ntime.sleep(.5)\nPath('recover.json').write_text('{}')\n")
    register_job(root,'test-recover',p,[],auth)
    class Interrupted(DockerExecutor):
        injected=False
        def inspect(self,name,job):
            if not self.injected:self.injected=True;raise ExecutorError('infrastructure_error','TEST injected monitor interruption')
            return super().inspect(name,job)
    try:Interrupted(root,allow_test_jobs=True).execute('test-recover')
    except ExecutorError:pass
    engine=DockerExecutor(root,allow_test_jobs=True)
    deadline=time.monotonic()+10
    while True:
        recovered=engine.status('test-recover')
        if recovered['status']!='running' or time.monotonic()>deadline:break
        await anyio.sleep(.1)
    checks.append({'id':'recover_after_monitor_interruption_no_redispatch','passed':recovered['status']=='succeeded' and recovered['cleanup']['removed']})
    audit=[]
    for path in folder.glob('*.jsonl'):audit.extend(json.loads(line) for line in path.read_text(encoding='utf-8').splitlines())
    completed=[v for v in audit if v['phase']=='completed']
    checks.append({'id':'all_mcp_responses_audited','passed':len(completed)==len(responses) and {c['call_id'] for c in completed}=={r['structuredContent']['call_id'] for r in responses}})
    report={'date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'status':'passed' if all(c['passed'] for c in checks) else 'failed',
        'transport':'stdio','separate_server_process':True,'real_docker':True,'checks':checks,'responses':responses,
        'verification_code_executions':len(cases)+1,'new_llm_calls':0,'new_formal_problem_solves':0,'new_real_user_approvals':0,
        'independent_modeling_trial':False,'scope':'Fixed test programs and measured containment only; not proof of absolute sandbox safety or mathematical correctness'}
    (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(checks),'mcp_calls':len(responses),'failed':[c for c in checks if not c['passed']]}))
    if report['status']!='passed':raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    anyio.run(main,p.parse_args().output)
