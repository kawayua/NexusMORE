"""Business records are authoritative; graph checkpoints are repairable projections.

Every command and graph replay holds one per-task PostgreSQL session lock. Business
side effects are transactional and idempotent, then checkpoint writes occur. A crash
between them is recovered by replaying nodes against authoritative business flags.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict
import json,uuid,hashlib
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from langgraph.graph import StateGraph,START,END
from langgraph.types import interrupt,Command
from langgraph.checkpoint.postgres import PostgresSaver
from .contracts import validate,digest,bench_review,ContractError
from .config import ROOT,database_url
from .artifacts import snapshot_artifacts,same_artifacts

class WorkflowError(ValueError):pass
class State(TypedDict):
    task_id:str
    thread_id:str

class Workflow:
    def __init__(self,url=None,executors=None,mcp_client=None):
        from .executors import backends
        self.executors=backends()
        self.url=url or database_url()
        from .mcp_client import McpClient
        from .mcp_execution import McpCodeExecutor
        self.mcp=mcp_client or McpClient(database_url=self.url)
        self.executors['mcp-code-executor']=McpCodeExecutor(self)
        if executors:self.executors.update(executors)
        self.db=psycopg.connect(self.url,autocommit=True,row_factory=dict_row)
        self.cp=psycopg.connect(self.url,autocommit=True,row_factory=dict_row,prepare_threshold=0)
        self.saver=PostgresSaver(self.cp)
        self.graph=self._graph()
    def close(self):self.cp.close();self.db.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def setup(self):
        # Serialize migration/setup against concurrent CLI startups.
        self.db.execute("SELECT pg_advisory_lock(hashtext('modelcrew-stage-b-migration'))")
        try:
            with self.db.transaction():self.db.execute((ROOT/'migrations/001_stage_b.sql').read_text(encoding='utf-8-sig'))
            for migration in sorted((ROOT/'migrations').glob('[0-9]*.sql')):
                version=int(migration.name.split('_',1)[0])
                if not self.db.execute('SELECT 1 FROM mc_migrations WHERE version=%s',(version,)).fetchone():
                    with self.db.transaction():self.db.execute(migration.read_text(encoding='utf-8-sig'))
            self.saver.setup()
        finally:self.db.execute("SELECT pg_advisory_unlock(hashtext('modelcrew-stage-b-migration'))")
    @contextmanager
    def lock(self,task):
        self.db.execute('SELECT pg_advisory_lock(hashtextextended(%s,0))',(task,))
        try:yield
        finally:self.db.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))',(task,))
    def task(self,task):
        row=self.db.execute('SELECT * FROM mc_tasks WHERE id=%s',(task,)).fetchone()
        if not row:raise WorkflowError('Unknown task')
        return row
    def _event(self,task,kind,actor,payload):
        self.db.execute('INSERT INTO mc_events(task_id,kind,actor,payload) VALUES(%s,%s,%s,%s)',(task,kind,actor,Jsonb(payload)))
    def create(self,task,contract,project='bench-dragon',executor_key='historical-fixture',entries=None,executor_config=None,math_package=None):
        if executor_key not in self.executors:raise WorkflowError('Unknown execution backend')
        from .executors import prepare_config
        executor_config=prepare_config(executor_key,executor_config or {})
        validate(contract)
        if executor_key=='mcp-code-executor':
            from .mcp_execution import checked_job
            checked_job(task,1,contract,executor_config)
        if bench_review(contract)['status']=='failed':raise WorkflowError('Case-specific mathematical review failed')
        with self.lock(task),self.db.transaction():
            if self.db.execute('SELECT 1 FROM mc_tasks WHERE id=%s',(task,)).fetchone():raise WorkflowError('Task already exists')
            self.db.execute('INSERT INTO mc_projects VALUES(%s,%s) ON CONFLICT DO NOTHING',(project,'Stage B development project'))
            self.db.execute('INSERT INTO mc_tasks(id,project_id,current_version,thread_id,phase) VALUES(%s,%s,1,%s,%s)',(task,project,str(uuid.uuid4()),'WAITING_MODEL_APPROVAL'))
            self.db.execute('INSERT INTO mc_contracts(task_id,version,content,sha256,parent_version,guidance,executor_key,executor_config) VALUES(%s,1,%s,%s,NULL,%s,%s,%s)',(task,Jsonb(contract),digest(contract),'Initial proposal',executor_key,Jsonb(executor_config)))
            self.db.execute('UPDATE mc_tasks SET executor_key=%s,executor_config=%s WHERE id=%s',(executor_key,Jsonb(executor_config),task))
            if math_package is not None:
                from .mathematics import store
                store(self,task,1,math_package,'system','Initial mathematical proposal','initial')
            self._event(task,'created','system',{'contract_version':1,'mode':'pending' if executor_key in ['mcp-code-executor','pending-code'] else 'fixture','executor_key':executor_key})
            for entry in entries or []:self.record_entry(task,version=1,**entry)
        return self.resume(task)
    def _current(self,state):
        t=self.task(state['task_id'])
        if t['thread_id']!=state['thread_id']:raise WorkflowError('Obsolete graph thread fenced')
        return t
    def _graph(self):
        def route(state):
            t=self._current(state)
            if t['result_revision']>0:return 'result_gate'
            return 'model_gate'
        def model_gate(state):
            t=self._current(state)
            if not t['model_approved']:
                # Resume payload is a wake-up only; never an authorization.
                interrupt({'kind':'model','task_id':t['id'],'version':t['current_version'],'status':'WAITING_MODEL_APPROVAL'})
                t=self._current(state)
                if not t['model_approved']:raise WorkflowError('Durable user model approval missing')
            return {}
        def solve(state):
            t=self._current(state)
            if not t['model_approved']:raise WorkflowError('Model not approved')
            from .modeling_hand import assert_m1
            assert_m1(self,t)
            from .mathematics import assert_gate_binding
            assert_gate_binding(self,t,'model')
            from .dispatch import dispatch,DispatchError
            try:execution,review=dispatch(self,t)
            except DispatchError as exc:raise WorkflowError(str(exc)) from exc
            execution_id=execution['id']
            with self.db.transaction():
                self.db.execute('INSERT INTO mc_results(task_id,version,revision,execution_id,interpretation,review) VALUES(%s,%s,1,%s,%s,%s) ON CONFLICT DO NOTHING',(t['id'],t['current_version'],execution_id,t['interpretation'],Jsonb(review)))
                self.db.execute("UPDATE mc_tasks SET phase='WAITING_RESULT_APPROVAL',execution_id=%s,result_revision=1,updated_at=now() WHERE id=%s",(execution_id,t['id']))
            return {}
        def result_gate(state):
            t=self._current(state)
            if not t['result_revision']:raise WorkflowError('Missing result')
            if not t['result_approved']:
                interrupt({'kind':'result','task_id':t['id'],'version':t['current_version'],'result_revision':t['result_revision'],'mode':self.db.execute('SELECT mode FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()['mode'],'review_status':self.db.execute('SELECT review FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(t['id'],t['current_version'],t['result_revision'])).fetchone()['review']['status']})
                t=self._current(state)
                if not t['result_approved']:raise WorkflowError('Durable result approval missing')
            return {}
        def finish(state):
            t=self._current(state)
            if not t['model_approved'] or not t['result_approved']:raise WorkflowError('Both approvals required')
            from .mathematics import assert_gate_binding
            assert_gate_binding(self,t,'model');assert_gate_binding(self,t,'result')
            mode=self.db.execute('SELECT mode FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()['mode']
            with self.db.transaction():
                self.db.execute('INSERT INTO mc_summaries(task_id,version,revision,content) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(t['id'],t['current_version'],t['result_revision'],Jsonb({'kind':'confirmed_'+mode+'_summary','mode':mode,'not_paper':True,'execution_id':str(t['execution_id']),'interpretation':t['interpretation']})))
                if t['phase']!='COMPLETED':self._event(t['id'],'completed','system',{'version':t['current_version'],'revision':t['result_revision'],'mode':mode})
                self.db.execute("UPDATE mc_tasks SET phase='COMPLETED',updated_at=now() WHERE id=%s",(t['id'],))
            return {}
        graph=StateGraph(State)
        graph.add_node('model_gate',model_gate);graph.add_node('solve',solve);graph.add_node('result_gate',result_gate);graph.add_node('finish',finish)
        graph.add_conditional_edges(START,route,{'model_gate':'model_gate','result_gate':'result_gate'})
        graph.add_edge('model_gate','solve');graph.add_edge('solve','result_gate');graph.add_edge('result_gate','finish');graph.add_edge('finish',END)
        return graph.compile(checkpointer=self.saver)
    def resume(self,task):
        with self.lock(task):
            self._resume_locked(task)
            return self.inspect(task)
    def _resume_locked(self,task):
        t=self.task(task)
        # Explicit reviewed-code path: durable approval is retained, but the
        # frozen fixture/backend is not dispatched while new code is prepared.
        # This persists across restarts and is cleared by an attached real result.
        if t['model_approved'] and not t['result_revision']:
            approval=self.db.execute("SELECT payload FROM mc_events WHERE task_id=%s AND kind='model_approve' AND (payload->>'version')::integer=%s ORDER BY id DESC LIMIT 1",(task,t['current_version'])).fetchone()
            if approval and approval['payload'].get('defer_execution'):
                return
        config={'configurable':{'thread_id':t['thread_id']}}
        snapshot=self.graph.get_state(config)
        if not snapshot.values:
            self.graph.invoke({'task_id':task,'thread_id':t['thread_id']},config)
        else:
            # Resume only if the corresponding durable approval was committed.
            pending=snapshot.next
            if pending:
                ready=('model_gate' in pending and t['model_approved']) or ('result_gate' in pending and t['result_approved'])
                self.graph.invoke(Command(resume={'durable_approval':True}) if ready else None,config)
        # The graph can replay a gate from older state while business already
        # advanced. A second pass reconciles the next gate without new approval.
        t=self.task(task);snapshot=self.graph.get_state(config)
        if snapshot.next and (('model_gate' in snapshot.next and t['model_approved']) or ('result_gate' in snapshot.next and t['result_approved'])):
            self.graph.invoke(Command(resume={'durable_approval':True}),config)
    def inspect(self,task):
        t=self.task(task);v=t['current_version']
        contract=self.db.execute('SELECT * FROM mc_contracts WHERE task_id=%s AND version=%s',(task,v)).fetchone()
        result=self.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,v,t['result_revision'])).fetchone()
        execution=self.db.execute('SELECT * FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone() if t['execution_id'] else None
        state=self.graph.get_state({'configurable':{'thread_id':t['thread_id']}})
        events=self.db.execute('SELECT id,kind,actor,payload,created_at FROM mc_events WHERE task_id=%s ORDER BY id',(task,)).fetchall()
        attempts=self.db.execute('SELECT * FROM mc_backend_attempts WHERE task_id=%s AND version=%s ORDER BY id',(task,v)).fetchall()
        receipts=self.db.execute('SELECT * FROM mc_backend_receipts WHERE task_id=%s AND version=%s ORDER BY created_at',(task,v)).fetchall()
        from .mathematics import snapshot
        return {'mathematics':snapshot(self,task,v),'execution_attempts':attempts,'execution_receipts':receipts,'task':t,'contract':contract,'result':result,'execution':execution,'checkpoint_next':list(state.next),'events':events,'mode':execution['mode'] if execution else ('pending' if t['executor_key']=='mcp-code-executor' else 'fixture')}
    def action(self,task,*,actor,request_id,version,kind,decision=None,result_revision=None,reason='',contract=None,source_version=None,claims=None,structured_only=False,executor_key=None,executor_config=None,math_package=None,math_semantic_sha256=None,defer_execution=False,crash_after_commit=False):
        if defer_execution and (kind!='model' or decision!='approve'):
            raise WorkflowError('Execution deferral requires model approval')
        if not actor.strip() or not request_id.strip():raise WorkflowError('Actor and request ID required')
        if kind not in ['model','result','revise_model','revise_mathematics','revise_interpretation','restore_version']:raise WorkflowError('Unknown action')
        if kind in ['model','result'] and decision not in ['approve','reject']:raise WorkflowError('approve/reject required')
        if (decision=='reject' or kind.startswith('revise') or kind=='restore_version') and not reason.strip():raise WorkflowError('Reason or guidance required')
        if kind=='revise_model':
            validate(contract)
            if bench_review(contract)['status']=='failed':raise WorkflowError('Case mathematical check failed')
        payload={'actor':actor,'version':version,'kind':kind,'decision':decision,'result_revision':result_revision,'reason':reason,'contract':contract,'source_version':source_version}
        if defer_execution:payload['defer_execution']=True
        if math_package is not None:payload['math_package']=math_package
        if math_semantic_sha256 is not None:payload['math_semantic_sha256']=math_semantic_sha256
        if math_package is not None and kind not in ['revise_model','revise_mathematics','restore_version']:raise WorkflowError('Mathematical changes require their versioned action')
        if kind=='revise_mathematics' and (math_package is None or contract is not None):raise WorkflowError('Math revision requires a package and reuses current contract')
        if source_version is None:payload.pop('source_version')
        if executor_key is not None:payload['executor_key']=executor_key
        if executor_config is not None:payload['executor_config']=executor_config
        if (executor_key is not None or executor_config is not None) and kind not in ['revise_model','revise_mathematics','restore_version']:raise WorkflowError('Execution backend changes require a new contract version')
        if claims is not None:payload['claims']=claims
        if structured_only:payload['structured_only']=True
        if kind=='revise_interpretation':
            from .reviews import validate_claims
            if claims is not None:validate_claims(claims)
            if structured_only and claims is None:raise WorkflowError('Structured-only explanation needs claims')
        fingerprint=digest(payload)
        with self.lock(task):
            with self.db.transaction():
                old=self.db.execute('SELECT * FROM mc_requests WHERE task_id=%s AND request_id=%s',(task,request_id)).fetchone()
                if old:
                    if old['payload_sha256']!=fingerprint:raise WorkflowError('Idempotency key reused with different action')
                else:
                    t=self.task(task)
                    if t['current_version']!=version:raise WorkflowError('Stale contract version')
                    from .mathematics import approval_snapshot,latest,store,classify_change
                    if kind in ['model','result'] and decision=='approve':
                        bound=approval_snapshot(self,t,math_semantic_sha256,reason)
                        if bound is not None:
                            payload['math_snapshot']=bound
                            if kind=='result':
                                current_result=self.db.execute('SELECT * FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,version,result_revision)).fetchone()
                                if current_result is None:raise WorkflowError('Stale or nonpending result')
                                payload['math_snapshot']['result_revision']=result_revision
                                payload['math_snapshot']['execution_id']=str(current_result['execution_id'])
                                payload['math_snapshot']['result_review_sha256']=digest(current_result['review'])
                    if kind=='model':
                        if t['phase']!='WAITING_MODEL_APPROVAL' or t['model_approved']:raise WorkflowError('Not awaiting model approval')
                        if decision=='approve':
                            current_contract=self.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()['content']
                            if current_contract['schema_version']=='1.1.0':
                                from .inputs import assert_ready
                                assert_ready(current_contract)
                            from .modeling_hand import assert_m1
                            modeling_snapshot=assert_m1(self,t)
                            if modeling_snapshot is not None:payload['modeling_snapshot']=modeling_snapshot
                            from .mcp_workflow import source_snapshot
                            payload['reference_snapshot']=source_snapshot(self,task,version)
                            self.db.execute("UPDATE mc_tasks SET model_approved=true,phase='SOLVING' WHERE id=%s",(task,))
                    elif kind=='result':
                        if t['phase']!='WAITING_RESULT_APPROVAL' or t['result_approved'] or result_revision!=t['result_revision']:raise WorkflowError('Stale or nonpending result')
                        if decision=='approve':
                            review=self.db.execute('SELECT review FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(task,version,result_revision)).fetchone()['review']
                            if review.get('status')=='failed':raise WorkflowError('Failed review blocks result approval')
                            if review.get('kind')=='hand_runtime_P2':
                                from .hand_runtime import verify_result
                                verify_result(self,task,review['run_id'])
                            if review.get('kind')=='d4_P2_review':
                                from .full_result import validate_full_run
                                validate_full_run(self,task,version,ROOT/review['source_run'])
                            if review.get('kind')=='interpretation_review':
                                from .reviews import artifact_status
                                if any(artifact_status(a)!='verified' for a in review['artifacts']):raise WorkflowError('Reviewed artifacts changed; a fresh review is required')
                            if review.get('kind')=='mcp_execution_review':
                                from .reviews import artifact_status
                                outputs=self.db.execute('SELECT artifacts FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()['artifacts']
                                if any(artifact_status(a)!='verified' for a in outputs):raise WorkflowError('MCP execution artifacts changed; result approval blocked')
                            if review.get('mode')=='solver' and review['status']=='unknown' and not reason.strip():raise WorkflowError('Unknown solver review requires explicit human review reason')
                            if review.get('kind')=='interpretation_review' and review['status']=='unknown' and not reason.strip():raise WorkflowError('Unknown interpretation review requires explicit human review reason')
                            self.db.execute('UPDATE mc_tasks SET result_approved=true WHERE id=%s',(task,))
                    elif kind in ['revise_model','revise_mathematics','restore_version']:
                        previous_math=latest(self,task,version)
                        if kind=='revise_mathematics':
                            contract=self.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()['content']
                            if previous_math and classify_change(previous_math['content'],math_package)['kind']!='mathematical':raise WorkflowError('Use math presentation update for an unchanged semantic package')

                        if kind=='restore_version':
                            if source_version==version:raise WorkflowError('Source is already current; use version view')
                            original=self.db.execute('SELECT * FROM mc_contracts WHERE task_id=%s AND version=%s',(task,source_version)).fetchone()
                            if not original:raise WorkflowError('Unknown restoration source')
                            contract=original['content'];validate(contract)
                            source_math=latest(self,task,source_version)
                            if math_package is None and source_math is not None:math_package=source_math['content']
                            from .inputs import file_hash
                            for item in contract['inputs']:
                                if not Path(item['path']).is_file() or file_hash(item['path']).lower()!=item['sha256'].lower():raise WorkflowError('Restoration input missing or changed')
                        if previous_math is not None and math_package is None:raise WorkflowError('Mathematical package cannot be silently dropped in a new version')
                        from .executors import prepare_config
                        if kind=='restore_version':
                            selected_key=executor_key or original['executor_key']
                            if selected_key is None:raise WorkflowError('Legacy source has no saved execution config; select an executor explicitly')
                            selected_config=executor_config if executor_config is not None else (original['executor_config'] or {})
                        else:
                            selected_key=executor_key or t['executor_key']
                            selected_config=executor_config if executor_config is not None else (t['executor_config'] if selected_key==t['executor_key'] else {})
                        if selected_key not in self.executors:raise WorkflowError('Unknown execution backend')
                        selected_config=prepare_config(selected_key,selected_config)
                        v=version+1
                        if selected_key=='mcp-code-executor':
                            from .mcp_execution import checked_job
                            checked_job(task,v,contract,selected_config)
                        if kind=='revise_model' and selected_key==t['executor_key'] and selected_config==t['executor_config'] and digest(contract)==self.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()['sha256']:raise WorkflowError('No contract change')
                        self.db.execute('INSERT INTO mc_contracts(task_id,version,content,sha256,parent_version,guidance,restored_from_version,executor_key,executor_config) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(task,v,Jsonb(contract),digest(contract),version,reason,source_version if kind=='restore_version' else None,selected_key,Jsonb(selected_config)))
                        if math_package is not None:store(self,task,v,math_package,actor,reason,'restoration' if kind=='restore_version' else 'mathematical')
                        self.db.execute('UPDATE mc_tasks SET executor_key=%s,executor_config=%s,updated_at=now() WHERE id=%s',(selected_key,Jsonb(selected_config),task))
                        self.db.execute("UPDATE mc_tasks SET current_version=%s,thread_id=%s,phase='WAITING_MODEL_APPROVAL',model_approved=false,result_revision=0,result_approved=false,execution_id=NULL,interpretation='' WHERE id=%s",(v,str(uuid.uuid4()),task))
                    else:
                        if not t['execution_id'] or not t['model_approved']:raise WorkflowError('No confirmed calculation to reuse')
                        if result_revision!=t['result_revision']:raise WorkflowError('Stale result revision')
                        revision=t['result_revision']+1
                        from .reviews import review_interpretation
                        current_contract=self.db.execute('SELECT * FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
                        execution=self.db.execute('SELECT * FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()
                        fresh_review=review_interpretation(current_contract,execution,reason,claims,structured_only)
                        interpretation=fresh_review['interpretation']
                        self.db.execute('INSERT INTO mc_results(task_id,version,revision,execution_id,interpretation,review) VALUES(%s,%s,%s,%s,%s,%s)',(task,version,revision,t['execution_id'],interpretation,Jsonb(fresh_review)))
                        self.db.execute("UPDATE mc_tasks SET result_revision=%s,thread_id=%s,interpretation=%s,phase='WAITING_RESULT_APPROVAL',result_approved=false WHERE id=%s",(revision,str(uuid.uuid4()),interpretation,task))
                    self._event(task,kind+'_'+(decision or 'requested'),actor,payload)
                    self.db.execute('INSERT INTO mc_requests VALUES(%s,%s,%s,%s)',(task,request_id,fingerprint,Jsonb({'accepted':True,'kind':kind})))
            if crash_after_commit:raise RuntimeError('Injected crash after business commit before checkpoint')
            self._resume_locked(task)
            return self.inspect(task)

    def attach_solver_result(self,task,*,version,run_dir):
        """Register an already reviewed/executed run; never approve its result."""
        from .solver_validation import validate_run
        with self.lock(task):
            t=self.task(task)
            if t['current_version']!=version or not t['model_approved']:raise WorkflowError('Solver requires current approved contract')
            from .modeling_hand import assert_m1
            assert_m1(self,t)
            from .mathematics import assert_gate_binding
            assert_gate_binding(self,t,'model')
            contract=self.db.execute('SELECT * FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
            run=Path(run_dir).resolve()
            old=self.db.execute("SELECT * FROM mc_executions WHERE task_id=%s AND version=%s AND run_id=%s AND mode='solver'",(task,version,run.name)).fetchone()
            if run.parent==(ROOT/'stage-d/runs/full').resolve():
                from .full_result import validate_full_run
                validation,artifacts=validate_full_run(self,task,version,run)
            else:
                validation,artifacts=validate_run(run,contract['content'])
            if old:
                if not same_artifacts(old['artifacts'],artifacts):raise WorkflowError('Registered solver artifacts changed')
                self._resume_locked(task)
                return self.inspect(task)
            if t['result_approved']:raise WorkflowError('Current result already approved; revise contract or interpretation before replacement')
            artifacts=snapshot_artifacts(artifacts)
            with self.db.transaction():
                execution_id=uuid.UUID(validation['execution_id']) if validation.get('review_kind')=='d4_P2_review' else uuid.uuid4();revision=t['result_revision']+1
                if validation.get('review_kind')=='d4_P2_review' and validation['result_revision']!=revision:raise WorkflowError('D4 result revision changed')
                self.db.execute("INSERT INTO mc_executions(id,task_id,version,contract_sha256,mode,artifacts,run_id) VALUES(%s,%s,%s,%s,'solver',%s,%s)",(execution_id,task,version,contract['sha256'],Jsonb(artifacts),run.name))
                review={'status':'passed','mode':'solver','independent_validation':validation,'user_confirmation':'pending'}
                if validation.get('review_kind')=='d4_P2_review':review.update(kind='d4_P2_review',source_run=validation['source_run'],P2_receipt_sha256=validation['P2_receipt_sha256'])
                self.db.execute('INSERT INTO mc_results(task_id,version,revision,execution_id,interpretation,review) VALUES(%s,%s,%s,%s,%s,%s)',(task,version,revision,execution_id,'按确认契约实际运行并经独立核验；等待用户确认。',Jsonb(review)))
                self.db.execute("UPDATE mc_tasks SET execution_id=%s,result_revision=%s,result_approved=false,thread_id=%s,phase='WAITING_RESULT_APPROVAL',interpretation=%s,updated_at=now() WHERE id=%s",(execution_id,revision,str(uuid.uuid4()),'当前确认契约的真实求解结果；旧记录保留。',task))
                self._event(task,'solver_result_attached','system',{'version':version,'result_revision':revision,'execution_id':str(execution_id),'run_id':run.name,'contract_sha256':contract['sha256'],'not_user_approval':True})
            self._resume_locked(task)
            return self.inspect(task)

    def versions(self,task):
        self.task(task)
        return self.db.execute('SELECT version,parent_version,restored_from_version,sha256,guidance,created_at FROM mc_contracts WHERE task_id=%s ORDER BY version',(task,)).fetchall()

    def version_dossier(self,task,version=None):
        from .versions import dossier
        return dossier(self,task,version)

    def record_entry(self,task,*,version,kind,text,actor,request_id,artifacts=None,metadata=None):
        from .reviews import artifact_status
        if kind not in ['proposal','feedback','next_step','change_note','code','experiment']:raise WorkflowError('Unknown entry kind')
        if not all(isinstance(x,str) and x.strip() for x in [text,actor,request_id]):raise WorkflowError('Text, actor and request ID required')
        artifacts=artifacts or []
        body={'text':text,'artifacts':artifacts,'metadata':metadata or {}}
        payload={'version':version,'kind':'record_entry','entry_kind':kind,'actor':actor,'body':body}
        fingerprint=digest(payload)
        with self.lock(task),self.db.transaction():
            if not self.db.execute('SELECT 1 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone():raise WorkflowError('Unknown contract version')
            old=self.db.execute('SELECT * FROM mc_requests WHERE task_id=%s AND request_id=%s',(task,request_id)).fetchone()
            if old:
                if old['payload_sha256']!=fingerprint:raise WorkflowError('Idempotency key reused with different action')
                return old['response']
            for item in artifacts:
                if not isinstance(item,dict) or set(item)!={'path','sha256','role'} or artifact_status(item)!='verified':raise WorkflowError('Entry artifact missing or changed')
            body['artifacts']=snapshot_artifacts(artifacts)
            entry_id=str(uuid.uuid4())
            self.db.execute('INSERT INTO mc_version_entries(id,task_id,version,kind,body,actor,request_id) VALUES(%s,%s,%s,%s,%s,%s,%s)',(entry_id,task,version,kind,Jsonb(body),actor,request_id))
            response={'entry_id':entry_id,'task_id':task,'version':version,'kind':kind}
            self.db.execute('INSERT INTO mc_requests VALUES(%s,%s,%s,%s)',(task,request_id,fingerprint,Jsonb(response)))
            self._event(task,'version_entry_added',actor,{**response,'text':text})
            return response

    def create_project(self,project,title):
        """Idempotent creation by ID and title, with no overwrite of existing metadata."""
        if not project.strip() or not title.strip():raise WorkflowError('Project ID and title required')
        with self.db.transaction():
            self.db.execute('INSERT INTO mc_projects(id,title) VALUES(%s,%s) ON CONFLICT DO NOTHING',(project,title))
            row=self.require_project(project)
            if row['title']!=title:raise WorkflowError('Project already exists with a different title')
            return row

    def require_project(self,project):
        row=self.db.execute('SELECT id,title FROM mc_projects WHERE id=%s',(project,)).fetchone()
        if not row:raise WorkflowError('Unknown project')
        return row

    def list_projects(self,*,limit=50,offset=0):
        return self.db.execute('SELECT id,title FROM mc_projects ORDER BY id LIMIT %s OFFSET %s',(limit,offset)).fetchall()

    def list_tasks(self,project,*,limit=50,offset=0):
        self.require_project(project)
        return self.db.execute('SELECT id,project_id,current_version,phase,model_approved,result_revision,result_approved,updated_at FROM mc_tasks WHERE project_id=%s ORDER BY id LIMIT %s OFFSET %s',(project,limit,offset)).fetchall()

    def retrieve_references(self,task,**kwargs):
        from .mcp_workflow import retrieve
        return retrieve(self,task,**kwargs)

    def discuss_references(self,task,**kwargs):
        from .mcp_workflow import discussion
        return discussion(self,task,**kwargs)

    def tool_evidence(self,task,version=None):
        from .mcp_workflow import evidence
        with self.lock(task):
            t=self.task(task)
            version=t['current_version'] if version is None else version
            if not self.db.execute('SELECT 1 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone():raise WorkflowError('Unknown contract version')
            return {'task_id':task,'version':version,**evidence(self,task,version)}

    def mathematical_proposal(self,task,version=None):
        from .mathematics import snapshot
        with self.lock(task),self.db.transaction():
            t=self.task(task);v=t['current_version'] if version is None else version
            if not self.db.execute('SELECT 1 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,v)).fetchone():raise WorkflowError('Unknown contract version')
            return snapshot(self,task,v)

    def publish_mathematics(self,task,*,version,package,actor,request_id,reason,crash_after_commit=False):
        from .mathematics import latest,store,classify_change
        if not all(isinstance(x,str) and x.strip() for x in [actor,request_id,reason]):raise WorkflowError('Actor, request ID and review reason required')
        payload={'kind':'publish_mathematics','version':version,'package':package,'actor':actor,'reason':reason};fingerprint=digest(payload)
        with self.lock(task),self.db.transaction():
            old_request=self.db.execute('SELECT * FROM mc_requests WHERE task_id=%s AND request_id=%s',(task,request_id)).fetchone()
            if old_request:
                if old_request['payload_sha256']!=fingerprint:raise WorkflowError('Idempotency key reused with different action')
                response=old_request['response']
            else:
                t=self.task(task)
                if version!=t['current_version']:raise WorkflowError('Stale contract version')
                old=latest(self,task,version)
                if old is None:
                    if t['model_approved'] or t['execution_id'] or t['phase']!='WAITING_MODEL_APPROVAL':raise WorkflowError('Already approved version requires a new mathematical business version')
                    change={'kind':'initial','changes':[]}
                else:
                    change=classify_change(old['content'],package)
                    if change['kind']=='mathematical':raise WorkflowError('Mathematical changes require revise_mathematics and new approval')
                if change['kind']!='unchanged':store(self,task,version,package,actor,reason,change['kind'])
                from .mathematics import snapshot
                proposal=snapshot(self,task,version)
                response={k:proposal[k] for k in ['task_id','version','revision','semantic_sha256','package_sha256','proposal_sha256']}
                response['change']=change
                self._event(task,'mathematics_published',actor,{**response,'reason':reason})
                self.db.execute('INSERT INTO mc_requests VALUES(%s,%s,%s,%s)',(task,request_id,fingerprint,Jsonb(response)))
        if crash_after_commit:raise RuntimeError('Injected crash after mathematical publish commit')
        return response


    def run_modeling(self,task,**kwargs):
        from .modeling_hand import run
        return run(self,task,**kwargs)

    def modeling_status(self,task):
        from .modeling_hand import status
        return status(self,task)


    def recheck_modeling(self,task,**kwargs):
        from .modeling_hand import recheck
        return recheck(self,task,**kwargs)


    def question_intake(self,**kwargs):
        from .question_references import intake
        return intake(self,**kwargs)

    def attach_question_reference(self,**kwargs):
        from .question_references import attach
        return attach(self,**kwargs)

    def question_context(self,**kwargs):
        from .question_references import consume
        return consume(self,**kwargs)

    def start_hand(self,task,hand,**kwargs):
        from .hand_runtime import start
        return start(self,task,hand,**kwargs)

    def advance_hand(self,task,run_id,**kwargs):
        from .hand_runtime import advance
        return advance(self,task,run_id,**kwargs)

    def hand_status(self,task,run_id):
        from .hand_runtime import status
        return status(self,task,run_id)

    def hand_decision(self,task,run_id,**kwargs):
        from .hand_runtime import decision
        return decision(self,task,run_id,**kwargs)


    def recheck_hand(self,task,run_id,**kwargs):
        from .hand_runtime import recheck
        return recheck(self,task,run_id,**kwargs)

    def start_assembly(self, project, **kwargs):
        from .assembly_runtime import start
        return start(self, project, **kwargs)

    def rebind_assembly(self, project, run_id, **kwargs):
        from .assembly_binding import rebind
        return rebind(self, project, run_id, **kwargs)

    def assembly_status(self, project, run_id):
        from .assembly_runtime import status
        return status(self, project, run_id)

    def compose_assembly(self, project, run_id, **kwargs):
        from .assembly_builds import compose
        return compose(self, project, run_id, **kwargs)

    def assembly_build_status(self, project, build_id):
        from .assembly_builds import status
        return status(self, project, build_id)

    def assembly_build_decision(self, project, build_id, **kwargs):
        from .assembly_builds import decision
        return decision(self, project, build_id, **kwargs)

    def bind_assembly_reviews(self, project, build_id, **kwargs):
        from .assembly_builds import bind_reviews
        return bind_reviews(self, project, build_id, **kwargs)

    def export_assembly(self, project, build_id, **kwargs):
        from .assembly_builds import export
        return export(self, project, build_id, **kwargs)

    def render_assembly(self, project, build_id, **kwargs):
        from .assembly_builds import render
        return render(self, project, build_id, **kwargs)

    def review_assembly_w2(self, project, build_id, **kwargs):
        from .assembly_w2 import start
        return start(self, project, build_id, **kwargs)

    def retry_assembly_w2_delivery(self, project, build_id, review_request_id, **kwargs):
        from .assembly_w2 import retry_delivery
        return retry_delivery(self, project, build_id, review_request_id, **kwargs)

    def recover_assembly(self, project, build_id):
        from .assembly_builds import recover
        return recover(self, project, build_id)
