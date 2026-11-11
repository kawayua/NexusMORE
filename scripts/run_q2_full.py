"""Q2 full-run orchestration; generated numerical code runs only through MCP/Docker."""
import argparse,json,uuid,shutil
from pathlib import Path
import numpy as np
from modelcrew.config import ROOT
from modelcrew.collaboration import Binding,Call,CollaborationStore,sha_file
from modelcrew.docker_executor import DockerExecutor,register_job
from modelcrew.mcp_client import executor_root
from modelcrew.mcp_workflow import trace_call
from scripts.run_d3_minimal import approved,static_check,read,write
from scripts.run_d4_full import workflow
TASK='d6-bench-q2-20261109'
PARENT=ROOT/'stage-d/runs/coding/q2-minimal-027eb6ae1c3642a185725e844f745fcf'
def active():return ROOT/read(ROOT/'stage-d/q2-coding/full-active.json')['folder']
def build(folder):
    with workflow() as w,w.lock(TASK):
        state=approved(w,TASK,2);admission=read(PARENT/'P1-admission.json')
        if admission['status']!='PASS':raise ValueError('P1 required')
        source=(PARENT/'generated_solver.py').read_text(encoding='utf-8')
        base=source[:source.index('def main():')]
        base=base.replace('T_END = 300.0','T_END = float(arc(THETA_INIT)-arc(24.0))-.01') if False else base.replace('T_END = 300.0','T_END = 417.0')
        base=base.replace('if head[0]<40:', 'if head[0]<24:').replace('delta=np.diff(q); e=2e-11','delta=np.diff(q); e=1e-13').replace('e+1e-13','e+4e-14')
        supplier=(folder/'supplier-functions.py').read_text(encoding='utf-8')
        supplier=supplier.replace('    import sys\n','').replace('sys.float_info.epsilon, sys.float_info.epsilon','np.nextafter(a,b), np.nextafter(b,a)').replace('iv(2.86, 2.86)','iv(down(2.86), up(2.86))')
        supplier=supplier.replace('    # outer branch residual is strictly negative for ell < 2r, so the\n    # *continuation* check we certify is that the outer root stays below\n    # pi/2, i.e. the sign at pi/2 has not yet flipped into a second root.','    # F is strictly increasing on (0,pi), so F(pi/2)>0 places the\n    # unique root below pi/2. This is a branch-domain check.')
        tail=(ROOT/'execution/full_q2_tail.py').read_text(encoding='utf-8-sig')
        code=base+'\n'+supplier+'\n'+tail
        static_check(code);(folder/'full-base.py').write_text(code,encoding='utf-8')
        bind=Binding(task_id=TASK,contract_version=2,contract_sha256=state['contract']['sha256'],execution_id=folder.name,result_revision=1)
        author=Call(call_id='coding-'+uuid.uuid4().hex,context_id='codex-q2-full-'+uuid.uuid4().hex,role='coding',binding=bind)
        store=CollaborationStore(folder/'records');store.register_call(author)
        api=read(folder/'supplier-coding-call.json');api_author=Call(call_id=api['call_id'],context_id=api['context_id'],role='coding',binding=bind);store.register_call(api_author)
        meta={'task_id':TASK,'contract_version':2,'contract_sha256':state['contract']['sha256'],'folder':folder.relative_to(ROOT).as_posix(),'author':author.model_dump(mode='json'),'supplier_author':api_author.model_dump(mode='json'),'base_code_sha256':sha_file(folder/'full-base.py'),'P1_receipt_sha256':admission['receipt_sha256'],'P1_core_preserved_exactly':False,'P1_changes':'head domain 24; certified nonexpansive bound; endpoint/extrema sine tightening; batched root precision; AABB; left-first first-event search','supplier_API_coding_call':api,'supplier_patch':'removed unused sys import; decimal ell interval widening; corrected explanatory comment; raw reply preserved','status':'prepared','result_user_approval':'pending','figure_selection_user_approval':'pending','execution_id':folder.name,'result_revision':1}
        write(folder/'run.json',meta)
        paths=['AGENTS.md','resources/paper/workflow.json','resources/paper/writer-instructions.md','resources/paper/chinese-modeling-policy.json','docs/scientific-figure-contract.md','resources/algorithms/index.md','resources/algorithms/numerical-geometry.md','scripts/run_q2_full.py','execution/full_q2_tail.py']
        records=[]
        for i,p in enumerate(paths):
            dest=folder/'sources'/f'{i}-{Path(p).name}';shutil.copyfile(ROOT/p,dest);records.append({'path':p,'sha256':sha_file(ROOT/p),'snapshot':dest.relative_to(ROOT).as_posix()})
        write(folder/'configuration.json',{'sources':records,'backend':'Python/matplotlib','supplier_partial_implementation':True,'Codex_integration':True,'full_autonomous_API_Coder':False})
        w.record_entry(TASK,version=2,kind='code',text='Q2全量实现准备：实际供应商API参与域证书/左优先函数，Codex集成连续区间、事件与输出；原始API回复及补丁留痕。',actor='coding-hand',request_id=folder.name+'-prepared',artifacts=[{'path':meta['folder']+'/full-base.py','sha256':meta['base_code_sha256'],'role':'full_solver_code'}])
    print(str(folder),flush=True)

def job(folder,key,start,end):
    sub=folder/key;sub.mkdir(exist_ok=True);root=executor_root();m=read(folder/'run.json')
    code=sub/'generated_solver.py'
    if not code.exists():
        base=(folder/'full-base.py').read_text(encoding='utf-8')
        if key.endswith('early-feature'):
            base=base.replace('if b-a<2e-7:','if b-a<1e-4:').replace('probe=min(end,a+4e-7)','probe=min(end,max(b,a+4e-7))')
        if key.endswith('tight-rate') or key.endswith('final-bound'):
            base=base.replace('if b-a<2e-7:','if b-a<.01:').replace('probe=min(end,a+4e-7)','probe=min(end,max(b,a+4e-7))')
            base=base.replace('def attempt_event(a,b,state):',(ROOT/'execution/q2_tight_rate.py').read_text(encoding='utf-8-sig')+'\n\ndef attempt_event(a,b,state):')
            base=base.replace('a,b=stack.pop();attempts+=1','a,b=stack.pop();attempts+=1\n        if attempts%512==0:print(json.dumps({"attempts":attempts,"current_s":[a,b],"safe_end":safe[-1][1] if safe else start}),flush=True)')
        if key.endswith('final-bound'):
            base=base.replace('probe=min(end,max(b,a+4e-7))','probe=min(end,max(b,a+1e-3))')
            base=base.replace('gap,corner,normal=feature_interval(qi,spec)\n    _,denom=', 'gap,corner,normal=feature_interval(qi,spec)\n    endpoint_right=feature_interval(state(right)[3],spec)[0]\n    endpoint_left=feature_interval(state(left)[3],spec)[0]\n    gap=iv(max(float(gap[0]),float(endpoint_right[0])),min(float(gap[1]),float(endpoint_left[1])))\n    _,denom=')
        code.write_text('PART_START='+repr(start)+'\nPART_END='+repr(end)+'\n'+base,encoding='utf-8')
    static_check(code.read_text(encoding='utf-8'))
    with workflow() as w,w.lock(TASK):
        state=approved(w,TASK,2,m['contract_sha256'])
        if sha_file(folder/'full-base.py')!=m['base_code_sha256']:raise ValueError('frozen base changed')
        jid=folder.name+'-'+key
        if not (sub/'job.json').exists():
            inputs=[{'name':'template.xlsx' if i['role']=='required_output_template' else 'statement.pdf','path':i['path'],'sha256':i['sha256'],'input_id':i['id']} for i in state['contract']['content']['inputs']]
            write(sub/'job.json',register_job(root,jid,code,inputs,{'mode':'workflow','task_id':TASK,'version':2,'contract_sha256':m['contract_sha256']},{'timeout_s':180,'memory_mb':1024}))
        registered=read(sub/'job.json');_,actual=DockerExecutor(root).job(jid)
        if actual!=registered or registered['code_sha256']!=sha_file(code):raise ValueError('job bytes changed')
        if (sub/'execution.json').exists():result=read(sub/'execution.json')
        else:
            tool='code_execution_status' if (sub/'dispatch.json').exists() else 'code_execute'
            previous=read(sub/'envelope.json') if (sub/'envelope.json').exists() else {}
            if previous.get('error') and previous['error'].get('code')=='not_found' and not (root/'runs'/jid).exists():tool='code_execute'
            write(sub/'dispatch.json',{'tool':tool,'job_id':jid})
            trace,envelope=trace_call(w,TASK,2,'code-executor',tool,{'run_id' if tool=='code_execution_status' else 'job_id':jid},jid)
            write(sub/('mcp-'+envelope['call_id']+'.json'),envelope);write(sub/'envelope.json',envelope)
            if envelope['status']!='ok':raise ValueError('MCP failed; preserve/query same operation')
            result=envelope['data'];write(sub/'execution.json',result)
        if result['status']!='succeeded':print(json.dumps(result),flush=True);raise ValueError('job failed; frozen failure retained')
        if result['job_sha256']!=registered['job_sha256'] or result['code_sha256']!=registered['code_sha256'] or result['authorization']!=registered['authorization'] or result['run_id']!=jid or result.get('cleanup',{}).get('removed') is not True:raise ValueError('receipt mismatch')
        DockerExecutor(root).verify_artifacts(result)
    files={a['name']:root/a['path'] for a in result['artifacts']}
    for p in files.values():
        if not p.resolve().is_relative_to((root/'runs'/jid/'artifacts').resolve()):raise ValueError('bad output path')
    if 'partition-result.json' not in files:
        write(sub/'output-manifest.json',{n:{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha_file(p)} for n,p in files.items()})
        if set(files)!={'support-certificate.json'}:raise ValueError('unexpected auxiliary outputs')
        return read(files['support-certificate.json'])
    report=read(files['partition-result.json'])
    if report['contract_sha256']!=m['contract_sha256'] or report['code_sha256']!=registered['code_sha256']:raise ValueError('report binding mismatch')
    write(sub/'output-manifest.json',{n:{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha_file(p)} for n,p in files.items()})
    write(sub/'partition-result.json',report)
    with np.load(files['safe-segments.npz'],allow_pickle=False) as z:segments=z['segments'].copy()
    cursor=start
    for a,b,gap in segments:
        if a!=cursor or b<=a or gap<=0:raise ValueError('invalid certificate prefix')
        cursor=float(b)
    if report['safe_prefix_end_s']!=cursor:raise ValueError('certificate end mismatch')
    if report['status']=='SAFE' and cursor!=end:raise ValueError('partition incomplete')
    print(json.dumps({'partition':key,'status':report['status'],'segments':len(segments),'elapsed_s':result['elapsed_s'],'time_interval_s':report.get('time_interval_s')}),flush=True)
    return report

def run(folder,one=False):
    reports=[]
    plan=read(folder/'primary-plan.json')['partitions'] if (folder/'primary-plan.json').exists() else [{'key':f'part-{k:02d}','start':float(a),'end':float(min(a+40,416))} for k,a in enumerate(range(0,416,40))]
    for k,part in enumerate(plan):
        a,b=part['start'],part['end']
        r=job(folder,part['key'],a,b);reports.append(r)
        write(folder/'progress.json',{'completed_partitions':len(reports),'status':r['status'],'safe_prefix_end_s':r['safe_prefix_end_s'],'last_partition':k})
        if r['status']=='FIRST_CONTACT':
            write(folder/'collision-event.json',r);m=read(folder/'run.json');m['status']='full_event_found';write(folder/'run.json',m);return
        if r['status']!='SAFE':raise ValueError('earliest unresolved interval; never bypass')
        if one:return
    raise ValueError('No contact before certified branch-domain horizon; UNKNOWN, not collision')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['build','run','one']);a=p.parse_args();f=active()
    (build(f) if a.stage=='build' else run(f,a.stage=='one'))
