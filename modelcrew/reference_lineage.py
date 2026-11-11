"""Explicit preservation of frozen cross-question references after interpretation-only updates."""
from pathlib import Path
from .config import ROOT
from .contracts import digest
from .collaboration import sha_file,workspace_path
from .workflow import WorkflowError
from .result_lineage import read,verify as verify_result_lineage
EVENT='question_reference_interpretation_conserved'

def validate_conservation(w,target_id,reference_id,proof):
    from .question_references import verify_record,artifact
    t=w.task(target_id)
    row=w.db.execute('SELECT payload,sha256 FROM mc_question_references WHERE id=%s',(reference_id,)).fetchone();ref=verify_record(row)
    if ref['target_id']!=target_id or proof['reference_id']!=reference_id or proof['target_id']!=target_id or proof['target_version']!=t['current_version']:raise WorkflowError('Conservation target mismatch')
    source=ref['source'];binding=source['source_binding'];lineage=verify_result_lineage(w,binding['task_id'])
    if lineage['base_revision']!=binding.get('result_revision') or lineage['version']!=binding['contract_version'] or lineage['execution_id']!=binding['execution_id'] or proof['new_source_revision']!=lineage['revision']:raise WorkflowError('Reference is not the admitted unchanged numerical result')
    c=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(target_id,t['current_version'])).fetchone()
    if c['sha256']!=proof['target_contract_sha256']:raise WorkflowError('Dependent model changed')
    sc=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(binding['task_id'],binding['contract_version'])).fetchone()
    if sc['sha256']!=binding['contract_sha256']:raise WorkflowError('Source model changed')
    for f in source['files']:artifact(f['path'],f['sha256'])
    base=w.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(binding['task_id'],binding['contract_version'],binding['result_revision'])).fetchone()
    old=source['values'].get('result')
    if old and (old['interpretation']!=base['interpretation'] or old['review']!=base['review']):raise WorkflowError('Frozen reference differs from original result')
    review_path=workspace_path(ROOT,proof['independent_review_path'])
    if sha_file(review_path)!=proof['independent_review_sha256']:raise WorkflowError('Reference conservation review changed')
    report=read(review_path)
    expected=(target_id,reference_id,proof['new_source_revision'])
    if (report.get('target_id'),report.get('reference_id'),report.get('new_source_revision'))!=expected or report.get('status')!='PASS' or report.get('gate')!='M1' or not report.get('read_only') or not report.get('independent_context'):raise WorkflowError('Independent reference-impact review required')
    if report.get('proposal_sha256')!=proof['proposal_sha256']:raise WorkflowError('Reference-impact proposal changed')
    proposal=workspace_path(ROOT,proof['proposal_path'])
    if sha_file(proposal)!=proof['proposal_sha256']:raise WorkflowError('Conservation proposal changed')
    return source

def admit(w,target_id,reference_id,*,proposal_path,independent_review_path):
    with w.lock(target_id):
        proposal=read(workspace_path(ROOT,proposal_path));t=w.task(target_id)
        c=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(target_id,t['current_version'])).fetchone()
        p=workspace_path(ROOT,independent_review_path)
        proof={'target_id':target_id,'target_version':t['current_version'],'target_contract_sha256':c['sha256'],'reference_id':reference_id,'new_source_revision':proposal['new_source_revision'],'proposal_path':proposal_path,'proposal_sha256':sha_file(workspace_path(ROOT,proposal_path)),'independent_review_path':independent_review_path,'independent_review_sha256':sha_file(p),'scope':'Preserve exact historical reference bytes after independently verified unchanged execution; do not rewrite source binding or grant new downstream approvals.'}
        validate_conservation(w,target_id,reference_id,proof)
        rows=w.db.execute('SELECT payload FROM mc_events WHERE task_id=%s AND kind=%s ORDER BY id DESC',(target_id,EVENT)).fetchall()
        old=next((r['payload'] for r in rows if r['payload']['reference_id']==reference_id and r['payload']['new_source_revision']==proof['new_source_revision']),None)
        if old and old!=proof:raise WorkflowError('Conflicting reference conservation')
        if not old:w._event(target_id,EVENT,'trusted-local-independent-review-import',proof)
        return proof

def conserved(w,target_id,reference_id,source):
    rows=w.db.execute('SELECT payload FROM mc_events WHERE task_id=%s AND kind=%s ORDER BY id DESC',(target_id,EVENT)).fetchall()
    for row in rows:
        if row['payload']['reference_id']==reference_id:
            actual=validate_conservation(w,target_id,reference_id,row['payload'])
            if actual!=source:raise WorkflowError('Conserved reference bytes changed')
            return True
    return False
