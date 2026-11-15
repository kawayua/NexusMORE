"""Persist MCP operations and source discussions against immutable contract versions."""
import uuid
from psycopg.types.json import Jsonb
from .contracts import digest
from .mcp_client import McpTransportError

READ_TOOLS={'algorithm_search','paper_search','web_search','web_read','reference_get'}


def trace_call(workflow,task,version,service,tool,arguments,operation_key):
    contract=workflow.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
    if not contract:raise ValueError('Unknown contract version')
    base=(task,version,contract['sha256'],operation_key,service,tool)
    def save(phase,payload):
        identifier=str(uuid.uuid4())
        workflow.db.execute('INSERT INTO mc_mcp_traces(id,task_id,version,contract_sha256,operation_key,service,tool,phase,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                            (identifier,*base,phase,Jsonb(payload)))
        return identifier
    start_id=save('started',{'arguments':arguments})
    try:
        envelope=workflow.mcp.call(service,tool,arguments)
        digest(envelope)
    except Exception as exc:
        save('transport_error',{'started_trace_id':start_id,'error_code':'mcp_transport_unavailable'})
        raise McpTransportError('MCP operation has no confirmed response; inspect traces before retry') from exc
    trace_id=save('completed',{'started_trace_id':start_id,'envelope':envelope})
    return trace_id,envelope


def retrieve(workflow,task,*,version,tool,arguments,actor,request_id):
    from .workflow import WorkflowError
    if tool not in READ_TOOLS:raise WorkflowError('Only reference retrieval tools allowed')
    if not actor.strip() or not request_id.strip():raise WorkflowError('Actor and request ID required')
    if not isinstance(arguments,dict):raise WorkflowError('Tool arguments must be an object')
    # Validate before starting a process or loading local weights.
    from .paper_search_mcp import SearchRequest,WebSearchRequest,WebReadRequest,ReferenceRequest,AlgorithmRequest
    schema={'algorithm_search':AlgorithmRequest,'paper_search':SearchRequest,'web_search':WebSearchRequest,'web_read':WebReadRequest,'reference_get':ReferenceRequest}[tool]
    arguments=schema.model_validate(arguments).model_dump(mode='json')
    fingerprint=digest({'kind':'mcp_retrieve','version':version,'tool':tool,'arguments':arguments,'actor':actor})
    with workflow.lock(task):
        old=workflow.db.execute('SELECT * FROM mc_requests WHERE task_id=%s AND request_id=%s',(task,request_id)).fetchone()
        if old:
            if old['payload_sha256']!=fingerprint:raise WorkflowError('Idempotency key reused with different action')
            return old['response']
        t=workflow.task(task)
        if t['current_version']!=version:raise WorkflowError('Stale contract version')
        if t['model_approved'] or t['phase']!='WAITING_MODEL_APPROVAL':raise WorkflowError('New reference input requires an unapproved model version')
        op=digest({'task':task,'version':version,'request_id':request_id,'fingerprint':fingerprint})
        trace_id,envelope=trace_call(workflow,task,version,'paper-search',tool,arguments,op)
        with workflow.db.transaction():
            if envelope['status']=='ok':
                for hit in envelope['data']['hits']:
                    citation=hit.get('citation')
                    if not citation or citation.get('origin') not in (('external_reference','builtin_project_reference') if tool in ('algorithm_search','reference_get') else ('external_reference',)) or citation.get('modeler_generated') is not False or citation.get('content_sha256')!=digest(hit['text']) or citation.get('source_sha256')!=hit['source_sha256'] or citation.get('source_url')!=hit.get('source_url'):
                        raise WorkflowError('Invalid external citation binding')
                    if tool!='reference_get' and citation.get('bound_call_id')!=envelope['call_id']:
                        raise WorkflowError('Citation belongs to another MCP call')
                    row=workflow.db.execute('SELECT payload,payload_sha256 FROM mc_references WHERE task_id=%s AND version=%s AND reference_id=%s',(task,version,citation['reference_id'])).fetchone()
                    if row:
                        if any(row['payload'].get(key)!=hit.get(key) for key in ('text','citation','source_sha256','source_url','locator','parser','chunk_id')):
                            raise WorkflowError('Reference ID reused with different content')
                        continue
                    workflow.db.execute('INSERT INTO mc_references(task_id,version,reference_id,trace_id,payload,payload_sha256) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                        (task,version,citation['reference_id'],trace_id,Jsonb(hit),digest(hit)))
            response={'task_id':task,'version':version,'trace_id':trace_id,'envelope':envelope}
            workflow.db.execute('INSERT INTO mc_requests VALUES(%s,%s,%s,%s)',(task,request_id,fingerprint,Jsonb(response)))
            workflow._event(task,'mcp_reference_retrieved',actor,{'version':version,'trace_id':trace_id,'tool':tool,'status':envelope['status'],'reference_ids':[h['citation']['reference_id'] for h in envelope['data']['hits']] if envelope['status']=='ok' else []})
        return response


def discussion(workflow,task,*,version,kind,text,references,actor,request_id):
    from .workflow import WorkflowError
    if kind not in ('proposal','feedback'):raise WorkflowError('Reference discussion kind must be proposal or feedback')
    if not references or not isinstance(references,list):raise WorkflowError('Reference decisions required')
    ids=set()
    for item in references:
        if not isinstance(item,dict) or set(item)!={'reference_id','decision'} or item['decision'] not in ('adopted','rejected','considered') or item['reference_id'] in ids:
            raise WorkflowError('Invalid or duplicate reference decision')
        ids.add(item['reference_id'])
    fingerprint=digest({'kind':'reference_discussion','version':version,'entry_kind':kind,'text':text,'references':references,'actor':actor})
    with workflow.lock(task),workflow.db.transaction():
        old=workflow.db.execute('SELECT * FROM mc_requests WHERE task_id=%s AND request_id=%s',(task,request_id)).fetchone()
        if old:
            if old['payload_sha256']!=fingerprint:raise WorkflowError('Idempotency key reused with different action')
            return old['response']
        t=workflow.task(task)
        if t['current_version']!=version:raise WorkflowError('Stale contract version')
        if t['model_approved']:raise WorkflowError('Reference changes require a new model version')
        for ref in ids:
            if not workflow.db.execute('SELECT 1 FROM mc_references WHERE task_id=%s AND version=%s AND reference_id=%s',(task,version,ref)).fetchone():
                raise WorkflowError('Reference is not bound to this task version')
        entry=workflow.record_entry(task,version=version,kind=kind,text=text,actor=actor,request_id='ref-entry-'+str(uuid.uuid4()),metadata={'external_reference_decisions':references,'model_approval':'pending'})
        identifier=str(uuid.uuid4())
        workflow.db.execute('INSERT INTO mc_reference_discussions(id,task_id,version,entry_id,decisions) VALUES(%s,%s,%s,%s,%s)',(identifier,task,version,entry['entry_id'],Jsonb(references)))
        response={'discussion_id':identifier,'entry_id':entry['entry_id'],'task_id':task,'version':version,'references':references}
        workflow.db.execute('INSERT INTO mc_requests VALUES(%s,%s,%s,%s)',(task,request_id,fingerprint,Jsonb(response)))
        return response


def source_snapshot(workflow,task,version):
    from .workflow import WorkflowError
    rows=workflow.db.execute('SELECT reference_id,payload,payload_sha256,trace_id FROM mc_references WHERE task_id=%s AND version=%s ORDER BY reference_id',(task,version)).fetchall()
    discussions=workflow.db.execute('SELECT d.id,d.entry_id,d.decisions,e.kind FROM mc_reference_discussions d JOIN mc_version_entries e ON e.id=d.entry_id WHERE d.task_id=%s AND d.version=%s ORDER BY d.sequence',(task,version)).fetchall()
    decisions={}
    for row in discussions:
        for item in row['decisions']:decisions[item['reference_id']]=item['decision']
    for row in rows:
        if digest(row['payload'])!=row['payload_sha256']:raise WorkflowError('Reference record integrity failure')
    if rows and not any(row['kind']=='proposal' for row in discussions):
        raise WorkflowError('Reference-grounded proposal discussion required before approval')
    if any(value=='considered' for value in decisions.values()):
        raise WorkflowError('Resolve considered references as adopted or rejected before approval')
    snapshot={'references':[{'reference_id':r['reference_id'],'payload_sha256':r['payload_sha256'],'trace_id':str(r['trace_id']),'decision':decisions.get(r['reference_id'],'not_adopted')} for r in rows],
              'discussion_ids':[str(d['id']) for d in discussions]}
    return {**snapshot,'sha256':digest(snapshot)}


def evidence(workflow,task,version):
    return {'mcp_traces':workflow.db.execute('SELECT * FROM mc_mcp_traces WHERE task_id=%s AND version=%s ORDER BY created_at,id',(task,version)).fetchall(),
            'references':workflow.db.execute('SELECT * FROM mc_references WHERE task_id=%s AND version=%s ORDER BY created_at,reference_id',(task,version)).fetchall(),
            'reference_discussions':workflow.db.execute('SELECT * FROM mc_reference_discussions WHERE task_id=%s AND version=%s ORDER BY sequence',(task,version)).fetchall()}
