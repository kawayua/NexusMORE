"""Read-only review routing from a chapter chat to its current assembly build."""
from .business_artifacts import ArtifactRegistry
from .business_projection import list_pending
from .business_contract import BusinessContractError


def contains_task(w,project,build,task,run=None):
    row=w.db.execute('SELECT r.payload FROM mc_assembly_builds b JOIN mc_assembly_runs r ON r.id=b.assembly_run_id WHERE b.project_id=%s AND b.id::text=%s',(project,build)).fetchone()
    return bool(row and any(c.get('task_id')==task and (not run or c.get('run_id')==run) for c in row['payload'].get('chapters',[])))


def review_target(service,scope):
    """Never choose an unrelated project build or silently pick among several drafts."""
    items=service.pending(scope)
    if items or not scope.get('task_id'):return scope,items
    with service.adapter.workflow() as w:
        if w.task(scope['task_id'])['project_id']!=scope['project_id']:raise BusinessContractError('not_found','Task outside project')
        builds=w.db.execute("SELECT id FROM mc_assembly_builds WHERE project_id=%s AND phase='WAITING_ASSEMBLY_REVIEW' AND payload->>'source_ready'='true' ORDER BY created_at DESC LIMIT 1001",(scope['project_id'],)).fetchall()
        if len(builds)>1000:raise BusinessContractError('user_input_required','Narrow assembly review to a build')
        candidates=[]
        for row in builds:
            build=str(row['id'])
            if not contains_task(w,scope['project_id'],build,scope['task_id'],scope.get('run_id')):continue
            effective={'project_id':scope['project_id'],'build_id':build}
            pending=list_pending(w,ArtifactRegistry(w,service.root),effective)
            if pending:candidates.append((effective,pending))
        if len(candidates)>1:raise BusinessContractError('user_input_required','Several assembly drafts need review; specify a build')
        return candidates[0] if candidates else (scope,[])
