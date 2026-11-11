"""Persist backend receipts before graph publication; reuse them after a crash."""
import copy,uuid
from psycopg.types.json import Jsonb
from .contracts import digest
from .executors import ExecutionRequest,receipt,validate_receipt
from .artifacts import snapshot_artifacts
from .reviews import artifact_status

class DispatchError(ValueError):pass

def dispatch(workflow,task):
    db=workflow.db
    contract=db.execute('SELECT sha256,content,executor_key,executor_config FROM mc_contracts WHERE task_id=%s AND version=%s',(task['id'],task['current_version'])).fetchone()
    if not task['model_approved']:raise DispatchError('Model not approved')
    if contract['executor_key'] is not None and (contract['executor_key']!=task['executor_key'] or contract['executor_config']!=task['executor_config']):raise DispatchError('Task execution settings differ from approved version')
    key=digest({'task':task['id'],'version':task['current_version'],'contract':contract['sha256'],'backend':task['executor_key'],'config':task['executor_config']})
    request=ExecutionRequest(task['id'],task['current_version'],contract['sha256'],key,task['executor_key'],copy.deepcopy(task['executor_config']),copy.deepcopy(contract['content']))
    existing=db.execute('SELECT * FROM mc_executions WHERE operation_key=%s',(key,)).fetchone()
    if existing:return existing,db.execute('SELECT payload FROM mc_backend_receipts WHERE operation_key=%s',(key,)).fetchone()['payload']['review']
    # Old records predate receipts; preserve their identity when rebuilding checkpoints.
    old=db.execute("SELECT * FROM mc_executions WHERE task_id=%s AND version=%s AND mode='fixture' AND operation_key IS NULL",(task['id'],task['current_version'])).fetchone()
    if old:return old,{'status':'unknown','mode':'fixture','note':'Legacy fixed evidence; user review required.'}
    cached=db.execute('SELECT payload FROM mc_backend_receipts WHERE operation_key=%s',(key,)).fetchone()
    if cached:
        result=cached['payload'];validate_receipt(result,request)
        if any(artifact_status(a)!='verified' for a in result['artifacts']):raise DispatchError('Cached execution receipt artifact changed')
    else:
        backend=workflow.executors.get(task['executor_key'])
        if backend is None:raise DispatchError('Configured execution backend unavailable; no fallback')
        previous=db.execute("SELECT phase FROM mc_backend_attempts WHERE operation_key=%s ORDER BY id DESC LIMIT 1",(key,)).fetchone()
        legacy=not callable(getattr(backend,'execute',None)) and callable(getattr(backend,'artifacts',None))
        replay_safe=legacy or getattr(backend,'replay_safe',False)
        if previous and not replay_safe:
            # Recover only; never blindly dispatch a potentially side-effecting job again.
            recover=getattr(backend,'recover',None)
            if not callable(recover):raise DispatchError('Execution outcome unknown; backend recovery required before retry')
            invoke=lambda:recover(request)
        else:invoke=(lambda:receipt(request,backend.artifacts(request.contract))) if legacy else (lambda:backend.execute(request))
        db.execute('INSERT INTO mc_backend_attempts(operation_key,task_id,version,phase,payload) VALUES(%s,%s,%s,%s,%s)',(key,task['id'],task['current_version'],'started',Jsonb({'backend_key':request.backend_key,'recovery':bool(previous and not replay_safe)})))
        try:
            result=invoke();validate_receipt(result,request)
            result['artifacts']=snapshot_artifacts(result['artifacts'])
        except Exception as exc:
            db.execute('INSERT INTO mc_backend_attempts(operation_key,task_id,version,phase,payload) VALUES(%s,%s,%s,%s,%s)',(key,task['id'],task['current_version'],'failed' if replay_safe or getattr(exc,'failure_domain',None)=='code' else 'unknown',Jsonb({'error':str(exc)[:2000],'backend_key':request.backend_key,'error_code':getattr(exc,'code',None),'failure_domain':getattr(exc,'failure_domain','infrastructure')})))
            raise
        with db.transaction():
            db.execute('INSERT INTO mc_backend_receipts(operation_key,task_id,version,backend_key,contract_sha256,payload) VALUES(%s,%s,%s,%s,%s,%s)',(key,task['id'],task['current_version'],request.backend_key,request.contract_sha256,Jsonb(result)))
            db.execute('INSERT INTO mc_backend_attempts(operation_key,task_id,version,phase,payload) VALUES(%s,%s,%s,%s,%s)',(key,task['id'],task['current_version'],'succeeded',Jsonb({'backend_key':request.backend_key})))
    # Deliberately a separate transaction: receipt survives publication failure.
    with db.transaction():
        current=workflow.task(task['id'])
        if current['current_version']!=request.version or not current['model_approved']:raise DispatchError('Stale or unapproved execution cannot publish')
        execution_id=uuid.uuid4()
        execution=db.execute('INSERT INTO mc_executions(id,task_id,version,contract_sha256,mode,artifacts,run_id,backend_key,operation_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(execution_id,task['id'],task['current_version'],request.contract_sha256,result['mode'],Jsonb(result['artifacts']),result.get('run_id'),request.backend_key,key)).fetchone()
        workflow._event(task['id'],'execution_receipt_registered','system',{'version':task['current_version'],'execution_id':str(execution_id),'backend_key':request.backend_key,'operation_key':key,'mode':result['mode'],'not_new_solve':result['mode']=='fixture'})
    return execution,result['review']
