"""Explicit local operator repair; never resets the automatic author budget."""
import ast
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
        if (req.version != row['version'] or row['hand'] != 'coding'
                or row['phase'] != 'NEEDS_HUMAN' or p['retries'] != 3
                or p.get('failure_domain') != 'implementation'
                or p.get('rework_target') != 'coding' or p.get('attached')
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
        ast.parse(code)  # Static parsing only; execution stays in Docker.
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
