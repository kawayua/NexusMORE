"""E1: immutable multi-question input runs from approved generic Writer runs.

No paper rewriting, solver invocation or approval inference occurs here. Status
revalidates live dependencies and reports the affected assembly products.
"""
from contextlib import ExitStack
from pathlib import Path
import json
import hashlib
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg.types.json import Jsonb

from .config import ROOT
from .runtime_paths import run_directory
from .contracts import digest
from .workflow import WorkflowError
from . import hand_runtime as hands
from .collaboration import CollaborationStore, Receipt, Ticket, sha_file, workspace_path
from .modeling_paper import writing_context


class ChapterInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
    task_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=100)
    source_project_id: str | None = Field(default=None, min_length=1, max_length=200)


class AssemblyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
    actor: str = Field(min_length=1, max_length=200)
    required_questions: list[str] = Field(min_length=1, max_length=100)
    chapters: list[ChapterInput] = Field(min_length=1, max_length=100)
    allow_partial: bool = False
    previous_run_id: str | None = None

    @model_validator(mode='after')
    def coverage(self):
        questions = [c.question_id for c in self.chapters]
        tasks = [c.task_id for c in self.chapters]
        if len(questions) != len(set(questions)) or len(tasks) != len(set(tasks)):
            raise ValueError('Duplicate question or task')
        if len(self.required_questions) != len(set(self.required_questions)):
            raise ValueError('Duplicate required question')
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', q) for q in self.required_questions):
            raise ValueError('Invalid required question ID')
        if not set(questions) <= set(self.required_questions):
            raise ValueError('Undeclared question in assembly')
        if not self.allow_partial and set(questions) != set(self.required_questions):
            raise ValueError('All required questions must be present')
        return self


def folder(run_id):
    return run_directory(ROOT,'assembly-inputs',run_id)


def relative(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def load(w, project, run_id):
    try:
        key = str(uuid.UUID(str(run_id)))
    except ValueError:
        raise WorkflowError('Invalid assembly run ID') from None
    row = w.db.execute('SELECT * FROM mc_assembly_runs WHERE id=%s AND project_id=%s', (key, project)).fetchone()
    if not row:
        raise WorkflowError('Unknown assembly run')
    return row


def approved_chapter(w, chapter, project, *, historical_context=None):
    if historical_context:
        from .assembly_binding import context_delta
        from .collaboration import historical_review_context
        context_delta(historical_context['context'], writing_context())
        paper_policy = next(d['sha256'] for d in historical_context['context']['documents']
                            if d['path']=='resources/paper/chinese-modeling-policy.json')
        with historical_review_context(historical_context['context']['workflow_sha256'], paper_policy):
            return _approved_chapter(w, chapter, project, historical_context=historical_context)
    return _approved_chapter(w, chapter, project)


def _approved_chapter(w, chapter, project, *, historical_context=None):
    task = w.task(chapter.task_id)
    if task['project_id'] != (chapter.source_project_id or project):
        raise WorkflowError('Cross-project source must be explicitly declared')
    if historical_context:
        from .assembly_binding import historical_state
        state = historical_state(w, chapter, historical_context)
    else:
        state = hands.status(w, chapter.task_id, chapter.run_id)
    if state['hand'] != 'writing' or state['phase'] != 'READY_FOR_E_EXPORT' or not state['reviews']['can_export']:
        raise WorkflowError('Approved manuscript and figure selection required')
    row = hands.load(w, chapter.task_id, chapter.run_id)
    p = row['payload']
    key = p.get('accepted_reviews', {}).get('W1', f'W1-{p["attempt"]}')
    review = p.get('reviews', {}).get(key)
    if not review or review['status'] != 'PASS':
        raise WorkflowError('Independent W1 required')
    store = CollaborationStore(hands.run_folder(row)/'records')
    receipt = store.load(Receipt, review['receipt_sha256'])
    ticket = store.load(Ticket, receipt.ticket_sha256)
    if ticket.gate != 'W1' or receipt.status != 'PASS' or ticket.binding.model_dump(mode='json', exclude={'schema_version'}) != state['binding']:
        raise WorkflowError('W1 binding mismatch')
    if store.accept_review(receipt, review['snapshot_sha256'], **({'historical_workflow_sha256':historical_context['context']['workflow_sha256']} if historical_context else {})) != review['receipt_sha256']:
        raise WorkflowError('W1 receipt invalid')
    manuscript = workspace_path(ROOT, p['manuscript'])
    base = hands.run_folder(row).resolve()
    manuscript.relative_to(base)
    # Seal the complete existing evidence chain, not just the visible Markdown.
    files = dict(p['sealed'])
    for path in (manuscript, base/'figure-catalog.json', base/'manuscript-review.json', base/'figures-review.json'):
        files[relative(path)] = sha_file(path)
    for path in sorted((base/'records').rglob('*.json')):
        files[relative(path)] = sha_file(path)
    for name, expected in files.items():
        evidence = historical_context['files'].get(name) if historical_context else None
        path = workspace_path(ROOT, evidence['snapshot']) if evidence else workspace_path(ROOT, name)
        if (evidence and evidence['sha256'] != expected) or sha_file(path) != expected:
            raise WorkflowError('Changed source evidence: '+name)
    return {'question_id': chapter.question_id, 'task_id': chapter.task_id,
            'run_id': chapter.run_id, 'source_project_id': task['project_id'], 'binding': state['binding'],
            'manuscript': relative(manuscript), 'manuscript_sha256': state['manuscript_sha256'],
            'figure_catalog_sha256': state['figure_catalog_sha256'],
            'W1': review, 'reviews': state['reviews'], 'files': files}


def impact(previous, current):
    """Pure dependency comparison; never starts computation or revokes history."""
    old = {c['question_id']: c for c in previous}
    new = {c['question_id']: c for c in current}
    changed = sorted(q for q in old.keys() | new.keys() if old.get(q) != new.get(q))
    return {'changed_questions': changed,
            'preserved_questions': sorted(q for q in old.keys() & new.keys() if q not in changed),
            'invalidated_products': (['chapter:'+q for q in changed] +
                                    ['abstract', 'introduction', 'conclusion', 'global_numbering', 'build', 'W2']) if changed else [],
            'solver_rerun_started': False,
            'scope': 'Assembly dependencies only; upstream workflow decides whether model/result checks must rerun.'}


def snapshot_root(input_row,question_id):
    base=folder(input_row['id'])/'snapshot'
    return base/question_id if input_row['payload'].get('snapshot_layout')=='per_question' else base


def write_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)


def start(w, project, **kwargs):
    req = AssemblyRequest.model_validate(kwargs)
    # Project lock followed by sorted task locks gives an atomic live snapshot
    # relative to task actions and avoids cross-assembly lock inversion.
    with ExitStack() as locks:
        locks.enter_context(w.lock('assembly:'+project))
        w.require_project(project)
        for task in sorted(c.task_id for c in req.chapters):
            locks.enter_context(w.lock(task))
        existing = w.db.execute('SELECT * FROM mc_assembly_runs WHERE project_id=%s AND request_id=%s', (project, req.request_id)).fetchone()
        request_hash = digest(req.model_dump(mode='json'))
        if existing:
            if existing['request_sha256'] != request_hash:
                raise WorkflowError('Assembly request ID reused with different inputs')
            return status(w, project, str(existing['id']))
        previous = load(w, project, req.previous_run_id) if req.previous_run_id else None
        historical={}
        if previous:
            from .assembly_binding import chapter_context
            for c in req.chapters:
                prior=next((p for p in previous['payload']['chapters'] if p['question_id']==c.question_id and p.get('task_id')==c.task_id and p.get('run_id')==c.run_id),None)
                if prior and (previous['payload'].get('context_rebinding') or c.question_id in previous['payload'].get('historical_chapters',[])):
                    historical[c.question_id]=chapter_context(previous['payload'],prior)
        chapters = [approved_chapter(w,c,project,**({'historical_context':historical[c.question_id]} if c.question_id in historical else {})) for c in req.chapters]
        run_id = str(uuid.uuid4())
        base = folder(run_id)
        base.mkdir(parents=True, exist_ok=False)
        context = writing_context()
        write_once(base/'writer-context.json', context)
        frozen = []
        for chapter in chapters:
            for name, expected in sorted(chapter['files'].items()):
                prior=historical.get(chapter['question_id'],{}).get('files',{}).get(name)
                source=workspace_path(ROOT,prior['snapshot'] if prior else name)
                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise WorkflowError('Source changed during freeze: '+name)
                target = (base/'snapshot'/chapter['question_id']/name) if historical else (base/'snapshot'/name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if sha_file(target) != expected:
                        raise WorkflowError('Conflicting shared source identity: '+name)
                else:
                    with target.open('xb') as f:
                        f.write(data)
                frozen.append({'source': name, 'snapshot': relative(target), 'sha256': expected,
                               'question_id': chapter['question_id']})
        payload = {'format_version': '1.0.0', 'run_id': run_id, 'project_id': project,
                   'request': req.model_dump(mode='json'), 'chapters': chapters,
                   'snapshot_layout':'per_question' if historical else 'shared',
                   'historical_chapters':sorted(historical),
                   'missing_questions': sorted(set(req.required_questions)-{c.question_id for c in req.chapters}),
                   'files': frozen, 'workflow_sha256': context['workflow_sha256'],
                   'context_sha256': sha_file(base/'writer-context.json'), 'context_identity': digest(context),
                   'combined_manuscript_approved': False, 'W2': 'NOT_RUN',
                   'scope': 'E1 frozen inputs, not a new manuscript, formal export, or W2 receipt.'}
        if previous:
            payload['update_impact'] = impact(previous['payload']['chapters'], chapters)
        write_once(base/'input-manifest.json', payload)
        payload['manifest_sha256'] = sha_file(base/'input-manifest.json')
        w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',
                     (run_id, project, req.request_id, request_hash, Jsonb(payload)))
        return status(w, project, run_id)


def status(w, project, run_id):
    row = load(w, project, run_id)
    p = row['payload']
    with ExitStack() as locks:
        locks.enter_context(w.lock('assembly:'+project))
        for task in sorted(c['task_id'] for c in p['chapters']):
            locks.enter_context(w.lock(task))
        issues = []
        changed = set()
        base = folder(run_id)
        if not (base/'input-manifest.json').is_file() or sha_file(base/'input-manifest.json') != p['manifest_sha256']:
            issues.append({'scope': 'manifest', 'reason': 'Frozen manifest missing or changed'})
        if not (base/'writer-context.json').is_file() or sha_file(base/'writer-context.json') != p['context_sha256']:
            issues.append({'scope': 'policy', 'reason': 'Frozen writing context missing or changed'})
        frozen_identity = p.get('context_identity')
        if frozen_identity is None and (base/'writer-context.json').is_file():
            frozen_identity = digest(json.loads((base/'writer-context.json').read_text(encoding='utf-8')))
        if digest(writing_context()) != frozen_identity:
            issues.append({'scope': 'policy', 'reason': 'Current writing policy changed'})
        for item in p['files']:
            path = workspace_path(ROOT, item['snapshot'])
            if not path.is_file() or sha_file(path) != item['sha256']:
                changed.add(item['question_id'])
                issues.append({'scope': item['question_id'], 'reason': 'Frozen evidence changed', 'path': item['snapshot']})
        for chapter in p['chapters']:
            try:
                chapter_input = ChapterInput.model_validate({k: chapter[k] for k in ['question_id','task_id','run_id','source_project_id']})
                if p.get('context_rebinding') or chapter['question_id'] in p.get('historical_chapters',[]):
                    from .assembly_binding import chapter_context
                    current = approved_chapter(w, chapter_input, project, historical_context=chapter_context(p, chapter))
                else:
                    current = approved_chapter(w, chapter_input, project)
                if current != chapter:
                    raise WorkflowError('Live chapter identity changed')
            except (ValueError, OSError) as exc:
                changed.add(chapter['question_id'])
                issues.append({'scope': chapter['question_id'], 'reason': str(exc)})
        global_change = any(i['scope'] in ['manifest','policy'] for i in issues)
        affected = sorted({c['question_id'] for c in p['chapters']} if global_change else changed)
        return {'run_id': str(row['id']), 'project_id': project,
                'phase': 'STALE_INPUTS' if issues else 'PARTIAL_INPUTS_FROZEN' if p['missing_questions'] else 'ASSEMBLY_INPUTS_FROZEN',
                'manifest': relative(base/'input-manifest.json'), 'manifest_sha256': p['manifest_sha256'],
                'missing_questions': p['missing_questions'], 'issues': issues,
                'affected_questions': affected,
                'preserved_questions': sorted(c['question_id'] for c in p['chapters'] if c['question_id'] not in affected),
                'invalidated_products': (['chapter:'+q for q in affected]+['abstract','introduction','conclusion','global_numbering','build','W2']) if issues else [],
                'update_impact': p.get('update_impact'), 'new_export_created': False,
                'new_W2_performed': False, 'combined_manuscript_approved': False,
                'scope': p['scope']}
