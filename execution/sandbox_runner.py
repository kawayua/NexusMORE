"""Container-side supervisor. All returned solver data remains untrusted evidence."""
import base64,json,os,signal,stat,subprocess,sys,threading,time
from pathlib import Path

JOB=Path('/work/job');OUT=Path('/work/output')
config=json.loads((JOB/'job.json').read_text())
limits=config['limits'];started=time.monotonic();overflow=threading.Event()
logs={'stdout':bytearray(),'stderr':bytearray()}

def oom_count():
    try:return int(dict(line.split() for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines()).get('oom_kill',0))
    except (OSError,ValueError):return 0

def drain(stream,key):
    while True:
        block=stream.read(8192)
        if not block:break
        room=limits['max_log_bytes']-len(logs[key])
        logs[key].extend(block[:max(0,room)])
        if len(block)>room:overflow.set()

def collect(encode=False):
    artifacts=[];total=0
    for folder,dirs,files in os.walk(OUT,followlinks=False):
        for name in dirs+files:
            p=Path(folder)/name;s=p.lstat()
            if stat.S_ISLNK(s.st_mode):raise ValueError('unsafe_artifact')
            if stat.S_ISDIR(s.st_mode):continue
            if not stat.S_ISREG(s.st_mode):raise ValueError('unsafe_artifact')
            total+=s.st_size
            if s.st_size>limits['max_file_bytes'] or total>limits['max_total_bytes'] or len(artifacts)>=limits['max_files']:raise ValueError('output_limit')
            item={'name':p.relative_to(OUT).as_posix(),'size_bytes':s.st_size}
            if encode:
                fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as f:data=f.read(limits['max_file_bytes']+1)
                if len(data)!=s.st_size:raise ValueError('unsafe_artifact')
                item['base64']=base64.b64encode(data).decode('ascii')
            artifacts.append(item)
    return artifacts

before_oom=oom_count()
process=subprocess.Popen([sys.executable,'-I','-B',str(JOB/'solver.py')],cwd=OUT,
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
threads=[threading.Thread(target=drain,args=(getattr(process,key),key),daemon=True) for key in logs]
for t in threads:t.start()
status='succeeded'
while process.poll() is None:
    if time.monotonic()-started>limits['timeout_s']:status='timeout';break
    if overflow.is_set():status='output_limit';break
    try:collect()
    except ValueError as exc:status=str(exc);break
    time.sleep(.03)
# Terminate the solver's process group, including ordinary forked descendants.
try:os.killpg(process.pid,signal.SIGKILL)
except ProcessLookupError:pass
try:process.wait(timeout=2)
except subprocess.TimeoutExpired:status='timeout'
for t in threads:t.join(timeout=1)
if any(t.is_alive() for t in threads):status='code_error'
if oom_count()>before_oom:status='memory_limit'
elif overflow.is_set():status='output_limit'
elif status=='succeeded' and process.returncode!=0:status='code_error'
artifacts=[]
try:
    artifacts=collect(encode=status=='succeeded')
except ValueError as exc:status=str(exc)
if status!='succeeded':artifacts=[]
stderr=logs['stderr'].decode('utf-8',errors='replace')
error_kind='syntax_error' if 'SyntaxError:' in stderr else 'dependency_missing' if 'ModuleNotFoundError:' in stderr else None
packet={'packet_version':'1.0.0','status':status,'exit_code':process.returncode,
    'stdout':logs['stdout'].decode('utf-8',errors='replace'),'stderr':stderr,
    'elapsed_s':round(time.monotonic()-started,6),'artifacts':artifacts,'error_kind':error_kind,
    'oom_kill_observed':oom_count()>before_oom}
print(json.dumps(packet,ensure_ascii=True,separators=(',',':')),flush=True)
sys.exit(0 if status=='succeeded' else 10)
