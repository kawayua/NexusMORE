"""One explicit user decision for the displayed manuscript and figure versions."""
from .contracts import digest


def combined_pending(items):
    """Group only two still-pending writing decisions for the identical run/binding."""
    groups={}
    for item in items:
        if item.get('decision_operation') not in ('hand_decide','assembly_decide') or item['kind'] not in ('manuscript','figures'):continue
        base={k:v for k,v in item['binding'].items() if k!='artifact_sha256'}
        key=digest([item['decision_operation'],base]);groups.setdefault(key,{'base':base,'operation':item['decision_operation'],'items':{}})['items'][item['kind']]=item
    result=[]
    from .business_projection import pending_id
    for value in groups.values():
        pair=value['items']
        if set(pair)!= {'manuscript','figures'}:continue
        components={'manuscript_sha256':pair['manuscript']['binding']['artifact_sha256'],
                    'figure_catalog_sha256':pair['figures']['binding']['artifact_sha256']}
        bound={**value['base'],'artifact_sha256':digest(components)}
        ids=sorted(set(pair['manuscript']['artifact_ids']+pair['figures']['artifact_ids']))
        result.append({'pending_id':pending_id('manuscript_and_figures',bound,ids),'kind':'manuscript',
            'binding':bound,'artifact_ids':ids,'allowed_decisions':['approve'],
            'decision_operation':value['operation'],'confirmation_scope':'manuscript_and_figures',
            'components':components,'prompt':'请一起审阅当前正文和配图；查看后一次明确确认同时记录两个批准。'})
    return result


def native_decision(w,row,*,decision,actor,statement,reason,artifact_sha256,request_id,manuscript_sha256,figure_catalog_sha256):
    from . import hand_runtime as hr
    from .writing_reviews import manuscript_record,selection_record,catalog_at,review_status
    if decision!='approve' or actor!='user':raise hr.WorkflowError('Combined review requires explicit user approval')
    p=row['payload'];f=hr.run_folder(row)
    body={'kind':'manuscript','decision':decision,'actor':actor,'statement':statement,'reason':reason,
          'artifact_sha256':artifact_sha256,'approve_figures':True,'manuscript_sha256':manuscript_sha256,'figure_catalog_sha256':figure_catalog_sha256}
    previous=p.get('decisions',{}).get(request_id)
    if previous:
        if previous!=digest(body):raise hr.WorkflowError('Combined approval idempotency conflict')
        return hr.status(w,row['task_id'],str(row['id']))
    if row['phase']!='WAITING_MANUSCRIPT_AND_FIGURES' or p.get('manuscript_review') or p.get('figure_review'):
        raise hr.WorkflowError('Preserve prior decisions; both current objects must still be pending')
    md=hr.workspace_path(hr.ROOT,p['manuscript']);cat=f/'figure-catalog.json'
    components={'manuscript_sha256':hr.sha_file(md),'figure_catalog_sha256':hr.sha_file(cat)}
    if components!={'manuscript_sha256':manuscript_sha256,'figure_catalog_sha256':figure_catalog_sha256} or digest(components)!=artifact_sha256:
        raise hr.WorkflowError('Manuscript or figure version changed; show a new combined review')
    # Validate BOTH complete records before writing either approval to business state.
    mr=manuscript_record(md,cat,decision=decision,actor=actor,statement=statement,reason=reason)
    fr=selection_record(cat,[fig['id'] for fig in catalog_at(cat)['figures'] if fig['formal']],decision=decision,actor=actor,statement=statement,reason=reason)
    bundle={'protocol':'combined-paper-decision/1.0.0','binding':p['binding'],'request_id':request_id,
            'components':components,'user_statement':statement,'manuscript':mr,'figures':fr}
    target=f/('combined-paper-decision-'+digest(body)[:24]+'.json')
    if not target.exists():hr.write(target,bundle)
    if hr.read(target)!=bundle:raise hr.WorkflowError('Immutable combined decision differs')
    # One row/event transaction is the authoritative all-or-nothing decision.
    for name,record in [('manuscript-review.json',mr),('figures-review.json',fr)]:
        path=f/name
        if not path.exists():hr.write(path,record)
        if hr.read(path)!=record:raise hr.WorkflowError('Existing individual review file differs')
        hr.seal(row,path)
    hr.seal(row,target);p.update(manuscript_review=mr,figure_review=fr)
    p.setdefault('decisions',{})[request_id]=digest(body)
    p.setdefault('combined_user_decisions',{})[request_id]={'path':hr.rel(target),'sha256':hr.sha_file(target),'components':components}
    state=review_status(md,cat,mr,fr)
    hr.save(w,row,'READY_FOR_E_EXPORT' if state['can_export'] else 'WAITING_MANUSCRIPT_AND_FIGURES')
    return hr.status(w,row['task_id'],str(row['id']))


def assembly_decision(w,project,build_id,body):
    """One native capture atomically approves the displayed assembly components."""
    from . import assembly_builds as ab
    from .writing_reviews import manuscript_record,selection_record,catalog_at
    from .collaboration import sha_file
    from .workflow import WorkflowError
    core={k:v for k,v in body.items() if k not in ('approve_figures','manuscript_sha256','figure_catalog_sha256')}
    req=ab.Decision.model_validate(core)
    if body.get('approve_figures') is not True or req.kind!='manuscript' or req.decision!='approve':raise WorkflowError('Explicit combined assembly approval required')
    row=ab.load(w,project,build_id);input_row=ab.inputs.load(w,project,str(row['assembly_run_id']))
    with ab.locks_for(w,project,input_row):
        ab.guard(w,project,row);p=row['payload'];key=digest(body)
        previous=p['decisions'].get(req.request_id)
        if previous:
            if previous['request_sha256']!=key:raise WorkflowError('Combined decision ID reused')
            return ab.status(w,project,build_id)
        if row['phase']!='WAITING_ASSEMBLY_REVIEW' or p.get('manuscript_review') or p.get('figure_review'):raise WorkflowError('Preserve existing approvals; both components must be pending')
        source=ab.source_folder(row);md=source/ab.composer.MD_NAME;cat=source/'figure-catalog.json'
        components={'manuscript_sha256':sha_file(md),'figure_catalog_sha256':sha_file(cat)}
        if components!={k:body.get(k) for k in components} or digest(components)!=req.artifact_sha256:raise WorkflowError('Combined assembly version changed')
        kw={'decision':'approve','actor':'user','statement':req.statement,'reason':req.reason}
        mr=manuscript_record(md,cat,**kw)
        fr=selection_record(cat,[f['id'] for f in catalog_at(cat)['figures'] if f['formal']],**kw)
        record={'kind':'manuscript_and_figures','components':components,'manuscript':mr,'figures':fr}
        data={'request_sha256':key,'record':record};target=ab.folder(build_id)/'decisions'/(req.request_id+'.json')
        if target.exists():
            if ab.read(target)!=data:raise WorkflowError('Conflicting immutable combined decision')
        else:ab.inputs.write_once(target,data)
        p['sealed'][ab.rel(target)]=sha_file(target)
        p.update(manuscript_review=mr,figure_review=fr);p['decisions'][req.request_id]=data
        ab.save(w,row,'READY_TO_EXPORT' if ab.reviews(row)['can_export'] else 'WAITING_ASSEMBLY_REVIEW')
        return ab.status(w,project,build_id)
