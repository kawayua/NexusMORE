"""Read authoritative external rerun facts; never run a solver or alter results."""
import json
from pathlib import Path
from .collaboration import sha_file,workspace_path,CollaborationStore,Receipt,Ticket
from .contracts import digest
from .workflow import WorkflowError


def verify_packets(primary,replica,*,executor):
    """Verify both immutable packets and every actual output, not a claimed PASS."""
    for data in [primary,replica]:
        if data['receipt']['status']!='succeeded':raise WorkflowError('Runtime reproduction execution did not succeed')
    jobs=[v['job'] for v in [primary,replica]]
    if jobs[0]['code_sha256']!=jobs[1]['code_sha256'] or jobs[0]['inputs']!=jobs[1]['inputs'] or jobs[0]['authorization']!=jobs[1]['authorization'] or any(jobs[0].get(k)!=jobs[1].get(k) for k in ['runner_sha256','limits']):
        raise WorkflowError('Runtime reproduction job bindings differ')
    hashes=[]
    for data in [primary,replica]:
        seen={}
        for asset in data['receipt']['artifacts']:
            if asset['name'] in seen:raise WorkflowError('Duplicate runtime artifact name')
            path=workspace_path(executor,asset['path'])
            if sha_file(path)!=asset['sha256']:raise WorkflowError('Runtime reproduction output changed')
            seen[asset['name']]=asset['sha256']
        if not seen:raise WorkflowError('Runtime reproduction has no artifacts')
        hashes.append(seen)
    if hashes[0]!=hashes[1]:raise WorkflowError('Runtime reproduction output hashes differ')
    return {'status':'PASS','criterion':'Exact equality of all output bytes in two successful controlled executions',
        'artifact_count':len(hashes[0]),'artifact_hashes':hashes[0],
        'code_sha256':jobs[0]['code_sha256'],'authorization':jobs[0]['authorization'],
        'execution_runs':[v['receipt']['run_id'] for v in [primary,replica]],
        'actual_files_verified':True,'new_solver_execution':False}


def collect(w,chapter,*,root,executor):
    """Resolve a unique attached coder by exact approved chapter result binding."""
    binding=chapter['binding']
    if not all(k in binding for k in ['task_id','contract_version','contract_sha256','execution_id','result_revision']):
        return {'status':'NOT_AVAILABLE','reason':'Chapter does not declare a complete numeric binding; no success inferred'}
    candidates=w.db.execute("SELECT * FROM mc_hand_runs WHERE task_id=%s AND version=%s AND hand='coding'",(chapter['task_id'],binding['contract_version'])).fetchall()
    matches=[r for r in candidates if r['payload'].get('binding')==binding and r['payload'].get('attached') and r['payload'].get('full_packet') and r['payload'].get('replica_packet')]
    if not matches:return {'status':'NOT_AVAILABLE','binding':binding,'reason':'No bound external reproduction records found; generator status is not proof of completion'}
    if len(matches)!=1:raise WorkflowError('Ambiguous bound runtime reproduction source')
    row=matches[0];p=row['payload'];packets=[];sources=[]
    for name in ['full_packet','replica_packet']:
        relative=p[name];path=workspace_path(root,relative);expected=p.get('sealed',{}).get(relative)
        if not expected or sha_file(path)!=expected:raise WorkflowError('Unsealed or changed runtime execution packet')
        packets.append(json.loads(path.read_text(encoding='utf-8')))
        sources.append({'path':relative,'sha256':expected})
    report=verify_packets(*packets,executor=executor)
    auth=report['authorization']
    if any(auth.get(k)!=binding[b] for k,b in [('task_id','task_id'),('version','contract_version'),('contract_sha256','contract_sha256')]):
        raise WorkflowError('Runtime reproduction differs from approved model binding')
    accepted=p.get('reviews',{}).get(p.get('accepted_reviews',{}).get('P2'))
    if not accepted or accepted['status']!='PASS':raise WorkflowError('Bound coder has no accepted independent P2')
    store=CollaborationStore(Path(root)/'runs/hands'/str(row['id'])/'records',root=root)
    receipt=store.load(Receipt,accepted['receipt_sha256']);ticket=store.load(Ticket,receipt.ticket_sha256)
    if receipt.status!='PASS' or ticket.gate!='P2' or ticket.binding.model_dump(mode='json',exclude={'schema_version'})!=binding:
        raise WorkflowError('Bound P2 receipt identity mismatch')
    if store.accept_review(receipt,accepted['snapshot_sha256'],historical_workflow_sha256=p.get('workflow_sha256'))!=accepted['receipt_sha256']:
        raise WorkflowError('Bound independent P2 evidence invalid')
    report.update(binding=binding,source_run_id=str(row['id']),packet_sources=sources,
        accepted_independent_P2=accepted,
        status_semantics='This external runtime proof supersedes generator PENDING_RUNTIME ONLY for byte reproduction. It does not turn other numerical FAILs into PASS, grant user approval, or assert experimental validation.')
    return report
