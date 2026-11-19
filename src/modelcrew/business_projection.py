"""Read-only authoritative binding and separate user-decision projections."""
from .business_contract import BusinessContractError, pending_id
from .contracts import digest


def require_row(row):
    if row is None:
        raise BusinessContractError('not_found', 'Requested business object does not exist')
    return row


def binding(w, args):
    result = {}
    if args.get('task_id'):
        t = w.task(args['task_id'])
        result = {'project_id':t['project_id'],'task_id':t['id'],'version':t['current_version']}
        contract = require_row(w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s', (t['id'],t['current_version'])).fetchone())
        result['contract_sha256'] = contract['sha256']
        if t['execution_id']:
            result['execution_id'] = str(t['execution_id'])
        if t['result_revision']:
            result['result_revision'] = t['result_revision']
        if args.get('run_id'):
            table='mc_modeling_runs' if args.get('_modeling') else 'mc_hand_runs'
            selection='COALESCE(version,base_version) AS version,payload' if args.get('_modeling') else 'version,payload'
            run = require_row(w.db.execute(f'SELECT {selection} FROM {table} WHERE task_id=%s AND id::text=%s',(t['id'],args['run_id'])).fetchone())
            if run['version'] != t['current_version']:
                raise BusinessContractError('stale_binding','Run belongs to an earlier model version')
            result['run_id'] = args['run_id']
            if run['payload'].get('workflow_sha256'):
                result['context_sha256'] = run['payload']['workflow_sha256']
    elif args.get('project_id'):
        project = args['project_id'];w.require_project(project);result['project_id']=project
        if args.get('build_id'):
            row = require_row(w.db.execute('SELECT payload FROM mc_assembly_builds WHERE project_id=%s AND id::text=%s',(project,args['build_id'])).fetchone())
            result['build_id']=args['build_id']
            if row['payload'].get('context_identity'):
                result['context_sha256']=row['payload']['context_identity']
            if row['payload'].get('source_ready'):
                result['source_sha256']=digest(row['payload'].get('sealed',{}))
        elif args.get('run_id'):
            row = require_row(w.db.execute('SELECT payload FROM mc_assembly_runs WHERE project_id=%s AND id::text=%s',(project,args['run_id'])).fetchone())
            result['run_id']=args['run_id']
            if row['payload'].get('context_sha256'):
                result['context_sha256']=row['payload']['context_sha256']
    return result


def check_binding(w, args, expected):
    current=binding(w,args)
    if any(key not in current or current[key]!=value for key,value in expected.items()):
        raise BusinessContractError('stale_binding','Expected binding no longer matches authoritative state')
    return current


def pending_item(kind, bound, ids, operation):
    ids=sorted(ids)
    return {'pending_id':pending_id(kind,bound,ids),'kind':kind,'binding':bound,'artifact_ids':ids,
            'prompt':'请在自己控制的本地终端使用 python -m modelcrew.trusted_decisions review，分别审阅并决定；模型工具调用不能代表用户批准。',
            'allowed_decisions':['approve','reject'],'decision_operation':operation}


def task_pending(w, registry, task, *, run_id=None):
    with w.lock(task):
        bound=binding(w,{'task_id':task});t=w.task(task);result=[]
        if not run_id and not t['model_approved'] and t['phase']=='WAITING_MODEL_APPROVAL':
            result.append(pending_item('model',bound,[],'task_decide'))
        if not run_id and t['model_approved'] and t['result_revision'] and not t['result_approved'] and t['phase']=='WAITING_RESULT_APPROVAL':
            result.append(pending_item('result',bound,[],'task_decide'))
        rows=w.db.execute("SELECT id,payload FROM mc_hand_runs WHERE task_id=%s AND version=%s AND hand='writing'"+(' AND id::text=%s' if run_id else ''),
                          (task,t['current_version'],run_id) if run_id else (task,t['current_version'])).fetchall()
        if run_id and not rows:
            # A coding run has no writing-user decisions, but must still exist.
            require_row(w.db.execute('SELECT 1 FROM mc_hand_runs WHERE task_id=%s AND version=%s AND id::text=%s',(task,t['current_version'],run_id)).fetchone())
        for row in rows:
            state=w.hand_status(task,str(row['id']))
            if state['hand']!='writing' or not row['payload'].get('manuscript'):
                continue
            if state['phase'] not in ('WAITING_MANUSCRIPT_AND_FIGURES','READY_FOR_E_EXPORT'):
                continue
            artifacts=registry.task(task,t['current_version'],str(row['id']))
            for kind,key,hash_key in [('manuscript','manuscript_review','manuscript_sha256'),('figures','figure_review','figure_catalog_sha256')]:
                if row['payload'].get(key):
                    continue
                sha=state.get(hash_key)
                if sha:
                    ids=[a['artifact_id'] for a in artifacts if a['sha256']==sha]
                    if not ids:
                        raise BusinessContractError('artifact_changed','Pending decision artifact is not registered')
                    item_binding={**bound,'run_id':str(row['id']),'artifact_sha256':sha}
                    result.append(pending_item(kind,item_binding,ids,'hand_decide'))
        return result


def assembly_pending(w, registry, project, build):
    state=w.assembly_build_status(project,build)
    if state.get('issues') or state['phase'] not in ('WAITING_ASSEMBLY_REVIEW','READY_TO_EXPORT'):
        return []
    row=require_row(w.db.execute('SELECT payload FROM mc_assembly_builds WHERE project_id=%s AND id::text=%s',(project,build)).fetchone())
    artifacts=registry.assembly(project,build);base=binding(w,{'project_id':project,'build_id':build});result=[]
    for kind,key,path in [('manuscript','manuscript_review',state.get('manuscript')),('figures','figure_review',(state['source']+'/figure-catalog.json') if state.get('source') else None)]:
        if row['payload'].get(key) or not path:
            continue
        sha=row['payload'].get('sealed',{}).get(path)
        if not sha:
            raise BusinessContractError('artifact_changed','Pending assembly source is not sealed')
        ids=[a['artifact_id'] for a in artifacts if a['sha256']==sha]
        result.append(pending_item(kind,{**base,'artifact_sha256':sha},ids,'assembly_decide'))
    return result


def list_pending(w, registry, args):
    project=args['project_id'];w.require_project(project)
    if args.get('task_id'):
        if w.task(args['task_id'])['project_id']!=project:
            raise BusinessContractError('not_found','Task is outside requested project')
        return task_pending(w,registry,args['task_id'],run_id=args.get('run_id'))
    if args.get('build_id'):
        return assembly_pending(w,registry,project,args['build_id'])
    tasks=w.db.execute('SELECT id FROM mc_tasks WHERE project_id=%s ORDER BY id LIMIT 1001',(project,)).fetchall()
    builds=w.db.execute('SELECT id FROM mc_assembly_builds WHERE project_id=%s ORDER BY id LIMIT 1001',(project,)).fetchall()
    if len(tasks)>1000 or len(builds)>1000:
        raise BusinessContractError('invalid_request','Narrow pending lookup to a task or build')
    result=[]
    for task in tasks:
        result+=task_pending(w,registry,task['id'])
    for build in builds:
        result+=assembly_pending(w,registry,project,str(build['id']))
    return result


def host_review_readiness(w, task):
    """Stricter native UX readiness; never grants approval or edits a run."""
    t=w.task(task);version=t['current_version']
    row=w.db.execute('SELECT status,version,payload FROM mc_modeling_runs WHERE task_id=%s ORDER BY sequence DESC LIMIT 1',(task,)).fetchone()
    result={'model_ready':False,'version':version,'open_questions':[], 'reason':'modeling_required'}
    if t['model_approved'] or t['phase']!='WAITING_MODEL_APPROVAL':
        result['reason']='not_waiting_model';return result
    if row is None:return result
    if row['version']!=version:
        result['reason']='stale_modeling';return result
    result['open_questions']=row['payload'].get('open_questions',[])
    if result['open_questions']:
        result['reason']='clarification_required';return result
    if row['status']!='ready':
        result['reason']='independent_m1_required';return result
    try:
        from .modeling_hand import assert_m1
        from .mathematics import snapshot
        from .inputs import assert_ready
        from .mcp_workflow import source_snapshot
        contract=require_row(w.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone())['content']
        if contract['schema_version']=='1.1.0':assert_ready(contract)
        if snapshot(w,task,version) is None:
            result['reason']='mathematics_required';return result
        if assert_m1(w,t) is None:return result
        source_snapshot(w,task,version)
    except Exception:
        result['reason']='evidence_not_ready';return result
    return {**result,'model_ready':True,'reason':'ready'}
