"""Read-only paper handoff from a confirmed result, including completed tasks."""
from pathlib import Path
from .workflow import WorkflowError


def prepare(w,task,version,figure_catalog=None,result_evidence=None):
    from . import hand_runtime as hr
    t=w.task(task)
    if t['current_version']!=version or not t['model_approved'] or not t['result_approved'] or not t['result_revision']:
        raise WorkflowError('Current approved model and confirmed results required before writing')
    if w.db.execute("SELECT 1 FROM mc_hand_runs WHERE task_id=%s AND hand='coding' AND payload ? 'numeric_only_scope' AND payload->'binding'->>'execution_id'=%s",(task,str(t['execution_id']))).fetchone():
        raise WorkflowError('Numeric-only engineering result excludes writing')
    from .mathematics import assert_gate_binding
    from .result_lineage import assert_model
    assert_model(w,t);assert_gate_binding(w,t,'model');assert_gate_binding(w,t,'result')
    result=w.db.execute('SELECT review FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,version,t['result_revision'])).fetchone()
    if not result or result['review'].get('status')!='passed':raise WorkflowError('Passed independent result review required')
    review=result['review']
    if review.get('kind')!='hand_runtime_P2':
        if not figure_catalog:raise WorkflowError('Version-bound figure_catalog is required before writer creation')
        return {'figure_catalog':figure_catalog,'result_evidence':result_evidence or [],'acceptance_context':None}
    producer=hr.verify_result(w,task,review['run_id']);p=producer['payload']
    packet=hr.read(hr.workspace_path(hr.ROOT,p['full_packet']))
    artifact=next((a for a in packet['artifacts'] if a['path'].endswith('/figure-catalog.json')),None)
    if not artifact:raise WorkflowError('Confirmed result has no candidate figure catalog')
    catalog=hr.workspace_path(hr.ROOT,artifact['path'])
    if hr.sha_file(catalog)!=artifact['sha256']:raise WorkflowError('Confirmed catalog changed')
    if figure_catalog:
        supplied=Path(figure_catalog)
        supplied=supplied if supplied.is_absolute() else hr.workspace_path(hr.ROOT,figure_catalog)
        if not supplied.resolve().is_relative_to(hr.ROOT.resolve()) or hr.sha_file(supplied)!=artifact['sha256']:
            raise WorkflowError('Writer catalog must match the confirmed result')
    from .writing_reviews import catalog_at
    cat=catalog_at(catalog)
    expected={'task_id':task,'contract_version':version,'contract_sha256':p['binding']['contract_sha256'],
              'execution_id':str(t['execution_id']),'result_revision':t['result_revision']}
    if cat.get('evidence')!=expected:raise WorkflowError('Writer catalog binding differs from confirmed result')
    e=w.db.execute('SELECT artifacts FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()
    bysha={a['sha256']:a for a in e['artifacts']};selected=[]
    if result_evidence:
        for value in result_evidence:
            matches=[]
            for a in e['artifacts']:
                path=Path(a['path']);path=path if path.is_absolute() else hr.ROOT/path
                if value in (str(path),path.as_posix(),hr.rel(path),a.get('origin_path')):matches.append(path)
            if not matches:raise WorkflowError('Requested result evidence is not in the confirmed execution')
            selected.append(hr.rel(matches[0]))
    else:
        for name in ('result.json',):
            a=next((a for a in packet['artifacts'] if a['path'].endswith('/'+name)),None)
            if not a or a['sha256'] not in bysha:raise WorkflowError('Confirmed numerical result JSON is missing')
            path=Path(bysha[a['sha256']]['path']);path=path if path.is_absolute() else hr.ROOT/path
            if hr.sha_file(path)!=a['sha256']:raise WorkflowError('Confirmed result bytes changed')
            selected.append(hr.rel(path))
    p2=p['reviews'][p['accepted_reviews']['P2']]
    context={'binding':expected,'independent_P2':p2,'read_only_approved_result':True,
             'rule':'User-confirmed results only. Original numeric FAIL remains FAIL; disclose accepted deviations, not threshold achievement. Paper/figures need separate user confirmation.'}
    if p.get('error_acceptance_addendum'):
        from .deviation_acceptance import validate
        accepted=validate(producer);context['user_accepted_deviations']={k:accepted[k] for k in ['decision','accepted_checks','acceptance_disposition','scope']}
    return {'figure_catalog':hr.rel(catalog),'result_evidence':selected,'acceptance_context':context}


def resolve_confirmed_reference(w,registry,task,value):
    """An approved output may be a writer input without becoming a new task input."""
    if not isinstance(value,str) or not value.startswith('artifact:'):return value
    t=w.task(task);row=w.db.execute('SELECT path,sha256,owner FROM mc_business_artifacts WHERE artifact_id=%s',(value[9:],)).fetchone()
    if not row or any(row['owner'].get(k)!=v for k,v in {'project_id':t['project_id'],'task_id':task,'version':t['current_version']}.items()):
        raise WorkflowError('Writer reference belongs to another task/version')
    execution=w.db.execute('SELECT artifacts,run_id FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()
    if (not execution or row['sha256'] not in {a['sha256'] for a in execution['artifacts']}
            or row['owner'].get('run_id') not in (None,str(execution['run_id']))):
        raise WorkflowError('Writer reference is not an output of the approved execution')
    from .business_artifacts import checked_path,read_verified
    path=checked_path(registry.root,row['path']);read_verified(registry.root,path,row['sha256'])
    return str(path)


def recover_legacy_missing_catalog(w,task,request_id,legacy_source,*,apply=False):
    """Settle only the proved old pre-insert guard rejection; never replay it."""
    import hashlib
    from .business_store import BusinessStore
    from .business_contract import request_digest,validate_response
    from .business_adapter import failure
    from . import hand_runtime as hr
    with w.lock('business:task:'+task),w.lock(task),w.db.transaction():
        t=w.task(task);scope={'project_id':t['project_id'],'task_id':task};store=BusinessStore(w.db);row=store.get(scope,'hand_start',request_id)
        if not row:raise WorkflowError('Original writing start record required')
        if row['state']=='failed' and (row.get('response') or {}).get('data',{}).get('recovery_kind')=='legacy_writer_missing_catalog':
            return {'applied':True,'replayed':True,'evidence':row['response']['data']}
        req=row['request'];args=req['arguments'];body=args['body']
        if (row['state']!='outcome_unknown' or row['request_sha256']!=request_digest(req)
                or args['task_id']!=task or args.get('hand')!='writing' or body.get('figure_catalog')
                or body['version']!=t['current_version'] or not t['result_approved']
                or req['request_id']!=request_id):raise WorkflowError('Not the legacy missing-catalog failure')
        if w.db.execute('SELECT 1 FROM mc_hand_runs WHERE task_id=%s AND request_id=%s',(task,body['request_id'])).fetchone():
            raise WorkflowError('A writing run exists; query it instead')
        source=hr.workspace_path(hr.ROOT,legacy_source);text=source.read_text(encoding='utf-8')
        guard="if not req.figure_catalog:";insert='INSERT INTO mc_hand_runs'
        if guard not in text or insert not in text or text.index(guard)>text.index(insert):
            raise WorkflowError('No historical source proof of pre-insert rejection')
        producer=hr.verify_result(w,task,w.db.execute('SELECT review FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,t['current_version'],t['result_revision'])).fetchone()['review']['run_id'])
        evidence={'recovery_kind':'legacy_writer_missing_catalog','task_id':task,'version':t['current_version'],
            'original_request_sha256':row['request_sha256'],'no_matching_writer_run':True,
            'legacy_guard_source':legacy_source,'legacy_guard_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'guard_precedes_first_writer_insert':True,'approved_result_unchanged':producer['payload']['binding'],
            'reason':'Old core required figure_catalog and rejected this exact request before inserting any writing run; not a solver-mode prohibition. Original files/history retained.'}
        if apply:
            response=failure('hand_start','invalid_request',request_id);response.update(binding=scope,data=evidence,receipt={**store.receipt(row),'state':'failed'})
            validate_response(response);store.save(row,'failed',response)
        return {'applied':apply,'evidence':evidence}
