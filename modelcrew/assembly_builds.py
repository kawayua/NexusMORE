"""E: persisted composition, scoped user review, export and local updates.

Composition is deterministic. It copies confirmed input prose; any explicit
patch is logged. No user approval, model response or W2 is synthesized.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import uuid

from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from . import assembly_runtime as inputs
from . import assembly_compose as composer
from .config import ROOT
from .collaboration import sha_file, workspace_path
from .contracts import digest
from .workflow import WorkflowError
from .writing_reviews import (review_status, manuscript_record, selection_record)
from .modeling_paper import writing_context, require_review_for_export


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Patch(Strict):
    question_id: str = Field(min_length=1, max_length=100)
    before: str = Field(min_length=1, max_length=50000)
    after: str = Field(max_length=50000)
    expected_count: int = Field(default=1, ge=1, le=1000)
    reason: str = Field(min_length=1, max_length=2000)


class CrossReference(Strict):
    source_question: str = Field(min_length=1, max_length=100)
    target_question: str = Field(min_length=1, max_length=100)
    phrase: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern=r'^(figures|tables|equations)$')
    local_number: int = Field(ge=1)


class SymbolSource(Strict):
    question_id: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=1000)


class GlobalSymbol(Strict):
    symbol: str = Field(min_length=1, max_length=1000)
    meaning: str = Field(min_length=1, max_length=4000)
    unit: str = Field(min_length=1, max_length=1000)
    sources: list[SymbolSource] = Field(min_length=1, max_length=100)
    applicable_questions: list[str] | None = Field(default=None, min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)


class ComposeRequest(Strict):
    request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
    actor: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200, pattern=r'^[^\r\n#]+$')
    abstract: str | None = Field(default=None, min_length=1, max_length=10000)
    keywords: str | None = Field(default=None, min_length=1, max_length=1000)
    patches: list[Patch] = Field(default_factory=list, max_length=100)
    cross_references: list[CrossReference] = Field(default_factory=list, max_length=100)
    symbol_table: list[GlobalSymbol] | None = Field(default=None, min_length=1, max_length=1000)
    previous_build_id: str | None = None
    question_titles: dict[str,str] = Field(default_factory=dict)


class Decision(Strict):
    request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
    actor: str = Field(pattern=r'^user$')
    kind: str = Field(pattern=r'^(manuscript|figures)$')
    decision: str = Field(pattern=r'^(approve|reject)$')
    statement: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class ExportRequest(Strict):
    request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
    actor: str = Field(min_length=1, max_length=200)


def rel(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def folder(build_id):
    return ROOT/'stage-e/builds'/str(uuid.UUID(str(build_id)))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load(w, project, build_id):
    try:
        build_id = str(uuid.UUID(str(build_id)))
    except ValueError:
        raise WorkflowError('Invalid assembly build ID') from None
    row = w.db.execute('SELECT * FROM mc_assembly_builds WHERE id=%s AND project_id=%s', (build_id,project)).fetchone()
    if not row:
        raise WorkflowError('Unknown assembly build')
    return row


def save(w, row, phase):
    row['phase'] = phase
    with w.db.transaction():
        w.db.execute('UPDATE mc_assembly_builds SET phase=%s,payload=%s,updated_at=now() WHERE id=%s',
                     (phase,Jsonb(row['payload']),row['id']))
        w.db.execute('INSERT INTO mc_assembly_build_events(build_id,phase,payload) VALUES(%s,%s,%s)',
                     (row['id'],phase,Jsonb(row['payload'])))


def locks_for(w, project, input_row):
    stack = ExitStack()
    try:
        stack.enter_context(w.lock('assembly:'+project))
        for task in sorted(c['task_id'] for c in input_row['payload']['chapters']):
            stack.enter_context(w.lock(task))
    except BaseException:
        stack.close()
        raise
    return stack


def assert_inputs(w, project, run_id):
    state = inputs.status(w, project, run_id)
    if state['phase'] != 'ASSEMBLY_INPUTS_FROZEN':
        raise WorkflowError('Complete current assembly inputs required: '+state['phase'])
    return state


def source_folder(row):
    return folder(row['id'])/'source'


def reviews(row):
    p = row['payload']; source = source_folder(row)
    return review_status(source/composer.MD_NAME, source/'figure-catalog.json',
                         p.get('manuscript_review'),p.get('figure_review'))


def guard(w, project, row):
    assert_inputs(w,project,str(row['assembly_run_id']))
    for name, expected in row['payload'].get('sealed',{}).items():
        path = workspace_path(ROOT,name)
        if not path.is_file() or sha_file(path)!=expected:
            raise WorkflowError('Assembly artifact missing or changed: '+name)
    if digest(writing_context())!=row['payload']['context_identity']:
        raise WorkflowError('Assembly writing policy changed')
    if composer.implementation_sha256()!=row['payload']['composer_sha256']:
        raise WorkflowError('Assembly composer changed; create a new build')


def status(w, project, build_id):
    row = load(w,project,build_id)
    input_row = inputs.load(w,project,str(row['assembly_run_id']))
    with locks_for(w,project,input_row):
        issues=[]
        try:
            guard(w,project,row)
        except (ValueError,OSError) as exc:
            issues.append(str(exc))
        source=source_folder(row); rs=None
        if not issues and row['payload'].get('source_ready'):
            rs=reviews(row)
        phase = 'STALE_BUILD' if issues else row['phase']
        if phase in ['EXPORTING','RENDERING','COMPOSING','REVIEWING_W2']:
            phase = phase+'_RECOVERY_REQUIRED'
        return {'build_id':str(row['id']),'assembly_run_id':str(row['assembly_run_id']),
                'project_id':project,'phase':phase,'issues':issues,
                'source':rel(source) if row['payload'].get('source_ready') else None,
                'manuscript':rel(source/composer.MD_NAME) if row['payload'].get('source_ready') else None,
                'reviews':rs,'chapter_reuse':row['payload'].get('chapter_reuse',{}),
                'exports':row['payload'].get('exports',{}),'renders':row['payload'].get('renders',{}),
                'update':row['payload'].get('update'),
                'W2':('STALE' if issues and row['payload'].get('current_w2_request_id') else row['payload'].get('w2_reviews',{}).get(row['payload'].get('current_w2_request_id'),{}).get('phase','NOT_RUN')),
                'w2_reviews':row['payload'].get('w2_reviews',{}),
                'W2_recheck_exhausted':(row['payload'].get('w2_recheck_exhausted',False) or any(o.get('request',{}).get('recheck_of') and o.get('phase') in ['INVALID_RESPONSE','FAIL','BLOCKED'] for o in row['payload'].get('w2_reviews',{}).values())),
                'scope':'General composition/export lifecycle; no automatic scientific or final layout approval.'}


def compose(w, project, run_id, **kwargs):
    request=ComposeRequest.model_validate(kwargs)
    input_row=inputs.load(w,project,run_id)
    with locks_for(w,project,input_row):
        assert_inputs(w,project,run_id)
        identity=digest({'assembly_run_id':run_id,'request':request.model_dump(mode='json')})
        existing=w.db.execute('SELECT * FROM mc_assembly_builds WHERE project_id=%s AND request_id=%s',
                              (project,request.request_id)).fetchone()
        if existing:
            if existing['request_sha256']!=identity:
                raise WorkflowError('Composition request ID reused with different inputs')
            # Never implicitly repeat interrupted side effects.
            return status(w,project,str(existing['id']))
        qids={c['question_id'] for c in input_row['payload']['chapters']}
        if any(p.question_id not in qids for p in request.patches):
            raise WorkflowError('Patch targets unknown question')
        if any(r.source_question not in qids or r.target_question not in qids for r in request.cross_references):
            raise WorkflowError('Cross-reference targets unknown question')
        previous=load(w,project,request.previous_build_id) if request.previous_build_id else None
        if previous and not previous['payload'].get('source_ready'):
            raise WorkflowError('Previous build has no completed source')
        build_id=str(uuid.uuid4());base=folder(build_id)
        base.mkdir(parents=True,exist_ok=False)
        context=writing_context()
        payload={'request':request.model_dump(mode='json'),'context_identity':digest(context),
                 'composer_sha256':composer.implementation_sha256(), 'sealed':{},'normalized':{},
                 'source_ready':False,'decisions':{},'exports':{}}
        w.db.execute('INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                     (build_id,run_id,project,request.request_id,identity,'COMPOSING',Jsonb(payload)))
        row=load(w,project,build_id)
        save(w,row,'COMPOSING')
        try:
            _compose(w,row,input_row,previous,context)
        except Exception as exc:
            row['payload']['failure']={'kind':type(exc).__name__,'message':str(exc)}
            save(w,row,'COMPOSITION_FAILED')
            raise
        return status(w,project,build_id)


def _compose(w,row,input_row,previous,context):
    p=row['payload']; base=folder(row['id']); ready=[]; reuse={}
    patches=p['request']['patches']
    for chapter in input_row['payload']['chapters']:
        q=chapter['question_id']
        key=digest({'chapter':chapter,'patches':[r for r in patches if r['question_id']==q],
                    'composer_sha256':p['composer_sha256']})
        old=previous['payload'].get('normalized',{}).get(q) if previous else None
        path=base/(q+'-normalized.json')
        if old and old['identity']==key:
            src=workspace_path(ROOT,old['path'])
            if sha_file(src)!=old['sha256']:
                raise WorkflowError('Previous normalized chapter changed')
            data=src.read_bytes(); normalized=json.loads(data)
            reuse[q]='reused'
        else:
            frozen=inputs.snapshot_root(input_row,q)
            md=workspace_path(frozen,chapter['manuscript'])
            cat_path=md.parent/'figure-catalog.json'
            normalized=composer.normalize(q,md.read_text(encoding='utf-8'),read(cat_path),patches)
            data=json.dumps(normalized,ensure_ascii=False,indent=2).encode('utf-8')
            reuse[q]='rebuilt'
        with path.open('xb') as f:
            f.write(data)
        norm={'identity':key,'path':rel(path),'sha256':sha_file(path)}
        p['normalized'][q]=norm
        p['sealed'][rel(path)]=norm['sha256']
        # The current frozen directory is used even when the normalized text is reused.
        frozen=inputs.snapshot_root(input_row,q)
        normalized.update({'identity':key,'normalized_sha256':norm['sha256'],
                           'figure_base':str(workspace_path(frozen,chapter['manuscript']).parent)})
        ready.append(normalized)
    source=source_folder(row)
    report=composer.compose(ready,source,p['request']['title'],p['request']['cross_references'],p['request']['question_titles'] or None, p['request']['abstract'], p['request']['keywords'], p['request']['symbol_table'])
    inputs.write_once(source/'claim-evidence-map.json',claim_evidence(input_row))
    inputs.write_once(source/'assembly-map.json',report)
    inputs.write_once(source/'writer-context.json',context)
    inputs.write_once(source/'input-binding.json',{'assembly_run_id':str(input_row['id']),
                      'manifest_sha256':input_row['payload']['manifest_sha256'],
                      'chapters':[{'question_id':c['question_id'],'binding':c['binding'],
                                   'manuscript_sha256':c['manuscript_sha256'],'W1':c['W1']} for c in input_row['payload']['chapters']]})
    for path in source.rglob('*'):
        if path.is_file():p['sealed'][rel(path)]=sha_file(path)
    p['source_ready']=True;p['chapter_reuse']=reuse
    if previous:
        p['update']={'previous_build_id':str(previous['id']),
                     'rebuilt_questions':sorted(q for q,v in reuse.items() if v=='rebuilt'),
                     'reused_questions':sorted(q for q,v in reuse.items() if v=='reused'),
                     'regenerated_global':['abstract','symbol_table','conclusion','numbering','citations'],
                     'old_user_approvals_inherited':False,'old_W2_inherited':False,
                     'new_solver_runs':0}
        inputs.write_once(base/'update-report.json',p['update'])
        p['sealed'][rel(base/'update-report.json')]=sha_file(base/'update-report.json')
    save(w,row,'WAITING_ASSEMBLY_REVIEW')


def decision(w,project,build_id,**kwargs):
    req=Decision.model_validate(kwargs)
    row=load(w,project,build_id);input_row=inputs.load(w,project,str(row['assembly_run_id']))
    with locks_for(w,project,input_row):
        guard(w,project,row);p=row['payload'];source=source_folder(row)
        key=digest(req.model_dump(mode='json'))
        old=p['decisions'].get(req.request_id)
        if old:
            if old['request_sha256']!=key:raise WorkflowError('Decision ID reused')
            return status(w,project,build_id)
        if row['phase'] not in ['WAITING_ASSEMBLY_REVIEW','READY_TO_EXPORT','ASSEMBLY_REJECTED']:
            raise WorkflowError('Build is not accepting manuscript/figure decisions')
        path=source/composer.MD_NAME if req.kind=='manuscript' else source/'figure-catalog.json'
        if sha_file(path)!=req.artifact_sha256:raise WorkflowError('Decision targets stale artifact')
        args={'decision':req.decision,'actor':req.actor,'statement':req.statement,'reason':req.reason}
        if req.kind=='manuscript':
            record=manuscript_record(source/composer.MD_NAME,source/'figure-catalog.json',**args)
            p['manuscript_review']=record
        else:
            cat=read(source/'figure-catalog.json')
            record=selection_record(source/'figure-catalog.json',[f['id'] for f in cat['figures'] if f['formal']],**args)
            p['figure_review']=record
        event=folder(build_id)/'decisions'/(req.request_id+'.json')
        decision_data={'request_sha256':key,'record':record}
        if event.exists():
            if read(event)!=decision_data:raise WorkflowError('Conflicting persisted decision')
        else:inputs.write_once(event,decision_data)
        p['sealed'][rel(event)]=sha_file(event)
        p['decisions'][req.request_id]={'request_sha256':key,'record':record}
        rs=reviews(row)
        phase='READY_TO_EXPORT' if rs['can_export'] else 'ASSEMBLY_REJECTED' if 'rejected' in [rs['manuscript'],rs['figure_selection']] else 'WAITING_ASSEMBLY_REVIEW'
        save(w,row,phase)
        return status(w,project,build_id)


def export(w,project,build_id,*,exporter=None,**kwargs):
    req=ExportRequest.model_validate(kwargs)
    row=load(w,project,build_id);input_row=inputs.load(w,project,str(row['assembly_run_id']))
    with locks_for(w,project,input_row):
        guard(w,project,row);p=row['payload']
        old=p['exports'].get(req.request_id)
        request_hash=digest(req.model_dump(mode='json'))
        if old:
            if old['request_sha256']!=request_hash:raise WorkflowError('Export ID reused')
            return status(w,project,build_id)
        if row['phase'] not in ['READY_TO_EXPORT','EXPORT_FAILED','WAITING_RENDER','WAITING_W2'] or not reviews(row)['can_export']:
            raise WorkflowError('Current separate user approvals required before export')
        bundle={'review_version':'2.0.0','manuscript_review':p['manuscript_review'],
                'figure_selection_review':p['figure_review']}
        source=source_folder(row)
        require_review_for_export(source/composer.MD_NAME,source/'figure-catalog.json',bundle)
        review_path=source/'user-review-confirmed.json'
        if review_path.exists():
            if read(review_path)!=bundle:raise WorkflowError('Export approval bundle changed')
        else:inputs.write_once(review_path,bundle)
        p['sealed'][rel(review_path)]=sha_file(review_path)
        out=ROOT/'output/paper/assembly-runtime'/str(row['id'])/req.request_id
        p['exports'][req.request_id]={'request_sha256':request_hash,'output':rel(out),'phase':'EXPORTING','runtime_sha256':sha_file(Path(__file__))}
        p['current_export_request_id']=req.request_id
        save(w,row,'EXPORTING')  # durable claim before invoking Pandoc/Tectonic
        try:
            if exporter is None:
                from scripts.export_approved_paper import build as exporter
            exporter(source,out,ROOT/'stage-c-plus/tools/pandoc/pandoc.exe',ROOT/'stage-c-plus/tools/tectonic.exe')
            _finalize_export(row,req.request_id)
            guard(w,project,row)
            save(w,row,'WAITING_RENDER')
        except Exception as exc:
            p['exports'][req.request_id].update({'phase':'EXPORT_FAILED','error':str(exc)})
            save(w,row,'EXPORT_FAILED')
            raise
        return status(w,project,build_id)

def _finalize_export(row, request_id):
    p=row['payload'];entry=p['exports'][request_id]
    out=workspace_path(ROOT,entry['output']);source=source_folder(row)
    manifest=read(out/'build-manifest.json')
    expected={name:sha_file(source/name) for name in [composer.MD_NAME,'figure-catalog.json','user-review-confirmed.json']}
    if manifest.get('source_hashes')!=expected:
        raise WorkflowError('Export manifest does not bind the current source')
    for name,value in expected.items():
        if sha_file(out/name)!=value:raise WorkflowError('Exported source copy changed')
    for name in ['paper.pdf','paper.tex','paper.docx']:
        if not (out/name).is_file() or (out/name).stat().st_size==0:
            raise WorkflowError('Exporter omitted '+name)
    for figure in read(source/'figure-catalog.json')['figures']:
        for asset in figure['files'].values():
            if sha_file(workspace_path(out,asset['path']))!=asset['sha256']:
                raise WorkflowError('Exported figure differs from reviewed figure')
    # Preserve the evidence and transformation chain in the deliverable too.
    # This deterministic copy can safely finish during crash recovery.
    provenance=out/'assembly-provenance';provenance.mkdir(exist_ok=True)
    provenance_hashes={}
    for name in ['assembly-map.json','input-binding.json','claim-evidence-map.json','writer-context.json']:
        original=source/name;target=provenance/name;expected_hash=sha_file(original)
        if target.exists():
            if sha_file(target)!=expected_hash:raise WorkflowError('Exported provenance changed')
        else:
            with target.open('xb') as stream:stream.write(original.read_bytes())
        provenance_hashes[name]=expected_hash
    binding={'build_id':str(row['id']),'assembly_run_id':str(row['assembly_run_id']),
             'source_hashes':expected,'provenance_hashes':provenance_hashes,
             'composer_sha256':p['composer_sha256'],'build_runtime_sha256':entry.get('runtime_sha256',sha_file(Path(__file__))),
             'W2':'NOT_RUN','visual_review':'PENDING'}
    path=provenance/'binding.json'
    if path.exists():
        if read(path)!=binding:raise WorkflowError('Exported assembly binding changed')
    else:inputs.write_once(path,binding)
    built={rel(f):sha_file(f) for f in out.rglob('*') if f.is_file()}
    entry.update({'phase':'EXPORTED','artifacts':built,'render':'PENDING','W2':'NOT_RUN'})
    p['sealed'].update(built)


def recover(w,project,build_id):
    """Recover completed durable output; never rerun uncertain external work."""
    row=load(w,project,build_id)
    if row['phase'] in ['REVIEWING_W2','W2_RECOVERY_REQUIRED']:
        from .assembly_w2 import start
        active=row['payload'].get('current_w2_request_id')
        op=row['payload'].get('w2_reviews',{}).get(active)
        if not op:raise WorkflowError('Missing W2 recovery claim')
        return start(w,project,build_id,**op['request'])
    input_row=inputs.load(w,project,str(row['assembly_run_id']))
    with locks_for(w,project,input_row):
        guard(w,project,row)
        if row['phase']=='COMPOSING':
            row['payload']['failure']={'message':'Composition interrupted; use a new request ID to create a new build.'}
            save(w,row,'COMPOSITION_FAILED')
        elif row['phase']=='RENDERING':
            for item in row['payload'].get('renders',{}).values():
                if item['phase']=='RENDERING':
                    item.update({'phase':'RENDER_FAILED','error':'Interrupted rendering; use a new render request ID.'})
            save(w,row,'RENDER_FAILED')
        elif row['phase']=='EXPORTING':
            active=[k for k,v in row['payload']['exports'].items() if v['phase']=='EXPORTING']
            if len(active)!=1:raise WorkflowError('Ambiguous export recovery claim')
            try:
                _finalize_export(row,active[0])
                save(w,row,'WAITING_RENDER')
            except (ValueError,OSError) as exc:
                row['payload']['exports'][active[0]].update({'phase':'EXPORT_FAILED','error':str(exc)})
                save(w,row,'EXPORT_FAILED')
        return status(w,project,build_id)


class RenderRequest(ExportRequest):
    export_request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')


def render(w,project,build_id,*,renderer=None,**kwargs):
    """Actually render both exports and run deterministic layout checks.

    Mechanical checks do not stand in for independent W2 or human visual QA.
    """
    req=RenderRequest.model_validate(kwargs)
    row=load(w,project,build_id);input_row=inputs.load(w,project,str(row['assembly_run_id']))
    with locks_for(w,project,input_row):
        guard(w,project,row);p=row['payload'];entry=p['exports'].get(req.export_request_id)
        if not entry or entry['phase']!='EXPORTED':raise WorkflowError('Completed export required')
        renders=p.setdefault('renders',{})
        key=digest(req.model_dump(mode='json'))
        if req.request_id in renders:
            if renders[req.request_id]['request_sha256']!=key:raise WorkflowError('Render ID reused')
            return status(w,project,build_id)
        if p.get('current_export_request_id',req.export_request_id)!=req.export_request_id:
            raise WorkflowError('Render must target the current export attempt')
        if row['phase'] not in ['WAITING_RENDER','RENDER_FAILED','WAITING_W2']:
            raise WorkflowError('Render already pending or build not exported')
        out=workspace_path(ROOT,entry['output'])
        qa=folder(build_id)/'renders'/req.request_id
        qa.mkdir(parents=True,exist_ok=False)
        renders[req.request_id]={'request_sha256':key,'phase':'RENDERING','folder':rel(qa),
                                'export_request_id':req.export_request_id}
        if renderer is None:
            renders[req.request_id]['renderer_sha256']=sha_file(ROOT/'scripts/render_assembly_export.py')
            renders[req.request_id]['word_adapter_sha256']=sha_file(ROOT/'scripts/render_assembly_word.ps1')
        save(w,row,'RENDERING')
        try:
            if renderer is None:
                from scripts.render_assembly_export import render as renderer
            result=renderer(out,qa)
            if result.get('status')!='passed':raise WorkflowError('Rendered layout checks failed')
            for path in qa.rglob('*'):
                if path.is_file():p['sealed'][rel(path)]=sha_file(path)
            renders[req.request_id].update({'phase':'RENDERED','result':result})
            entry['render']='MECHANICAL_PASS';entry['visual_review']='PENDING';entry['W2']='NOT_RUN'
            save(w,row,'WAITING_W2')
        except Exception as exc:
            renders[req.request_id].update({'phase':'RENDER_FAILED','error':str(exc)})
            save(w,row,'RENDER_FAILED')
            raise
        return status(w,project,build_id)


def claim_evidence(input_row):
    """Carry forward exact original W1 claims; verify every selected JSON path."""
    from .modeling_hand import pointer
    claims=[]
    for chapter in input_row['payload']['chapters']:
        q=chapter['question_id']; frozen=inputs.snapshot_root(input_row,q); key=chapter['W1']['snapshot_sha256']
        directory=workspace_path(frozen,chapter['manuscript']).parent
        snapshot=read(directory/'records/Snapshot'/(key+'.json'))
        if digest(snapshot)!=key:raise WorkflowError('Frozen W1 snapshot identity changed')
        artifacts={a['artifact_id']:a for a in snapshot['artifacts']}
        objects={}
        for name,artifact in artifacts.items():
            path=workspace_path(frozen,artifact['path'])
            if sha_file(path)!=artifact['sha256']:raise WorkflowError('Frozen claim artifact changed')
            objects[name]=read(path)
        outline=objects['outline']
        if not outline.get('claims'):raise WorkflowError('W1 outline has no claims')
        for claim in outline['claims']:
            locations=[]
            for evidence in claim['evidence']:
                artifact=artifacts[evidence['artifact_id']]
                pointer(objects[evidence['artifact_id']],evidence['selector'])
                locations.append({'artifact_id':evidence['artifact_id'],
                                  'frozen_path':rel(workspace_path(frozen,artifact['path'])),
                                  'sha256':artifact['sha256'],'selector':evidence['selector']})
            claims.append({'global_claim_id':q+'-'+claim['id'],'question_id':q,
                           'statement':claim['statement'],'binding':chapter['binding'],
                           'W1_snapshot_sha256':key,'evidence':locations})
    if len({c['global_claim_id'] for c in claims})!=len(claims):
        raise WorkflowError('Duplicate claim identity')
    return {'claims':claims,'scope':'Original W1 claims and exact frozen evidence paths; editorial changes and final layout still require review.'}

class ReviewBindingRequest(Strict):
    request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
    actor: str = Field(min_length=1,max_length=200)
    reason: str = Field(min_length=1,max_length=4000)
    review_path: str = Field(min_length=1,max_length=1000)
    review_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    original_source: str | None = Field(default=None,min_length=1,max_length=1000)


def bind_reviews(w,project,build_id,**kwargs):
    """Reuse explicit existing user records only when both current snapshots match."""
    req=ReviewBindingRequest.model_validate(kwargs)
    row=load(w,project,build_id); input_row=inputs.load(w,project,str(row['assembly_run_id']))
    with locks_for(w,project,input_row):
        guard(w,project,row); p=row['payload']; identity=digest(req.model_dump())
        old=p.get('review_bindings',{}).get(req.request_id)
        if old:
            if old['request_sha256']!=identity:raise WorkflowError('Review binding ID reused')
            return status(w,project,build_id)
        if row['phase'] not in ['WAITING_ASSEMBLY_REVIEW','READY_TO_EXPORT']:
            raise WorkflowError('Build is not accepting review bindings')
        path=workspace_path(ROOT,req.review_path)
        if sha_file(path)!=req.review_sha256:raise WorkflowError('Existing review bundle changed')
        bundle=read(path); manuscript=bundle.get('manuscript_review'); figures=bundle.get('figure_selection_review')
        for record in (manuscript,figures):
            if not record or record.get('actor')!='user' or not record.get('user_statement','').strip():
                raise WorkflowError('Existing explicit user decisions required; no approval is inferred')
        source=source_folder(row)
        projection=None
        if not review_status(source/composer.MD_NAME,source/'figure-catalog.json',manuscript,figures)['can_export']:
            if not req.original_source:
                raise WorkflowError('Existing user decisions do not match current content, figures and policy')
            manuscript,figures,projection=_project_cache_only_reviews(source,req.original_source,manuscript,figures)
        event={'request_sha256':identity,'request':req.model_dump(),'original_bundle':bundle,
               'cache_only_projection':projection,
               'scope':'Reuse unchanged explicit decisions; not new approval or PDF/Word/W2 acceptance.'}
        target=folder(build_id)/'review-bindings'/(req.request_id+'.json')
        if target.exists():
            if read(target)!=event:raise WorkflowError('Conflicting persisted review binding')
        else:inputs.write_once(target,event)
        p['sealed'][rel(target)]=sha_file(target)
        p['manuscript_review']=manuscript; p['figure_review']=figures
        p.setdefault('review_bindings',{})[req.request_id]=event
        save(w,row,'READY_TO_EXPORT')
        return status(w,project,build_id)


def _project_cache_only_reviews(source,original_source,manuscript,figures):
    """Prove identical approved content with only normalization cache IDs changed."""
    from copy import deepcopy
    original=workspace_path(ROOT,original_source)
    md=original/composer.MD_NAME; cat=original/'figure-catalog.json'
    if not review_status(md,cat,manuscript,figures)['can_export']:
        raise WorkflowError('Original decisions are not valid for their original source/current policy')
    if sha_file(md)!=sha_file(source/composer.MD_NAME):
        raise WorkflowError('Changed manuscript cannot reuse an existing user decision')
    left=read(cat);right=read(source/'figure-catalog.json')
    # Only these two implementation cache identifiers may differ. Every figure,
    # scientific/evidence field, edit and caption must match in full.
    for value in (left,right):
        evidence=value.get('evidence',{})
        for chapter in evidence.get('chapters',[]):
            chapter.pop('identity',None);chapter.pop('normalized_sha256',None)
    if left!=right:
        raise WorkflowError('Figure content or scientific evidence changed; new decisions required')
    evidence={'original_manuscript_sha256':sha_file(md),'original_catalog_sha256':sha_file(cat),
              'current_catalog_sha256':sha_file(source/'figure-catalog.json'),
              'equivalent_catalog_sha256':digest(left),
              'ignored_fields':['evidence.chapters[].identity','evidence.chapters[].normalized_sha256'],
              'approval_created':False,'original_source':original_source}
    snapshot=review_status(source/composer.MD_NAME,source/'figure-catalog.json')['current_manuscript_snapshot']
    text=deepcopy(manuscript);selection=deepcopy(figures)
    for record in (text,selection):
        record['original_snapshot']=deepcopy(record['snapshot'])
        record['record_origin']='verified_existing_user_decision_with_cache_only_scope_binding'
        record['scope_binding']=evidence
    text['snapshot']=snapshot
    # The existing record's selected content and policy are unchanged; replace
    # only the catalog-dependent identity after the strict equality proof above.
    from .writing_reviews import selection_snapshot
    selection['snapshot']=selection_snapshot(source/'figure-catalog.json',figures['snapshot']['selected_ids'])
    return text,selection,evidence
