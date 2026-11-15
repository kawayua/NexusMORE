"""Freeze D4 evidence, admit independent P2, then publish a pending user result."""
import argparse,json,shutil,uuid
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.collaboration import (CollaborationStore,Artifact,Snapshot,Call,Binding,Receipt,sha_file,REQUIRED_CHECKS)
from modelcrew.modeling_hand import M1Answer,pointer
from scripts.run_d4_full import workflow,ensure_current,BASE
from scripts.run_d3_minimal import read,write
from modelcrew.full_result import verify_frozen_files


def freeze(folder):
    if (folder/'frozen-artifacts.json').exists():raise ValueError('Already frozen; do not rewrite reviewed evidence')
    meta=read(folder/'run.json')
    with workflow() as w:ensure_current(w,meta)
    manifest=read(folder/'figure-manifest.json')
    if manifest['logical_count']<9 or any(manifest['counts'].get(k,0)<3 for k in ['raw','process','result']):raise ValueError('Candidate set incomplete')
    if not read(folder/'figure-qa.json')['passed'] or not read(folder/'visual-review.json')['passed']:raise ValueError('Figure QA not complete')
    executions={key:read(folder/(key+'-execution.json')) for key in ['primary','reproduction','guard-probe','bracket-probe']}
    write(folder/'execution-evidence.json',{'binding':{k:meta[k] for k in ['task_id','contract_version','contract_sha256','execution_id','result_revision']},'executions':executions,
        'main_solver_code_sha256':meta['code_sha256'],'P1_numerical_core_sha256':meta['core_sha256'],'no_generated_code_on_host':True})
    numeric=read(folder/'independent-numerics.json')
    write(folder/'result-evidence.json',{'contract_checks':read(folder/'output/checks.json'),'numeric_checks':numeric['checks'],'finite_difference':numeric['finite_difference'],
        'workbook':read(folder/'workbook-validation.json'),'fault_probes':read(folder/'fault-probes.json'),'sample_results':read(folder/'sample-results.json'),
        'scope':'301 times x224 handles; deterministic kinematics, no collision proof','user_result_approval':'pending'})
    for path in ['scripts/render_d4_figures.py','scripts/review_d4_full.py','modelcrew/full_result.py','modelcrew/workflow.py']:
        shutil.copyfile(ROOT/path,folder/'sources'/Path(path).name)
    names=['contract.json','mathematics.json','inputs.json','configuration.json','generated_solver.py','numerical-core.py','code-evidence.json',
        'guard-probe.py','bracket-probe.py','reproduction.json','fault-probes.json','independent-numerics.json','workbook-validation.json',
        'geometry-provenance.json','figure-contracts.json','figure-manifest.json','figure-qa.json','visual-review.json','sample-results.json','execution-evidence.json','result-evidence.json']
    paths=[folder/name for name in names]
    for key in ['primary','reproduction','guard-probe','bracket-probe']:
        paths += [folder/(key+'-'+part+'.json') for part in ['job','dispatch','execution','envelope']]
    paths += [p for p in (folder/'output').iterdir() if p.is_file()]
    paths += [p for p in (folder/'sources').iterdir() if p.is_file()]
    for figure in manifest['figures']:paths += [ROOT/path for path in figure['files'].values()]
    contacts=list(folder.glob('figures-v*/contact-sheet.png'));paths += [contacts[-1]]
    binding={key:meta[key] for key in ['task_id','contract_version','contract_sha256','execution_id','result_revision']}
    files={'binding':binding,'artifacts':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size} for p in sorted(set(paths))]}
    write(folder/'frozen-artifacts.json',files)
    store=CollaborationStore(folder/'records');author=Call.model_validate(meta['author'])
    specs=[('code','code','code-evidence.json'),('inputs','input','inputs.json'),('contract','input','contract.json'),('mathematics','input','mathematics.json'),
        ('execution','execution','execution-evidence.json'),('result','result','result-evidence.json'),('figures','figure','figure-manifest.json'),
        ('figure_qa','figure','figure-qa.json'),('visual_review','figure','visual-review.json'),('geometry','input','geometry-provenance.json'),
        ('reproduction','reproduction','reproduction.json'),('frozen_files','result','frozen-artifacts.json')]
    artifacts=[Artifact(artifact_id=i,kind=kind,path=(folder/path).relative_to(ROOT).as_posix(),sha256=sha_file(folder/path),author_call_ids=[author.call_id]) for i,kind,path in specs]
    snapshot=Snapshot(binding=author.binding,hand='coding',artifacts=artifacts,lineage_call_ids=meta['lineage_call_ids'])
    key=store.freeze(snapshot)
    write(folder/'P2-context.json',{'snapshot_sha256':key,'binding':binding,'required_checks':REQUIRED_CHECKS['P2'],
        'evidence':{a.artifact_id:a.path for a in artifacts},'review_response_schema':M1Answer.model_json_schema(),
        'images':{fig['figure_id']:fig['files']['png'] for fig in manifest['figures']},
        'source_code':(folder/'generated_solver.py').relative_to(ROOT).as_posix(),
        'read_only':True,'author_self_check_is_not_independent':True})
    meta['status']='frozen_waiting_P2';meta['P2_snapshot_sha256']=key;write(folder/'run.json',meta)
    print(json.dumps({'snapshot_sha256':key,'frozen_files':len(files['artifacts'])}),flush=True)


def dispatch(folder,reviewer_id):
    verify_frozen_files(folder)
    if (folder/'P2-dispatch.json').exists():raise ValueError('P2 already dispatched')
    meta=read(folder/'run.json');context=read(folder/'P2-context.json')
    store=CollaborationStore(folder/'records')
    author=Call.model_validate(meta['author'])
    reviewer=Call(call_id='P2-agent-'+reviewer_id,context_id='independent-agent-'+reviewer_id,role='quality',binding=author.binding)
    store.register_call(reviewer)
    ticket=store.dispatch_review(context['snapshot_sha256'],'P2',reviewer.call_id)
    write(folder/'P2-dispatch.json',{'reviewer_agent_id':reviewer_id,'reviewer_call_id':reviewer.call_id,
        'ticket_sha256':ticket,'snapshot_sha256':context['snapshot_sha256'],'fork_turns':'none','read_only':True})
    print(json.dumps({'ticket_sha256':ticket}),flush=True)


def admit(folder):
    verify_frozen_files(folder)
    meta=read(folder/'run.json');packet=read(folder/'P2-dispatch.json');context=read(folder/'P2-context.json')
    answer=M1Answer.model_validate(read(folder/'P2-response.json'))
    evidence={key:read(ROOT/path) for key,path in context['evidence'].items()}
    for check in answer.checks:
        for proof in check.evidence:
            if proof.artifact_id not in evidence:raise ValueError('P2 cites unknown artifact')
            pointer(evidence[proof.artifact_id],proof.selector)
    status='FAIL' if any(c.status=='FAIL' for c in answer.checks) else ('BLOCKED' if any(c.status=='BLOCKED' for c in answer.checks) else 'PASS')
    receipt=Receipt(ticket_sha256=packet['ticket_sha256'],reviewer_call_id=packet['reviewer_call_id'],status=status,checks=answer.checks,issues=answer.issues)
    store=CollaborationStore(folder/'records');key=store.accept_review(receipt,packet['snapshot_sha256'])
    write(folder/'P2-admission.json',{'status':status,'reported_status':answer.status,'receipt_sha256':key,'snapshot_sha256':packet['snapshot_sha256'],
        'reviewer_agent_id':packet['reviewer_agent_id'],'raw_response_sha256':sha_file(folder/'P2-response.json'),
        'independent_context':True,'read_only':True,'semantic_findings_modified':False})
    meta['status']='P2_'+status.lower();write(folder/'run.json',meta)
    print(json.dumps({'P2':status,'receipt_sha256':key}),flush=True)


def attach(folder):
    meta=read(folder/'run.json')
    if read(folder/'P2-admission.json')['status']!='PASS':raise ValueError('P2 not passed')
    with workflow() as w:
        current=w.attach_solver_result(meta['task_id'],version=meta['contract_version'],run_dir=folder)
        task=current['task']
        if str(task['execution_id'])!=meta['execution_id'] or task['result_revision']!=meta['result_revision'] or task['result_approved']:raise ValueError('Unexpected submitted result state')
        payload={'task_id':task['id'],'version':task['current_version'],'execution_id':str(task['execution_id']),
            'result_revision':task['result_revision'],'phase':task['phase'],'result_approved':task['result_approved'],
            'review_status':current['result']['review']['status'],'review_kind':current['result']['review']['kind'],
            'P2_receipt_sha256':current['result']['review']['P2_receipt_sha256'],'artifact_count':len(current['execution']['artifacts'])}
        write(folder/'submission.json',payload)
    meta['status']='waiting_user_result_approval';write(folder/'run.json',meta)
    print(json.dumps(payload),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','dispatch','admit','attach']);parser.add_argument('--run',type=Path,required=True);parser.add_argument('--reviewer-id');args=parser.parse_args()
    folder=args.run.resolve()
    if folder.parent!=BASE.resolve():raise ValueError('Unexpected full run directory')
    if args.stage=='dispatch':dispatch(folder,args.reviewer_id)
    else:{'freeze':freeze,'admit':admit,'attach':attach}[args.stage](folder)
