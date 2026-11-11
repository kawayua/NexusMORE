"""Read-only delivery evidence audit; no provider calls, approvals or execution."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.workflow import Workflow
OUT=ROOT/'stage-d/runtime-integration/20261110-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    old=json.loads((ROOT/'stage-d/acceptance/20261109-v1/evidence-audit.json').read_text(encoding='utf-8'))
    changes=[]
    for item in old['evidence_files']:
        p=ROOT/item['path']
        if not p.is_file() or sha(p)!=item['sha256']:changes.append(item['path'])
    assert set(changes)<= {'AGENTS.md','modelcrew/api.py'}, changes
    calls=[];runs=[]
    with Workflow() as w:
        rows=w.db.execute("SELECT * FROM mc_hand_runs WHERE payload->'request'->>'actor'='ENGINEERING_PROBE' ORDER BY created_at").fetchall()
        for row in rows:
            p=row['payload'];folder=ROOT/'stage-d/runs/runtime'/str(row['id'])
            runs.append({'run_id':str(row['id']),'task_id':row['task_id'],'hand':row['hand'],'phase':row['phase'],'attempt':p['attempt'],'reviews':p['reviews'],'feedback':p.get('feedback'),'binding':p['binding'],'business_user_approvals_created':False,'synthetic_model_approval_for_isolated_probe':row['hand']=='coding'})
            for meta in sorted((folder/'operations').glob('*/*-metadata.json')):
                data=json.loads(meta.read_text(encoding='utf-8'))
                calls.append({'run_id':str(row['id']),'operation':meta.parent.name,'path':meta.relative_to(ROOT).as_posix(),'sha256':sha(meta),**{k:data.get(k) for k in ['call_id','stage','configured_model','returned_model','status','http_status','elapsed_seconds','usage','finish_reason']}})
        tasks={}
        for task in ['d2-bench-q1-20261108','d6-bench-q2-20261109']:
            t=w.task(task);assert t['model_approved'] and t['result_approved'] and t['result_revision']==1
            tasks[task]={k:str(t[k]) if k=='execution_id' else t[k] for k in ['current_version','model_approved','result_approved','result_revision','execution_id']}
    result={'created_at':datetime.now(timezone.utc).isoformat(),'scope':'Read-only byte/provenance/runtime audit; not new business semantic review or user approval','prior_pinned_files':len(old['evidence_files']),'expected_implementation_changes':changes,'other_prior_pinned_files_unchanged':len(old['evidence_files'])-len(changes),'business_approvals':tasks,'real_provider_calls':calls,'engineering_probe_runs':runs,'new_user_stage_acceptance':False}
    path=OUT/'delivery-evidence.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'prior_pinned_files':len(old['evidence_files']),'expected_changed':changes,'real_provider_metadata_records':len(calls),'runs':len(runs),'business_approvals_preserved':True},ensure_ascii=False))
if __name__=='__main__':main()
