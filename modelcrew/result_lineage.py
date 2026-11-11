"""Explicit inheritance of an unchanged numerical P2 across interpretation revisions.

The independent interpretation review supplements, never replaces, the original P2.
Admissions are immutable local audit events, not supplier-generated receipts.
"""
from pathlib import Path
import json
from .config import ROOT
from .contracts import digest
from .collaboration import CollaborationStore,Receipt,Ticket,Snapshot,sha_file,workspace_path
from .workflow import WorkflowError

EVENT='result_interpretation_P2_admitted'
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def same_execution(base,current):
    if str(base['execution_id'])!=str(current['execution_id']):raise WorkflowError('Interpretation changed numerical execution')
    if base['review'].get('kind')!='d4_P2_review' or base['review'].get('status')!='passed':raise WorkflowError('Original admitted numerical P2 required')
    if current['review'].get('kind')!='interpretation_review' or current['review'].get('status')!='passed' or current['review'].get('narrative_status')!='structured_only':raise WorkflowError('Passed structured interpretation required')
    if current['revision']<=base['revision']:raise WorkflowError('Interpretation revision must follow original P2')

def verify_proof(w,task,proof):
    t=w.task(task)
    if proof['task_id']!=task or proof['version']!=t['current_version'] or proof['revision']!=t['result_revision'] or not t['result_approved']:raise WorkflowError('Confirmed current interpretation required')
    from .mathematics import assert_gate_binding
    assert_gate_binding(w,t,'model');assert_gate_binding(w,t,'result')
    base=w.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,proof['version'],proof['base_revision'])).fetchone()
    current=w.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,proof['version'],proof['revision'])).fetchone()
    if not base or not current:raise WorkflowError('Missing result revision')
    same_execution(base,current)
    if digest(current['review'])!=proof['review_sha256'] or digest(base['review'])!=proof['base_review_sha256'] or str(t['execution_id'])!=proof['execution_id']:raise WorkflowError('Result review binding changed')
    path=workspace_path(ROOT,proof['independent_review_path'])
    if sha_file(path)!=proof['independent_review_sha256']:raise WorkflowError('Independent interpretation review changed')
    reviewer=read(path)
    if reviewer.get('status')!='PASS' or reviewer.get('gate')!='P2' or not reviewer.get('read_only') or not reviewer.get('independent_context') or not reviewer.get('reviewer'):raise WorkflowError('Independent P2 interpretation PASS required')
    if (reviewer.get('task_id'),reviewer.get('contract_version'),reviewer.get('result_revision'),reviewer.get('execution_id'))!=(task,proof['version'],proof['revision'],proof['execution_id']):raise WorkflowError('Independent interpretation binding mismatch')
    reviewed_current=False
    for name,expected in reviewer.get('input_hashes',{}).items():
        evidence=workspace_path(ROOT,(path.parent/name).resolve().relative_to(ROOT.resolve()).as_posix())
        if sha_file(evidence)!=expected:raise WorkflowError('Independent review input changed')
        obj=read(evidence); reviewed=obj.get('result',{}) if isinstance(obj,dict) else {}
        if (reviewed.get('task_id'),reviewed.get('version'),reviewed.get('revision'),str(reviewed.get('execution_id')))==(task,proof['version'],proof['revision'],proof['execution_id']) and reviewed.get('review')==current['review'] and reviewed.get('interpretation')==current['interpretation']:
            reviewed_current=True
    if not reviewed_current:raise WorkflowError('Independent P2 did not review this exact result and claim set')
    from .reviews import artifact_status,review_interpretation
    e=w.db.execute('SELECT * FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()
    if any(artifact_status(a)!='verified' for a in e['artifacts']):raise WorkflowError('Numerical artifact changed')
    c=w.db.execute('SELECT * FROM mc_contracts WHERE task_id=%s AND version=%s',(task,t['current_version'])).fetchone()
    if c['sha256']!=reviewer.get('contract_sha256'):raise WorkflowError('Interpretation contract differs')
    fresh=review_interpretation(c,e,current['interpretation'],current['review']['claims'],True)
    if fresh['status']!='passed':raise WorkflowError('Interpretation claims no longer pass')
    from .full_result import verify_frozen_files
    folder=workspace_path(ROOT,base['review']['source_run']);manifest,_=verify_frozen_files(folder)
    meta=read(folder/'run.json');admission=read(folder/'P2-admission.json');store=CollaborationStore(folder/'records')
    receipt=store.load(Receipt,admission['receipt_sha256']);ticket=store.load(Ticket,receipt.ticket_sha256)
    if ticket.gate!='P2' or receipt.status!='PASS' or store.accept_review(receipt,admission['snapshot_sha256'],historical_workflow_sha256=ticket.policy_sha256)!=admission['receipt_sha256']:raise WorkflowError('Original independent numerical P2 invalid')
    if (meta['task_id'],meta['contract_version'],meta['execution_id'],meta['result_revision'],meta['contract_sha256'])!=(task,proof['version'],proof['execution_id'],proof['base_revision'],c['sha256']):raise WorkflowError('Original numerical P2 binding mismatch')
    snapshot=store.load(Snapshot,admission['snapshot_sha256']);b=snapshot.binding
    if (b.task_id,b.contract_version,b.contract_sha256,b.execution_id,b.result_revision)!=(task,proof['version'],c['sha256'],proof['execution_id'],proof['base_revision']):raise WorkflowError('Original numerical P2 snapshot binding mismatch')
    frozen=next((a for a in snapshot.artifacts if a.artifact_id=='frozen_files'),None)
    if frozen is None or frozen.sha256!=sha_file(folder/'frozen-artifacts.json'):raise WorkflowError('Original P2 did not review this frozen package')
    return proof

def admit(w,task,*,base_revision,independent_review_path):
    t=w.task(task)
    with w.lock(task):
        base=w.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,t['current_version'],base_revision)).fetchone()
        current=w.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,t['current_version'],t['result_revision'])).fetchone()
        if not base or not current:raise WorkflowError('Missing result revision')
        path=workspace_path(ROOT,independent_review_path)
        proof={'task_id':task,'version':t['current_version'],'revision':t['result_revision'],'base_revision':base_revision,'execution_id':str(t['execution_id']),'review_sha256':digest(current['review']),'base_review_sha256':digest(base['review']),'independent_review_path':path.relative_to(ROOT).as_posix(),'independent_review_sha256':sha_file(path),'scope':'Original numerical P2 + new independent interpretation P2; neither receipt overwritten.'}
        verify_proof(w,task,proof)
        old=w.db.execute('SELECT payload FROM mc_events WHERE task_id=%s AND kind=%s ORDER BY id DESC',(task,EVENT)).fetchall()
        existing=next((r['payload'] for r in old if r['payload']['revision']==proof['revision']),None)
        if existing and existing!=proof:raise WorkflowError('Conflicting immutable interpretation admission')
        if not existing:w._event(task,EVENT,'trusted-local-independent-review-import',proof)
        return proof

def verify(w,task):
    t=w.task(task);rows=w.db.execute('SELECT payload FROM mc_events WHERE task_id=%s AND kind=%s ORDER BY id DESC',(task,EVENT)).fetchall()
    proof=next((r['payload'] for r in rows if r['payload']['version']==t['current_version'] and r['payload']['revision']==t['result_revision']),None)
    if not proof:raise WorkflowError('Independent interpretation P2 admission missing')
    return verify_proof(w,task,proof)

def assert_model(w,t):
    """Retain the exact old M1 policy, while revalidating current model semantics."""
    from .modeling_hand import assert_m1
    row=w.db.execute('SELECT review FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(t['id'],t['current_version'],t['result_revision'])).fetchone() if t['result_revision'] else None
    if not row or row['review'].get('kind')!='interpretation_review':return assert_m1(w,t)
    verify(w,t['id'])
    model=w.db.execute('SELECT * FROM mc_modeling_runs WHERE task_id=%s ORDER BY sequence DESC LIMIT 1',(t['id'],)).fetchone()
    if not model:return assert_m1(w,t)
    store=CollaborationStore(ROOT/model['payload']['folder']/'records');receipt=store.load(Receipt,model['payload']['receipt_sha256']);ticket=store.load(Ticket,receipt.ticket_sha256)
    return assert_m1(w,t,historical_workflow_sha256=ticket.policy_sha256)
