"""Explicit local operator repair; never resets the automatic author budget."""
import ast
import json
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from . import hand_runtime as hr
from .collaboration import sha_file, workspace_path
from .config import ROOT
from .contracts import digest
from .workflow import WorkflowError


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    stage: Literal["minimal", "full"] = "minimal"
    version: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_.-]+$')
    statement: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=20000)
    code_path: str = Field(min_length=1, max_length=2000)
    code_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    previous_code_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def repair(w, task, run_id, **kwargs):
    req = RepairRequest(**kwargs)
    if not all(v.strip() for v in (req.actor, req.statement, req.rationale)):
        raise WorkflowError('Explicit operator repair evidence required')
    with w.lock(task):
        row = hr.load(w, task, run_id)
        hr.guard(w, row)
        p = row['payload']
        fingerprint = digest(req.model_dump(exclude={"stage"}) if req.stage == "minimal" else req.model_dump())
        repairs = p.get('operator_repairs', {})
        if req.request_id in repairs:
            if repairs[req.request_id]['request_sha256'] != fingerprint:
                raise WorkflowError('Repair idempotency key conflict')
            return hr.status(w, task, run_id)
        from .numeric_test_scope import validate as numeric_test_scope,pre_p2_figure_failure
        scoped_failure=req.stage=='full' and numeric_test_scope(row) is not None and pre_p2_figure_failure(row)
        if (req.version != row['version'] or row['hand'] != 'coding'
                or row['phase'] != 'NEEDS_HUMAN' or p['retries'] != 3
                or (not scoped_failure and (p.get('failure_domain') != 'implementation'
                or p.get('rework_target') != 'coding')) or p.get('attached')
                or w.task(task)['result_revision']):
            raise WorkflowError('Repair requires exhausted coding implementation failure')
        if req.stage == 'minimal':
            if p.get('full_packet') or any(k.startswith('full-') for k in p.get('jobs', {})):
                raise WorkflowError('Repair requires exhausted minimal coding implementation failure')
        else:
            # Full-only repair cannot weaken the already accepted minimal gate.
            from .collaboration import CollaborationStore, Receipt
            key = p.get('accepted_reviews', {}).get('P1')
            accepted = p.get('reviews', {}).get(key)
            if not accepted or accepted['status'] != 'PASS' or not p.get('full_code_path'):
                raise WorkflowError('Full repair requires accepted independent P1 and previous full source')
            store = CollaborationStore(hr.run_folder(row)/'records')
            receipt = store.load(Receipt, accepted['receipt_sha256'])
            if receipt.status != 'PASS' or store.accept_review(receipt, accepted['snapshot_sha256']) != accepted['receipt_sha256']:
                raise WorkflowError('Full repair P1 receipt invalid')
        previous = workspace_path(ROOT, p[req.stage + '_code_path'])
        if sha_file(previous) != req.previous_code_sha256:
            raise WorkflowError('Repair previous code hash differs')
        source = workspace_path(ROOT, req.code_path)
        if source.is_symlink() or source.is_junction() or source.stat().st_size > 500000:
            raise WorkflowError('Unsafe or oversized repair code')
        if sha_file(source) != req.code_sha256:
            raise WorkflowError('Repair code hash differs')
        code = source.read_bytes().decode('utf-8')
        if not code.strip():raise WorkflowError('Empty repair code')
        ast.parse(code)
        compile(code, '<operator-solver>', 'exec', dont_inherit=True)  # Never execute on host.
        key = uuid.uuid5(uuid.UUID(str(row['id'])), req.request_id).hex
        folder = hr.run_folder(row)
        target = folder / (req.stage + '-repair-' + key + '.py')
        if not target.exists():
            with target.open('x', encoding='utf-8', newline='') as stream:stream.write(code)
        if sha_file(target) != req.code_sha256:
            raise WorkflowError('Repair artifact changed')
        manifest = folder / ('operator-repair-' + key + '.json')
        record = {'request':req.model_dump(), 'request_sha256':fingerprint,
                  'binding':p['binding'], 'previous_attempt':p['attempt'],
                  'attempt':p['attempt'] + 1, 'automatic_retries':p['retries'],
                  'previous_review':p.get('last_review'),
                  'code_path':hr.rel(target), 'origin':'operator_supplied_code',
                  'call_id':'operator-repair-' + key, 'context_id':str(uuid.uuid5(uuid.UUID(key),'author')),
                  'stage':req.stage,
                  'scope':('minimal only; new Docker execution and independent P1 required' if req.stage=='minimal' else
                           'full only; preserve accepted P1; new full execution, reproduction and independent P2 required') + '; no user result approval'}
        if not manifest.exists():hr.write(manifest, record)
        if hr.read(manifest) != record:raise WorkflowError('Repair recovery manifest differs')
        hr.seal(row, target);hr.seal(row, manifest);hr.seal(row, source)
        hr.author(row, record)
        p.setdefault('operator_repairs', {})[req.request_id] = record
        p.update(attempt=record['attempt'])
        p[req.stage + '_code'] = code
        p[req.stage + '_code_path'] = hr.rel(target)
        if req.stage == 'minimal':
            p['accepted_reviews'] = {}
        else:
            p['accepted_reviews'].pop('P2', None)
            for name in ('full_packet', 'replica_packet', 'figure_check', 'figure_catalog'):
                p.pop(name, None)
        for name in ('review_suffix','recheck_rationale','failure_domain','rework_target'):
            p.pop(name, None)
        hr.save(w, row, 'EXECUTE_FULL' if req.stage=='full' else 'EXECUTE_MINIMAL')
        return hr.status(w, task, run_id)


def recover_nonfinite_output(w, task, run_id, *, version, actor, request_id, statement):
    """Local operator recovery for the historical nonfinite-packet classification bug.

    Proves the failure from the existing immutable job and completed receipt; does
    not dispatch execution, reset retries, alter outputs, or grant any approval.
    """
    import re
    if (not isinstance(version, int) or isinstance(version, bool)
            or not all(isinstance(x, str) and x.strip() for x in (actor, request_id, statement))
            or len(actor)>200 or len(statement)>2000
            or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',request_id)):
        raise WorkflowError('Explicit local recovery evidence required')
    with w.lock(task):
        row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload']
        body=dict(version=version,actor=actor,request_id=request_id,statement=statement)
        prior=p.get('nonfinite_recoveries',{}).get(request_id)
        if prior:
            if prior['request']!=body:raise WorkflowError('Recovery idempotency key conflict')
            return hr.status(w,task,run_id)
        if (version!=row['version'] or row['hand']!='coding' or row['phase']!='NEEDS_HUMAN'
                or p.get('failure_domain')!='infrastructure' or p.get('rework_target')!='recovery'
                or p.get('error_type')!='ValueError' or p.get('retries')!=3
                or p.get('attached') or w.task(task)['result_revision']
                or p.get('full_packet') or any(k.startswith('full-') for k in p.get('jobs',{}))):
            raise WorkflowError('Recovery requires exhausted historical minimal packet failure')
        key='minimal-'+str(p['attempt']);saved=p.get('jobs',{}).get(key)
        if not saved or saved.get('dispatched') is not True:
            raise WorkflowError('No dispatched current execution to recover')
        root=hr.executor_root();job=saved['job'];jid=job['job_id']
        _,registered=hr.DockerExecutor(root).job(jid)
        auth=dict(mode='workflow',task_id=task,version=version,contract_sha256=p['binding']['contract_sha256'])
        source=workspace_path(ROOT,p['minimal_code_path'])
        if (registered!=job or job['authorization']!=auth or job['code_sha256']!=sha_file(source)):
            raise WorkflowError('Recovery job identity differs')
        receipt=hr.read(root/'runs'/jid/'result.json')
        if (receipt.get('status')!='succeeded' or receipt.get('cleanup',{}).get('removed') is not True
                or any(receipt.get(k)!=job[k] for k in ('job_sha256','code_sha256','authorization'))
                or receipt.get('run_id')!=jid):
            raise WorkflowError('No matching completed execution receipt')
        invalid=[]
        for item in receipt.get('artifacts',[]):
            path=(root/item['path']).resolve()
            if (not path.is_relative_to((root/'runs'/jid/'artifacts').resolve())
                    or path.is_symlink() or path.is_junction()
                    or path.stat().st_size!=item['size_bytes'] or sha_file(path)!=item['sha256']):
                raise WorkflowError('Recovery output differs')
            if path.suffix=='.json':
                value=hr.read(path)  # Malformed JSON is outside this narrow recovery.
                try:json.dumps(value,allow_nan=False)
                except ValueError:invalid.append(dict(path=hr.rel(path),sha256=item['sha256']))
        if not invalid:raise WorkflowError('No nonfinite JSON evidence; recovery refused')
        record=dict(request=body,binding=p['binding'],attempt=p['attempt'],automatic_retries=p['retries'],
                    previous_failure_domain=p['failure_domain'],job_sha256=job['job_sha256'],
                    receipt_sha256=sha_file(root/'runs'/jid/'result.json'),invalid_artifacts=invalid,
                    effect='Reclassify output failure only; no execution, approval or budget reset')
        target=hr.run_folder(row)/('nonfinite-recovery-'+uuid.uuid5(uuid.UUID(str(row['id'])),request_id).hex+'.json')
        if not target.exists():hr.write(target,record)
        if hr.read(target)!=record:raise WorkflowError('Recovery evidence differs')
        hr.seal(row,target)
        p.setdefault('nonfinite_recoveries',{})[request_id]=record
        p.update(failure_domain='implementation',rework_target='coding',
                 feedback=dict(error='Invalid or non-finite JSON output',artifacts=invalid))
        hr.save(w,row,'NEEDS_HUMAN')
        return hr.status(w,task,run_id)


class RejectedP1RepairRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    version: int = Field(ge=1)
    actor: str = Field(min_length=1,max_length=200)
    request_id: str = Field(min_length=1,max_length=200,pattern=r'^[A-Za-z0-9_.-]+$')
    statement: str = Field(min_length=1,max_length=2000)
    rationale: str = Field(min_length=1,max_length=2000)


def retry_after_invalid_p1(w,task,run_id,**kwargs):
    """Local explicit author rework, spending existing budget, never a re-review.

    Only a completed, provably inadmissible P1 can be abandoned. It remains
    NOT_ADMITTED, not rewritten as an accepted FAIL/PASS. Future code still
    requires a new actual execution and independent P1.
    """
    req=RejectedP1RepairRequest(**kwargs)
    if not all(x.strip() for x in (req.actor,req.statement,req.rationale)):
        raise WorkflowError('Explicit local repair evidence required')
    with w.lock('business:task:'+task),w.lock(task):
        from .business_store import BusinessStore
        if BusinessStore(w.db).unresolved('task:'+task):
            raise WorkflowError('Resolve the business operation fence before author rework')
        row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload'];fingerprint=digest(req.model_dump())
        prior=p.get('invalid_p1_repairs',{}).get(req.request_id)
        if prior:
            if prior['request_sha256']!=fingerprint:raise WorkflowError('Repair idempotency key conflict')
            return hr.status(w,task,run_id)
        last=p.get('last_review',{});key=last.get('stage_key')
        if (req.version!=row['version'] or row['hand']!='coding' or row['phase']!='NEEDS_HUMAN'
                or p.get('failure_domain')!='review_output' or not hr.recheck_attempt_usage(p)['used_this_attempt']
                or not 0<=p['retries']<3 or last.get('gate')!='P1' or last.get('attempt')!=p['attempt']
                or key in p.get('reviews',{}) or p.get('attached') or w.task(task)['result_revision']
                or p.get('full_packet') or any(k.startswith('full-') for k in p.get('jobs',{}))):
            raise WorkflowError('Repair requires unadmitted minimal P1, spent recheck and remaining author budget')
        op=p.get('ops',{}).get(key);folder=hr.run_folder(row)
        answer_path=folder/'operations'/key/'answer.json'
        if not op or op.get('state')!='completed' or sha_file(answer_path)!=op.get('answer_sha256'):
            raise WorkflowError('No complete unchanged reviewer answer')
        raw=hr.read(answer_path);answer=hr.M1Answer.model_validate(raw)
        ident=hr.read(folder/(key+'-identity.json'))
        store=hr.CollaborationStore(folder/'records');tickets=[]
        for path in (folder/'records'/'Ticket').glob('*.json'):
            ticket=hr.Ticket.model_validate(hr.read(path))
            if ticket.reviewer_call_id==ident['call_id'] and ticket.gate=='P1':
                tickets.append((path.stem,ticket))
        if len(tickets)!=1:raise WorkflowError('No unique original review ticket')
        ticket_sha,ticket=tickets[0]
        if (store.dispatch_review(ticket.snapshot_sha256,'P1',ticket.reviewer_call_id,_persist=False)!=ticket_sha
                or ticket.binding.model_dump()!=hr.Binding.model_validate(p['binding']).model_dump()):
            raise WorkflowError('Original review binding differs')
        snapshot=store.load(hr.Snapshot,ticket.snapshot_sha256)
        evidence={a.artifact_id:hr.read(workspace_path(ROOT,a.path)) for a in snapshot.artifacts}
        invalid=[]
        for check in answer.checks:
            for proof in check.evidence:
                if proof.artifact_id not in evidence:
                    invalid.append(dict(artifact_id=proof.artifact_id,selector=proof.selector));continue
                try:hr.pointer(evidence[proof.artifact_id],proof.selector)
                except ValueError:invalid.append(dict(artifact_id=proof.artifact_id,selector=proof.selector))
        missing=[c.check_id for c in answer.checks if c.status!='PASS' and not any(i.check_id==c.check_id for i in answer.issues)]
        if not invalid and not missing:raise WorkflowError('No proven pointer or issue-coverage admission error')
        record=dict(request=req.model_dump(),request_sha256=fingerprint,binding=p['binding'],
                    previous_attempt=p['attempt'],attempt=p['attempt']+1,previous_retries=p['retries'],
                    automatic_retries=p['retries']+1,review_stage=key,review_status='NOT_ADMITTED',
                    reviewer_answer_sha256=op['answer_sha256'],ticket_sha256=ticket_sha,
                    snapshot_sha256=ticket.snapshot_sha256,invalid_pointers=invalid,missing_issue_check_ids=missing,
                    effect='Spend one existing author retry; no new reviewer call, no accepted receipt or approval')
        target=folder/('invalid-p1-repair-'+uuid.uuid5(uuid.UUID(str(row['id'])),req.request_id).hex+'.json')
        if not target.exists():hr.write(target,record)
        if hr.read(target)!=record:raise WorkflowError('Repair evidence differs')
        hr.seal(row,target);hr.seal(row,answer_path)
        p.setdefault('invalid_p1_repairs',{})[req.request_id]=record
        p['review_pointer_protocol']='exact-v1'
        feedback=dict(reason=req.rationale,review_status='NOT_ADMITTED',admission_errors=dict(
                      invalid_pointers=invalid,missing_issue_check_ids=missing),
                      unadmitted_reviewer_response=raw,
                      actual_minimal_output=evidence.get('result'),
                      requirement='Repair the actual numerical failure; no invented checks, threshold changes, or fake PASS. New Docker execution and independent P1 remain mandatory.')
        hr.rework(w,row,feedback,'coding')
        return hr.status(w,task,run_id)
