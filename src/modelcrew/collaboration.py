"""D1 handoff contracts and deterministic QA admission, not an LLM agent runner.

Call identities are supplied by the trusted orchestrator. These records enforce
consistency, not authentication or OS/process isolation. No API approval is minted.
"""
from __future__ import annotations
from .project_assets import asset_path,input_path

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import ROOT
from .contracts import digest

_historical_review_workflow = ContextVar('historical_review_workflow', default=None)
_historical_paper_policy = ContextVar('historical_paper_policy', default=None)

def historical_paper_policy_sha256():
    return _historical_paper_policy.get()

@contextmanager
def historical_review_context(workflow_sha256, paper_policy_sha256=None):
    """Scoped read-only receipt verification; never affects another request/thread."""
    token = _historical_review_workflow.set(workflow_sha256)
    paper_token = _historical_paper_policy.set(paper_policy_sha256)
    try:
        yield
    finally:
        _historical_paper_policy.reset(paper_token)
        _historical_review_workflow.reset(token)

Text = Annotated[str, Field(min_length=1, max_length=300)]
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Hand = Literal['modeling', 'coding', 'writing']
Gate = Literal['M1', 'P1', 'P2', 'W1', 'W2']
Status = Literal['PASS', 'FAIL', 'BLOCKED']
Kind = Literal['task_graph', 'source', 'method_selection', 'contract', 'mathematics',
               'code', 'input', 'execution', 'result', 'figure', 'reproduction',
               'outline', 'manuscript', 'figure_selection', 'render']

from .hand_contracts import (RESPONSIBILITIES, TOOLS, OUTPUTS, GATE_HAND,
                             REQUIRED_CHECKS)


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, str_strip_whitespace=True)
    schema_version: Literal['1.0.0'] = '1.0.0'


class Binding(Record):
    task_id: Text
    contract_version: int = Field(ge=1)
    contract_sha256: Hash
    execution_id: Text | None = None
    result_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def result_needs_execution(self):
        if self.result_revision is not None and self.execution_id is None:
            raise ValueError('Result revision requires execution_id')
        return self


class Call(Record):
    call_id: Text
    context_id: Text
    role: Literal['modeling', 'coding', 'writing', 'quality']
    binding: Binding


class Artifact(Record):
    artifact_id: Text
    kind: Kind
    path: Text
    sha256: Hash
    author_call_ids: list[Text] = Field(min_length=1)


class Snapshot(Record):
    binding: Binding
    hand: Hand
    artifacts: list[Artifact] = Field(min_length=1)
    # Include earlier authors/editors even when an artifact has been replaced.
    lineage_call_ids: list[Text] = Field(min_length=1)


class Handoff(Record):
    sender: Hand
    recipient: Hand
    snapshot_sha256: Hash
    binding: Binding
    artifact_ids: list[Text] = Field(min_length=1)


class Ticket(Record):
    gate: Gate
    snapshot_sha256: Hash
    binding: Binding
    reviewer_call_id: Text
    required_checks: list[Text] = Field(min_length=1)
    policy_sha256: Hash


class Evidence(Record):
    artifact_id: Text
    selector: Text  # e.g. line range, JSON pointer, table row/column, rendered page


class Check(Record):
    check_id: Text
    status: Status
    evidence: list[Evidence] = Field(default_factory=list)
    explanation: Text


class Issue(Record):
    check_id: Text
    severity: Literal['error', 'warning', 'blocking']
    domain: Literal['model', 'implementation', 'explanation', 'writing', 'infrastructure']
    target: Literal['modeling', 'coding', 'writing', 'recovery']
    reason: Text
    recheck: Text


class Receipt(Record):
    ticket_sha256: Hash
    reviewer_call_id: Text
    status: Status
    checks: list[Check] = Field(min_length=1)
    issues: list[Issue] = Field(default_factory=list)


def sha_file(path):
    return hashlib.sha256(input_path(path).read_bytes()).hexdigest()


def unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError('Duplicate ' + label)


def workspace_path(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or ':' in relative or '\\' in relative:
        raise ValueError('Expected workspace-relative POSIX path')
    result = (root / path).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Path escapes workspace')
    return asset_path(root,relative)


def collaboration_policy(root=ROOT):
    config = json.loads((asset_path(root,'resources/paper/workflow.json')).read_text(encoding='utf-8'))
    policy = config['collaboration']
    actual = {item['id']: item['responsibility_labels'] for item in policy['primary_agents']}
    if actual != RESPONSIBILITIES or len(policy['primary_agents']) != 3:
        raise ValueError('Unsupported three-hand responsibility mapping')
    qa = policy['quality_checks']
    if (qa['mode'] != 'temporary_read_only_independent_calls'
            or qa['resident_business_agents'] is not False
            or qa['author_context_must_not_review_own_artifact'] is not True
            or qa['reviewer_must_not_modify_authoritative_artifact'] is not True
            or qa['gates'] != {'M1': 'Validator', 'P1': 'Reviewer', 'P2': 'Reviewer', 'W1': 'Reviewer', 'W2': 'Reviewer'}):
        raise ValueError('Independent QA policy required')
    return {'workflow_version': config['workflow_version'], 'workflow_sha256': sha_file(asset_path(root,'resources/paper/workflow.json')),
            'policy': policy, 'tools': {k: sorted(v) for k, v in TOOLS.items()},
            'outputs': {k: sorted(v) for k, v in OUTPUTS.items()}}


def require_tool(call: Call, tool: str):
    """Capability admission only; actual tool adapters must invoke this guard."""
    if tool not in TOOLS[call.role]:
        raise ValueError('Tool forbidden for ' + call.role)


class CollaborationStore:
    """Immutable content-addressed D1 records, separate from historical B/C DB.

    The directory is a local audit store. D2+ will integrate authoritative user
    approvals and checkpoints; no handoff or PASS here advances those systems.
    """
    def __init__(self, directory: Path, root=ROOT):
        self.root = root.resolve()
        self.directory = Path(directory).resolve()
        if not self.directory.is_relative_to(self.root):
            raise ValueError('Record store must be within workspace')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.policy = collaboration_policy()  # project policy, even in fixture workspaces

    def save(self, record: Record):
        if self.directory.is_relative_to(self.root/'archive'):
            raise ValueError('Historical archive is read-only; use a new current run')
        payload = record.model_dump(mode='json')
        key = digest(payload)
        folder = self.directory / type(record).__name__
        folder.mkdir(exist_ok=True)
        destination = folder / (key + '.json')
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
        fd, name = tempfile.mkstemp(dir=folder, prefix='.pending-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(name, destination)
            except FileExistsError:
                if destination.read_bytes() != data:
                    raise ValueError('Immutable record corrupted')
        finally:
            Path(name).unlink(missing_ok=True)
        return key

    def load(self, kind, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid record key')
        data = json.loads((self.directory / kind.__name__ / (key + '.json')).read_text(encoding='utf-8'))
        if digest(data) != key:
            raise ValueError('Record hash mismatch')
        return kind.model_validate(data)

    def register_call(self, call: Call):
        # Atomic unique call_id claim, including across concurrent orchestrators.
        call = Call.model_validate(call.model_dump(mode='json'))
        binding_key = self.save(call.binding)
        contexts = self.directory / 'ContextBinding'
        contexts.mkdir(exist_ok=True)
        context_path = contexts / (digest(call.context_id) + '.json')
        try:
            os.link(self.directory / 'Binding' / (binding_key + '.json'), context_path)
        except FileExistsError:
            previous_binding = Binding.model_validate_json(context_path.read_text(encoding='utf-8'))
            if previous_binding != call.binding:
                raise ValueError('Context already bound to another task/version')
        key = self.save(call)
        folder = self.directory / 'CallIdentity'
        folder.mkdir(exist_ok=True)
        identity = folder / (digest(call.call_id) + '.json')
        try:
            os.link(self.directory / 'Call' / (key + '.json'), identity)
        except FileExistsError:
            previous = Call.model_validate_json(identity.read_text(encoding='utf-8'))
            if previous != call:
                raise ValueError('Call identity already registered')
        return key

    def call(self, call_id):
        path = self.directory / 'CallIdentity' / (digest(call_id) + '.json')
        if not path.exists():
            raise ValueError('Unknown call identity')
        payload = json.loads(path.read_text(encoding='utf-8'))
        call = self.load(Call, digest(payload))
        if call.call_id != call_id:
            raise ValueError('Call identity mismatch')
        return call

    def validate_snapshot(self, snapshot: Snapshot):
        unique([a.artifact_id for a in snapshot.artifacts], 'artifact IDs')
        unique(snapshot.lineage_call_ids, 'lineage calls')
        for call_id in snapshot.lineage_call_ids:
            call = self.call(call_id)
            if (call.binding.task_id != snapshot.binding.task_id
                    or call.binding.contract_version != snapshot.binding.contract_version
                    or call.binding.contract_sha256 != snapshot.binding.contract_sha256
                    or (call.binding.execution_id is not None and call.binding.execution_id != snapshot.binding.execution_id)
                    or (call.binding.result_revision is not None and call.binding.result_revision != snapshot.binding.result_revision)):
                raise ValueError('Contributor binding mismatch')
        for artifact in snapshot.artifacts:
            unique(artifact.author_call_ids, 'artifact authors')
            if not set(artifact.author_call_ids) <= set(snapshot.lineage_call_ids):
                raise ValueError('Artifact authors absent from lineage')
            if sha_file(workspace_path(self.root, artifact.path)) != artifact.sha256:
                raise ValueError('Artifact missing or changed')
            if artifact.kind == 'contract':
                contract = json.loads(workspace_path(self.root, artifact.path).read_text(encoding='utf-8-sig'))
                if digest(contract) != snapshot.binding.contract_sha256:
                    raise ValueError('Contract content does not match binding')
            for author in artifact.author_call_ids:
                call = self.call(author)
                if call.role == 'quality':
                    raise ValueError('Read-only reviewer cannot author artifacts')
                # Inputs and external source excerpts can be registered by any hand.
                if artifact.kind not in {'source', 'input'} and artifact.kind not in OUTPUTS[call.role]:
                    raise ValueError('Artifact outside author responsibility')
        return snapshot

    def freeze(self, snapshot: Snapshot):
        snapshot = Snapshot.model_validate(snapshot.model_dump(mode='json'))
        self.validate_snapshot(snapshot)
        return self.save(snapshot)

    def handoff(self, key, recipient: Hand, artifact_ids):
        snapshot = self.validate_snapshot(self.load(Snapshot, key))
        if (snapshot.hand, recipient) not in {('modeling', 'coding'), ('coding', 'writing')}:
            raise ValueError('Unsupported handoff route')
        unique(artifact_ids, 'handoff artifacts')
        available = {a.artifact_id: a for a in snapshot.artifacts}
        if not artifact_ids or not set(artifact_ids) <= available.keys():
            raise ValueError('Unknown or empty handoff artifacts')
        needed = {'coding': {'contract', 'input'}, 'writing': {'contract', 'execution', 'result'}}[recipient]
        if not needed <= {available[i].kind for i in artifact_ids}:
            raise ValueError('Required handoff inputs missing')
        return self.save(Handoff(sender=snapshot.hand, recipient=recipient,
                                 snapshot_sha256=key, binding=snapshot.binding, artifact_ids=artifact_ids))

    def context(self, handoff_key, call_id):
        packet = self.load(Handoff, handoff_key)
        snapshot = self.validate_snapshot(self.load(Snapshot, packet.snapshot_sha256))
        call = self.call(call_id)
        if call.role != packet.recipient or call.binding != packet.binding or snapshot.binding != packet.binding:
            raise ValueError('Context recipient or version mismatch')
        if snapshot.hand != packet.sender:
            raise ValueError('Context sender mismatch')
        if self.handoff(packet.snapshot_sha256, packet.recipient, packet.artifact_ids) != handoff_key:
            raise ValueError('Handoff manifest mismatch')
        artifacts = {a.artifact_id: a for a in snapshot.artifacts}
        # Explicit file list; never import chat histories or adjacent directories.
        return {'call': call.model_dump(mode='json'), 'handoff_sha256': handoff_key,
                'tools': sorted(TOOLS[call.role]),
                'artifacts': [artifacts[i].model_dump(mode='json') for i in packet.artifact_ids],
                'requires_authoritative_user_approval': True,
                'workflow_sha256': collaboration_policy()['workflow_sha256']}

    def dispatch_review(self, snapshot_key, gate: Gate, reviewer_call_id, *, _policy_sha256=None, _persist=True):
        if gate not in REQUIRED_CHECKS:
            raise ValueError('Unknown QA gate')
        snapshot = self.validate_snapshot(self.load(Snapshot, snapshot_key))
        reviewer = self.call(reviewer_call_id)
        if reviewer.role != 'quality' or reviewer.binding != snapshot.binding:
            raise ValueError('Reviewer role or binding mismatch')
        if snapshot.hand != GATE_HAND[gate]:
            raise ValueError('Gate belongs to another hand')
        needed = {'M1': {'contract', 'mathematics'}, 'P1': {'code', 'input', 'execution', 'result'},
                  'P2': {'code', 'input', 'execution', 'result', 'figure', 'reproduction'},
                  'W1': {'outline', 'contract', 'execution', 'result'},
                  'W2': {'manuscript', 'render', 'figure'}}[gate]
        if not needed <= {a.kind for a in snapshot.artifacts}:
            raise ValueError('Gate evidence package incomplete')
        if gate != 'M1' and (snapshot.binding.execution_id is None or snapshot.binding.result_revision is None):
            raise ValueError('Result review requires execution and revision binding')
        if not any(self.call(c).role == snapshot.hand for a in snapshot.artifacts for c in a.author_call_ids):
            raise ValueError('Snapshot has no author from responsible hand')
        contexts = {self.call(c).context_id for c in snapshot.lineage_call_ids}
        if reviewer.context_id in contexts or reviewer.call_id in snapshot.lineage_call_ids:
            raise ValueError('Reviewer participated in authorship or revision')
        ticket = Ticket(gate=gate, snapshot_sha256=snapshot_key, binding=snapshot.binding,
                        reviewer_call_id=reviewer_call_id, required_checks=REQUIRED_CHECKS[gate],
                        policy_sha256=_policy_sha256 or collaboration_policy()['workflow_sha256'])
        return self.save(ticket) if _persist else digest(ticket.model_dump(mode='json'))

    def accept_review(self, receipt: Receipt, current_snapshot_key, *, historical_workflow_sha256=None):
        historical_workflow_sha256 = historical_workflow_sha256 or _historical_review_workflow.get()
        receipt = Receipt.model_validate(receipt.model_dump(mode='json'))
        ticket = self.load(Ticket, receipt.ticket_sha256)
        if ticket.snapshot_sha256 != current_snapshot_key:
            raise ValueError('Stale review snapshot')
        # Recheck identity, provenance and file bytes at receipt admission.
        if self.dispatch_review(current_snapshot_key, ticket.gate, ticket.reviewer_call_id,
                                _policy_sha256=historical_workflow_sha256, _persist=False) != receipt.ticket_sha256:
            raise ValueError('Review ticket mismatch')
        if receipt.reviewer_call_id != ticket.reviewer_call_id:
            raise ValueError('Wrong reviewer')
        unique([c.check_id for c in receipt.checks], 'check IDs')
        if {c.check_id for c in receipt.checks} != set(ticket.required_checks):
            raise ValueError('Incomplete or unexpected check coverage')
        snapshot = self.load(Snapshot, current_snapshot_key)
        artifact_ids = {a.artifact_id for a in snapshot.artifacts}
        for check in receipt.checks:
            if check.status == 'PASS' and not check.evidence:
                raise ValueError('PASS requires evidence')
            if any(e.artifact_id not in artifact_ids for e in check.evidence):
                raise ValueError('Unknown evidence artifact')
        expected = ('FAIL' if any(c.status == 'FAIL' for c in receipt.checks) else
                    'BLOCKED' if any(c.status == 'BLOCKED' for c in receipt.checks) else 'PASS')
        if receipt.status != expected:
            raise ValueError('Receipt status contradicts checks')
        checks = {c.check_id: c for c in receipt.checks}
        routes = {'model': 'modeling', 'implementation': 'coding', 'writing': 'writing', 'infrastructure': 'recovery'}
        for issue in receipt.issues:
            if issue.check_id not in checks:
                raise ValueError('Issue references unknown check')
            if issue.domain in routes and issue.target != routes[issue.domain]:
                raise ValueError('Wrong rework target')
            if issue.domain == 'explanation' and issue.target not in {'coding', 'writing'}:
                raise ValueError('Wrong explanation rework target')
        if any(c.status != 'PASS' and not any(i.check_id == c.check_id for i in receipt.issues) for c in receipt.checks):
            raise ValueError('Failed/blocked check needs issue and recheck entry')
        if receipt.status == 'PASS' and any(i.severity in {'error', 'blocking'} for i in receipt.issues):
            raise ValueError('PASS cannot contain unresolved errors')
        return digest(receipt.model_dump(mode='json')) if historical_workflow_sha256 else self.save(receipt)
