"""Narrow deterministic manuscript placement repair; no new scientific content."""
import copy,re,uuid
from pathlib import Path
from .contracts import digest
from .workflow import WorkflowError


def move_subsection(text,heading,before):
    lines=list(re.finditer(r'^#{1,3} [^\r\n]+',text,re.M))
    sources=[m for m in lines if m.group()==heading];targets=[m for m in lines if m.group()==before]
    if len(sources)!=1 or len(targets)!=1:raise WorkflowError('Unique source/destination headings required')
    start=sources[0].start();end=next((m.start() for m in lines if m.start()>start),len(text));dest=targets[0].start()
    if dest>=start:raise WorkflowError('This repair only moves an existing later subsection earlier')
    block=text[start:end];remaining=text[:start]+text[end:];updated=remaining[:dest]+block+remaining[dest:]
    if len(updated)!=len(text) or updated[:dest]+updated[dest+len(block):]!=remaining:
        raise WorkflowError('Repair changed content beyond the one moved subsection')
    return updated,{'source_start':start,'source_end':end,'destination':dest,'moved_subsection_sha256':digest(block),'characters_unchanged':len(text)}


def validate_plan_order(plan,catalog):
    sections=plan['sections'];positions={name:i for i,name in enumerate(sections)}
    mapping={v['figure_id']:v for v in plan['figure_plan']};order=[]
    for fig in catalog['figures']:
        if fig['formal']:
            item=mapping.get(fig['id'])
            if not item or item['section'] not in positions:raise WorkflowError('Figure plan must use existing sections')
            order.append(positions[item['section']])
    if order!=sorted(order):raise WorkflowError('Figure plan section order conflicts with fixed catalog numbering; put earlier diagnostic figures before later result figures')


def repair(w,task,run_id,*,request_id,source_heading,before_heading,figure_id,destination_section):
    from . import hand_runtime as hr
    from .business_store import BusinessStore
    from .collaboration import CollaborationStore,Receipt
    with w.lock('business:task:'+task),w.lock(task):
        if BusinessStore(w.db).unresolved('task:'+task):raise WorkflowError('Resolve original unknown operation first')
        row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload'];f=hr.run_folder(row)
        body={'request_id':request_id,'source_heading':source_heading,'before_heading':before_heading,'figure_id':figure_id,'destination_section':destination_section}
        old=p.get('writer_layout_repairs',{}).get(request_id)
        if old:
            if old['request_sha256']!=digest(body):raise WorkflowError('Writer repair idempotency conflict')
            return hr.status(w,task,run_id)
        if (row['hand']!='writing' or row['phase']!='NEEDS_HUMAN' or p['retries']!=3
                or p.get('manuscript') or p.get('manuscript_review') or p.get('figure_review')
                or p.get('feedback',{}).get('paper_findings')!=['Formal figures must appear in catalog numbering order']):
            raise WorkflowError('Only exhausted unpublished figure-order-only draft may use this repair')
        accepted=p.get('reviews',{}).get(p.get('accepted_reviews',{}).get('W1'))
        if not accepted or accepted['status']!='PASS':raise WorkflowError('Existing independent W1 required')
        store=CollaborationStore(f/'records');receipt=store.load(Receipt,accepted['receipt_sha256'])
        if receipt.status!='PASS' or store.accept_review(receipt,accepted['snapshot_sha256'])!=accepted['receipt_sha256']:
            raise WorkflowError('Original W1 receipt differs')
        source=hr.workspace_path(hr.ROOT,p['previous_draft']);data=source.read_bytes();text=data.decode('utf-8')
        catalog=hr.read(f/'figure-catalog.json');base_report=hr.validate_draft(source,f/'figure-catalog.json')
        if base_report['findings']!=['Formal figures must appear in catalog numbering order']:
            raise WorkflowError('Other actual manuscript defects require their own repair')
        updated,movement=move_subsection(text,source_heading,before_heading)
        expected=[v['files']['png']['path'] for v in catalog['figures'] if v['formal']]
        if re.findall(r'!\[[^]]*\]\(([^)]+)\)',updated)!=expected:raise WorkflowError('Single block move does not repair exact figure order')
        plan=hr.read(hr.workspace_path(hr.ROOT,p['outline']));new_plan=copy.deepcopy(plan)
        entry=next((x for x in new_plan['figure_plan'] if x['figure_id']==figure_id),None)
        if not entry or destination_section not in new_plan['sections']:raise WorkflowError('Known mapped figure/destination section required')
        old_section=entry['section'];entry['section']=destination_section;validate_plan_order(new_plan,catalog)
        token=uuid.uuid5(uuid.UUID(run_id),request_id).hex;draft=f/('author-layout-'+token+'.md');outline=f/('outline-layout-'+token+'.json')
        if not draft.exists():draft.write_bytes(updated.encode('utf-8'))
        if draft.read_bytes()!=updated.encode('utf-8'):raise WorkflowError('Immutable repaired draft differs')
        report=hr.validate_draft(draft,f/'figure-catalog.json')
        if report['status']!='passed':raise WorkflowError('Repaired draft still fails: '+str(report['findings']))
        if not outline.exists():hr.write(outline,new_plan)
        if hr.read(outline)!=new_plan:raise WorkflowError('Immutable repaired outline differs')
        check=f/('layout-check-'+token+'.json')
        if not check.exists():hr.write(check,report)
        record={'request':body,'request_sha256':digest(body),'binding':p['binding'],'source_draft':p['previous_draft'],
            'source_sha256':hr.sha_file(source),'source_outline':p['outline'],'source_outline_sha256':hr.sha_file(hr.workspace_path(hr.ROOT,p['outline'])),
            'draft_path':hr.rel(draft),'draft_sha256':hr.sha_file(draft),'outline_path':hr.rel(outline),'outline_sha256':hr.sha_file(outline),
            'catalog_sha256':hr.sha_file(f/'figure-catalog.json'),'movement':movement,
            'outline_change':{'figure_id':figure_id,'previous_section':old_section,'new_section':destination_section},
            'previous_attempt':p['attempt'],'attempt':p['attempt']+1,'automatic_retries':p['retries'],
            'origin':'deterministic_writer_layout_repair','call_id':'writer-layout-'+token,'context_id':str(uuid.uuid5(uuid.UUID(token),'author')),
            'scope':'Move one complete subsection verbatim and update its one figure-plan section mapping. No text/data/equation/caption/image/number or old receipt changes. New independent W1 before publishing; no user approval.'}
        manifest=f/('writer-layout-repair-'+token+'.json')
        if not manifest.exists():hr.write(manifest,record)
        for path in (draft,outline,check,manifest):hr.seal(row,path)
        hr.author(row,record)
        p.setdefault('writer_layout_repairs',{})[request_id]=record
        p.update(attempt=record['attempt'],outline=hr.rel(outline),previous_draft=hr.rel(draft),prepared_writer_draft={'attempt':record['attempt'],'path':hr.rel(draft),'sha256':hr.sha_file(draft),'outline_sha256':hr.sha_file(outline),'repair_manifest':hr.rel(manifest),'token':token})
        p.setdefault('accepted_reviews',{}).pop('W1',None)
        for key in ('review_suffix','recheck_rationale','failure_domain','rework_target'):p.pop(key,None)
        hr.save(w,row,'REVIEW_W1');return hr.status(w,task,run_id)


def publish_prepared(w,row):
    from . import hand_runtime as hr
    p=row['payload'];value=p['prepared_writer_draft'];f=hr.run_folder(row)
    if row['phase'] not in ('DRAFT','WAITING_MANUSCRIPT_AND_FIGURES') or p.get('manuscript_review') or p.get('figure_review'):
        raise WorkflowError('Preserve existing manuscript/figure user decisions')
    from .collaboration import CollaborationStore,Receipt,Snapshot
    accepted=p.get('reviews',{}).get(p.get('accepted_reviews',{}).get('W1'),{})
    if accepted.get('status')!='PASS':raise WorkflowError('New independent W1 required before publishing prepared manuscript')
    store=CollaborationStore(f/'records');receipt=store.load(Receipt,accepted['receipt_sha256'])
    if receipt.status!='PASS' or store.accept_review(receipt,accepted['snapshot_sha256'])!=accepted['receipt_sha256']:
        raise WorkflowError('Prepared manuscript W1 receipt differs')
    snapshot=store.load(Snapshot,accepted['snapshot_sha256']);artifacts={a.artifact_id:a for a in snapshot.artifacts}
    if ('prepared-manuscript' not in artifacts or artifacts.get('outline') is None
            or artifacts['outline'].sha256!=value['outline_sha256']):
        raise WorkflowError('W1 did not review this prepared manuscript/outline')
    if value['attempt']!=p['attempt'] or hr.sha_file(hr.workspace_path(hr.ROOT,p['outline']))!=value['outline_sha256']:
        raise WorkflowError('Prepared writer draft outline/attempt changed')
    source=hr.workspace_path(hr.ROOT,value['path'])
    if hr.sha_file(source)!=value['sha256']:raise WorkflowError('Prepared writer draft changed')
    report=hr.validate_draft(source,f/'figure-catalog.json')
    if report['status']!='passed':raise WorkflowError('Prepared draft failed after review')
    target=f/('单题论文-中文审阅稿-'+value['token'][:12]+'.md')
    if not target.exists():target.write_bytes(source.read_bytes())
    if hr.sha_file(target)!=value['sha256']:raise WorkflowError('Published prepared manuscript differs')
    hr.seal(row,target);p.update(manuscript=hr.rel(target),manuscript_review=None,figure_review=None,
        latest_paper_findings=[],feedback={'paper_findings':[],'layout_repair':'Passed structural validation and fresh independent W1; old findings retained in historical events.'})
    hr.save(w,row,'WAITING_MANUSCRIPT_AND_FIGURES')
