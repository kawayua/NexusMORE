"""Run a reviewed solver in a restricted Docker container; no host fallback."""
from modelcrew.project_assets import asset_path
from pathlib import Path
import argparse,json,hashlib,subprocess,shutil,time,uuid
ROOT=Path(__file__).resolve().parents[1];CASE=asset_path(ROOT,'stage-a/2024-A-problem-1')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('run_dir',type=Path);ap.add_argument('--image',default='modelcrew-reference:py313');ap.add_argument('--keep-container',action='store_true');a=ap.parse_args()
 run=a.run_dir.resolve()
 if run.parent not in [(CASE/'runs').resolve(),(asset_path(ROOT,'stage-b/runs')).resolve()]:raise ValueError('Run outside intended workspace')
 script=run/'generated_solver.py';review=json.loads((run/'review.json').read_text(encoding='utf-8'))
 sha=hashlib.sha256(script.read_bytes()).hexdigest()
 if review.get('code_sha256')!=sha or review.get('security_review',{}).get('passed') is not True or review.get('math_review',{}).get('passed') is not True:
  raise ValueError('Matching manual math and security approval required')
 if run.parent==(asset_path(ROOT,'stage-b/runs')).resolve():
  import sys
  sys.path.insert(0,str(ROOT))
  from modelcrew.workflow import Workflow
  from modelcrew.contracts import digest
  contract=json.loads((run/'contract.json').read_text(encoding='utf-8'))
  with Workflow() as w:
   current=w.inspect('dragon-q1')
   if not current['task']['model_approved'] or current['task']['current_version']!=2 or current['contract']['sha256']!=digest(contract) or review.get('contract_sha256')!=digest(contract):raise ValueError('Approved contract binding mismatch')
 subprocess.run(['docker','version','--format','{{.Server.Version}}'],check=True,capture_output=True,timeout=15)
 subprocess.run(['docker','image','inspect',a.image],check=True,capture_output=True,timeout=15)
 inputs=run/'input';output=run/'output';inputs.mkdir(exist_ok=True);output.mkdir(exist_ok=False)
 manifest=json.loads((CASE/'input-manifest.json').read_text(encoding='utf-8'))
 src=next(x for x in manifest['files'] if x['role']=='required_output_template')
 template=Path(src['path'])
 if hashlib.sha256(template.read_bytes()).hexdigest().lower()!=src['sha256'].lower():raise ValueError('Template changed')
 shutil.copyfile(template,inputs/'result1.xlsx')
 if (run/'contract.json').exists():shutil.copyfile(run/'contract.json',inputs/'contract.json')
 name='modelcrew-'+uuid.uuid4().hex[:16]
 cmd=['docker','run']+([] if a.keep_container else ['--rm'])+['--name',name,'--label','com.modelcrew.role=solver','--label',f'com.modelcrew.run={run.name}','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64','--cpus','1','--memory','1g','--memory-swap','1g','--user','10001:10001','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--mount',f'type=bind,source={inputs},target=/work/input,readonly','--mount',f'type=bind,source={script},target=/work/solver.py,readonly','--mount',f'type=bind,source={output},target=/work/output',a.image,'python','-I','/work/solver.py']
 start=time.perf_counter();record={'command':cmd,'container_name':name,'retained':a.keep_container,'image':a.image,'status':'started'}
 try:
  result=subprocess.run(cmd,capture_output=True,timeout=180)
  (run/'execution-stdout.txt').write_bytes(result.stdout);(run/'execution-stderr.txt').write_bytes(result.stderr)
  record.update(status='completed' if result.returncode==0 else 'failed',exit_code=result.returncode)
 except subprocess.TimeoutExpired as e:
  record.update(status='timeout',exit_code=None)
  (run/'execution-stdout.txt').write_bytes(e.stdout or b'');(run/'execution-stderr.txt').write_bytes(e.stderr or b'')
 finally:
  if a.keep_container:
   subprocess.run(['docker','stop','--time','2',name],capture_output=True,timeout=15)
   inspection=subprocess.run(['docker','inspect',name],capture_output=True,timeout=15)
   (run/'container-inspect.json').write_bytes(inspection.stdout)
  else:
   subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
  record['elapsed_s']=time.perf_counter()-start
  (run/'execution.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
 total=0
 for f in output.rglob('*'):
  if f.is_symlink() or f.is_junction():raise ValueError('Unexpected link in output')
  if f.is_file():
   size=f.stat().st_size;total+=size
   if size>10*1024*1024:raise ValueError('Output file exceeds 10 MiB')
 if total>30*1024*1024:raise ValueError('Output total exceeds 30 MiB')
 print(json.dumps(record,ensure_ascii=False))
 if record.get('exit_code')!=0:raise SystemExit(1)
if __name__=='__main__':main()
