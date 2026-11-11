"""Readable, immutable version history composed from business records and artifacts."""
import copy
from .reviews import artifact_status

def differences(before,after,path=''):
    if type(before)!=type(after):return [{'path':path or '/','before':before,'after':after,'change':'replace'}]
    if isinstance(before,dict):
        result=[]
        for key in sorted(before.keys()|after.keys()):
            pointer=path+'/'+key.replace('~','~0').replace('/','~1')
            if key not in before:result.append({'path':pointer,'change':'add','after':after[key]})
            elif key not in after:result.append({'path':pointer,'change':'remove','before':before[key]})
            else:result.extend(differences(before[key],after[key],pointer))
        return result
    if before!=after:return [{'path':path or '/','change':'replace','before':before,'after':after}]
    return []

def dossier(workflow,task,version=None):
    with workflow.lock(task),workflow.db.transaction():
        current=workflow.task(task);version=current['current_version'] if version is None else version
        contract=workflow.db.execute('SELECT * FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
        if not contract:raise ValueError('Unknown contract version')
        parent=workflow.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s',(task,contract['parent_version'])).fetchone() if contract['parent_version'] else None
        entries=workflow.db.execute('SELECT * FROM mc_version_entries WHERE task_id=%s AND version=%s ORDER BY created_at,id',(task,version)).fetchall()
        for entry in entries:entry['body']['artifacts']=[{**a,'integrity':artifact_status(a)} for a in entry['body'].get('artifacts',[])]
        executions=workflow.db.execute('SELECT * FROM mc_executions WHERE task_id=%s AND version=%s ORDER BY created_at,id',(task,version)).fetchall()
        for execution in executions:execution['artifacts']=[{**a,'integrity':artifact_status(a)} for a in execution['artifacts']]
        results=workflow.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s ORDER BY revision',(task,version)).fetchall()
        summaries=workflow.db.execute('SELECT * FROM mc_summaries WHERE task_id=%s AND version=%s ORDER BY revision',(task,version)).fetchall()
        events=workflow.db.execute('SELECT * FROM mc_events WHERE task_id=%s ORDER BY id',(task,)).fetchall()
        events=[e for e in events if e['payload'].get('version',e['payload'].get('contract_version'))==version or (e['kind'] in ('revise_model_requested','restore_version_requested') and e['payload'].get('version')==version-1)]
        # Legacy records are shown with honest gaps rather than invented Agent output.
        grouped={kind:[e for e in entries if e['kind']==kind] for kind in ['proposal','feedback','next_step','change_note','code','experiment']}
        from .mcp_workflow import evidence
        tools=evidence(workflow,task,version)
        from .mathematics import snapshot
        math_history=workflow.db.execute('SELECT revision,sha256,semantic_sha256,proposal_sha256,change_kind,actor,reason,created_at FROM mc_math_packages WHERE task_id=%s AND version=%s ORDER BY revision',(task,version)).fetchall()
        mathematical=snapshot(workflow,task,version)
        parent_mathematical=snapshot(workflow,task,contract['parent_version']) if parent else None
        math_changes=differences(parent_mathematical['content'] if parent_mathematical else None,mathematical['content'] if mathematical else None)
        return {'mathematics':mathematical,'mathematical_history':math_history,'mathematical_changes_from_parent':math_changes,**tools,'task_id':task,'version':version,'is_current':version==current['current_version'],'contract':contract,
                'changes_from_parent':differences(parent['content'],contract['content']) if parent else [],
                'entries':grouped,'method_from_contract':copy.deepcopy(contract['content']['method']),
                'execution_attempts':workflow.db.execute('SELECT * FROM mc_backend_attempts WHERE task_id=%s AND version=%s ORDER BY id',(task,version)).fetchall(),'execution_receipts':workflow.db.execute('SELECT * FROM mc_backend_receipts WHERE task_id=%s AND version=%s',(task,version)).fetchall(),'executions':executions,'results':results,'confirmations_and_events':events,'summaries':summaries,
                'missing_sections':[k for k in ['proposal','next_step'] if not grouped[k]],
                'note':'Missing historical prose is not reconstructed as original Agent output; artifact hashes are checked at read time.'}
