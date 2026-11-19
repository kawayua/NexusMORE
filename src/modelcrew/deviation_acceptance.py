"""Trusted, result-scoped acceptance of disclosed self-imposed error criteria.

No model tool creates this record. Original thresholds/checks/receipts stay intact;
this is a versioned acceptance addendum, never a numerical PASS or result approval.
"""
from pathlib import Path
import uuid
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from .contracts import digest
from .workflow import WorkflowError

ALLOWED={'chk_dt','chk_analytic2d','chk_grid','chk_bc','chk_1d_limit'}

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    protocol:Literal['disclosed-error-acceptance/1.0.0']
    run_id:str
    binding:dict
    actor:Literal['user']
    request_id:str=Field(pattern=r'^[A-Za-z0-9_.-]{1,200}$')
    user_statement:str=Field(min_length=1,max_length=4000)
    reason:str=Field(min_length=1,max_length=4000)
    check_ids:list[str]=Field(min_length=1,max_length=5)
    expected_p2_receipt_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_p2_snapshot_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_check_sha256:dict[str,str]
    requirement_provenance:str=Field(min_length=1,max_length=4000)
    capture_channel:Literal['trusted_local_user_message']


def numeric_identity(packet):
    """Exact check values/configuration; an export-only change can retain consent."""
    try:
        result=packet['json_outputs']['result.json']
        ref=packet['json_outputs']['outputs/diagnostics.json']['verification']['base_reference']
        checks={c['id']:c for c in result['checks']}
        if len(checks)!=len(result['checks']):raise ValueError('duplicate checks')
        return {'binding':result['binding'],'config_sha256':digest(result['config']),
            'check_sha256':{key:digest(value) for key,value in checks.items()},
            'unrounded_T_sha256':ref['sha256_unrounded_T'],
            'unrounded_C_sha256':ref['sha256_unrounded_C']}
    except (KeyError,TypeError,ValueError) as exc:
        raise WorkflowError('Complete exact-result numerical identity required') from exc


def verify_request(req,row,packet,contract):
    p=row['payload'];checks={c['id']:c for c in packet['json_outputs']['result.json']['checks']}
    if (req.run_id!=str(row['id']) or req.binding!=p['binding'] or row['hand']!='coding'
            or not req.user_statement.strip() or not req.reason.strip()
            or len(req.check_ids)!=len(set(req.check_ids)) or not set(req.check_ids)<=ALLOWED
            or set(req.expected_check_sha256)!=set(req.check_ids)):
        raise WorkflowError('Acceptance scope/binding is invalid')
    frozen={c['id']:c for c in contract['checks']}
    for key in req.check_ids:
        c=checks.get(key);base=frozen.get(key)
        if (not c or not base or c.get('status')!='FAIL' or c.get('tolerance')!=base['tolerance']
                or digest(c)!=req.expected_check_sha256[key]):
            raise WorkflowError('Accepted error must match an actually failed frozen check: '+key)
    last=p.get('last_review',{});review=p.get('reviews',{}).get(last.get('stage_key'),{})
    if (last.get('gate')!='P2' or review.get('status')!='FAIL'
            or review.get('receipt_sha256')!=req.expected_p2_receipt_sha256
            or review.get('snapshot_sha256')!=req.expected_p2_snapshot_sha256):
        raise WorkflowError('Acceptance must reference the actual last failed P2')
    return {key:checks[key] for key in req.check_ids}


def validate(row):
    """Read-only validation on every run guard, including future export-only repairs."""
    from . import hand_runtime as hr
    p=row['payload'];entry=p.get('error_acceptance_addendum')
    if not entry:return None
    path=hr.workspace_path(hr.ROOT,entry['path'])
    if hr.sha_file(path)!=entry['sha256']:raise WorkflowError('Error acceptance addendum changed')
    record=hr.read(path);req=Decision(**record['decision'])
    if (record.get('revision')!=entry['revision'] or record.get('request_sha256')!=digest(req.model_dump())
            or req.binding!=p['binding'] or req.run_id!=str(row['id'])
            or set(req.check_ids)!=set(record['accepted_checks'])
            or not set(req.check_ids)<=ALLOWED):
        raise WorkflowError('Error acceptance addendum binding differs')
    for key,c in record['accepted_checks'].items():
        if digest(c)!=req.expected_check_sha256[key] or c.get('status')!='FAIL':
            raise WorkflowError('Original accepted FAIL evidence differs')
    original=hr.read(hr.workspace_path(hr.ROOT,record['original_full_packet']['path']))
    if hr.sha_file(hr.workspace_path(hr.ROOT,record['original_full_packet']['path']))!=record['original_full_packet']['sha256']:
        raise WorkflowError('Accepted original execution changed')
    if numeric_identity(original)!=record['numeric_identity']:
        raise WorkflowError('Original accepted numerical evidence changed')
    current=p.get('full_packet')
    if current and numeric_identity(hr.read(hr.workspace_path(hr.ROOT,current)))!=record['numeric_identity']:
        raise WorkflowError('New numerical data differs from user-accepted errors; communicate again')
    return record


def adopt(w,task,run_id,source):
    """Capture explicit user consent; reopen independent P2 without author generation.

    Only an untouched post-P2 rework state is eligible. No budget resets, no
    changes to old author output, original PASS/FAIL, model or result approval.
    """
    from . import hand_runtime as hr
    from .business_store import BusinessStore
    from .collaboration import CollaborationStore,Receipt
    with w.lock('business:task:'+task),w.lock(task):
        if BusinessStore(w.db).unresolved('task:'+task):raise WorkflowError('Resolve unknown business operation first')
        row=hr.load(w,task,run_id);contract=hr.guard(w,row);p=row['payload']
        path=hr.workspace_path(hr.ROOT,source)
        if path.is_symlink() or path.is_junction() or path.stat().st_size>20000:raise WorkflowError('Unsafe user decision record')
        req=Decision(**hr.read(path));fingerprint=digest(req.model_dump())
        prior=p.get('error_acceptance_history',{}).get(req.request_id)
        if prior:
            record=validate(row)
            if not record or record['request_sha256']!=fingerprint:raise WorkflowError('Acceptance idempotency conflict')
            return hr.status(w,task,run_id)
        if (p.get('error_acceptance_addendum') or p.get('attached') or w.task(task)['result_revision']
                or row['phase'] not in ('GENERATE_MINIMAL','NEEDS_HUMAN','NEEDS_CODE_REVISION','NEEDS_RESULT_INTERPRETATION')
                or not p.get('full_packet') or not p.get('replica_packet')):
            raise WorkflowError('Acceptance requires an unmodified rejected full run')
        last=p.get('last_review',{});old_attempt=last.get('attempt')
        if (old_attempt is None or p['attempt'] not in (old_attempt,old_attempt+1)
                or any('code-'+stage+'-'+str(p['attempt']) in p.get('ops',{}) for stage in ('minimal','full'))
                or any(key.startswith(('minimal-'+str(p['attempt']),'full-'+str(p['attempt']))) for key in p.get('jobs',{}))):
            raise WorkflowError('A newer author generation/execution has already been claimed')
        packet=hr.read(hr.workspace_path(hr.ROOT,p['full_packet']));replica=hr.read(hr.workspace_path(hr.ROOT,p['replica_packet']))
        accepted=verify_request(req,row,packet,contract)
        names=lambda q:{a['path'].split('/artifacts/',1)[1]:a['sha256'] for a in q['artifacts']}
        if (packet['receipt']['status']!='succeeded' or replica['receipt']['status']!='succeeded'
                or names(packet)!=names(replica)):
            raise WorkflowError('Successful real full execution and exact reproduction required')
        store=CollaborationStore(hr.run_folder(row)/'records')
        rejected=store.load(Receipt,req.expected_p2_receipt_sha256)
        if store.accept_review(rejected,req.expected_p2_snapshot_sha256)!=req.expected_p2_receipt_sha256:
            raise WorkflowError('Original independent P2 receipt differs')
        # Revalidate the exact prior P1 rather than inventing a new PASS.
        p1_candidates=[(k,v) for k,v in p.get('reviews',{}).items() if k.startswith('P1-') and v['status']=='PASS']
        if len(p1_candidates)!=1:raise WorkflowError('Unique unchanged independent P1 required')
        p1key,p1=p1_candidates[0];receipt=store.load(Receipt,p1['receipt_sha256'])
        if store.accept_review(receipt,p1['snapshot_sha256'])!=p1['receipt_sha256']:raise WorkflowError('Prior P1 invalid')
        revision=1
        record={'protocol':req.protocol,'revision':revision,'decision':req.model_dump(),
            'request_sha256':fingerprint,'accepted_checks':accepted,'numeric_identity':numeric_identity(packet),
            'original_full_packet':{'path':p['full_packet'],'sha256':hr.sha_file(hr.workspace_path(hr.ROOT,p['full_packet']))},
            'original_replica_packet':{'path':p['replica_packet'],'sha256':hr.sha_file(hr.workspace_path(hr.ROOT,p['replica_packet']))},
            'unchanged_P1':{'stage_key':p1key,**p1},'previous_phase':row['phase'],
            'author_attempt_unchanged':p['attempt'],'automatic_retries_unchanged':p['retries'],
            'acceptance_disposition':'USER_ACCEPTED_DEVIATION; original numerical FAIL remains FAIL',
            'scope':'Only listed exact disclosed self-imposed error checks. No waiver of execution, reproduction, physics, other checks, PDF/font/visual quality or user result/paper approval. New independent P2 required.',
            'future_export_only_reuse':'Same binding, grid/configuration and ALL check hashes plus unrounded T/C fingerprints required. Changed numerical results need fresh disclosure and user decision.',
            'communication_rule':'Before treating difficult self-imposed tolerances as hard blockers, disclose measured error, units, locations/times, likely impact and cost; ask user whether to accept or improve. Never present output decimal places as proved accuracy.'}
        target=hr.run_folder(row)/('error-acceptance-v1-'+uuid.uuid5(uuid.UUID(run_id),req.request_id).hex+'.json')
        if not target.exists():hr.write(target,record)
        if hr.read(target)!=record:raise WorkflowError('Acceptance record differs')
        hr.seal(row,target)
        ref={'path':hr.rel(target),'sha256':hr.sha_file(target),'revision':revision}
        p['error_acceptance_addendum']=ref;p.setdefault('error_acceptance_history',{})[req.request_id]=ref
        p.setdefault('accepted_reviews',{})['P1']=p1key
        p.update(review_suffix='-accepted-error-v1',recheck_rationale='New explicit user acceptance of exact disclosed self-imposed error criteria, not a claim that the original thresholds passed. Review all other requirements independently; original artifacts and rejected P2 retained.')
        validate(row);hr.save(w,row,'REVIEW_P2')
        return hr.status(w,task,run_id)


def register_author_visual_evidence(w,task,run_id,source):
    """Attach actual author readthrough, explicitly distinct from independent P2."""
    from . import hand_runtime as hr
    from pypdf import PdfReader
    with w.lock(task):
        row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload']
        key='P2-'+str(p['attempt'])+p.get('review_suffix','')
        if row['phase']!='REVIEW_P2' or key in p.get('ops',{}):
            raise WorkflowError('Visual evidence must precede an unclaimed new P2')
        path=hr.workspace_path(hr.ROOT,source)
        if path.is_symlink() or path.is_junction() or path.stat().st_size>100000:raise WorkflowError('Unsafe visual evidence')
        value=hr.read(path)
        if value.get('status') not in ('DEFECTS_FOUND','NO_DEFECTS_OBSERVED') or not value.get('observations'):
            raise WorkflowError('Record actual author observations, never independent/user visual PASS')
        packet=hr.read(hr.workspace_path(hr.ROOT,p['full_packet']))
        pdfs={a['path']:a for a in packet['artifacts'] if a['path'].endswith('.pdf')}
        records=value.get('records',[])
        if len(records)!=len(pdfs) or {v['source_path'] for v in records}!=set(pdfs):
            raise WorkflowError('Actual readthrough must cover every candidate PDF')
        items=[]
        for item in records:
            pdf=hr.workspace_path(hr.ROOT,item['source_path'])
            raw_preview=Path(item['preview'])
            relative_preview=(raw_preview.resolve().relative_to(hr.ROOT.resolve()).as_posix()
                if raw_preview.is_absolute() else item['preview'].replace('\\','/'))
            preview=hr.workspace_path(hr.ROOT,relative_preview)
            if (hr.sha_file(pdf)!=item['source_sha256'] or item['source_sha256']!=pdfs[item['source_path']]['sha256']
                    or len(PdfReader(pdf).pages)!=item['page_count'] or item['page_count']!=1):
                raise WorkflowError('Visual source/page evidence differs')
            if preview.is_symlink() or preview.is_junction():raise WorkflowError('Unsafe preview')
            hr.seal(row,preview)
            items.append({**item,'author_visual_status':'ACTUALLY_VIEWED_'+value['status'],
                          'preview_sha256':hr.sha_file(preview)})
        record={'protocol':'author-visual-evidence/1.0.0','binding':p['binding'],'role':'coding_author_self_check',
                'status':value['status'],'pages_viewed':sum(i['page_count'] for i in items),'records':items,
                'source_code_sha256':hr.sha_file(hr.workspace_path(hr.ROOT,p['full_code_path'])),
                'observations':value['observations'],'source_sha256':hr.sha_file(path),
                'independent_review':'THIS NEW P2 MUST ASSESS; no independent visual PASS claimed',
                'user_figure_selection':'NOT_GRANTED','result_approval':'NOT_GRANTED'}
        target=hr.run_folder(row)/('author-visual-evidence-'+digest(record)[:20]+'.json')
        if not target.exists():hr.write(target,record)
        if hr.read(target)!=record:raise WorkflowError('Visual record differs')
        hr.seal(row,target);p['author_visual_evidence']={'path':hr.rel(target),'sha256':hr.sha_file(target)}
        hr.save(w,row)
        return p['author_visual_evidence']


def resume_before_review_dispatch(w,task,run_id,*,request_id,reason):
    """Recover a proved local snapshot-preparation error; never replay a model call."""
    from . import hand_runtime as hr
    from .business_store import BusinessStore
    if not re_full_id(request_id) or not reason.strip():raise WorkflowError('Explicit recovery record required')
    with w.lock('business:task:'+task),w.lock(task):
        if BusinessStore(w.db).unresolved('task:'+task):raise WorkflowError('Resolve unknown operation first')
        row=hr.load(w,task,run_id);contract=hr.guard(w,row);p=row['payload'];accepted=validate(row)
        if not accepted:raise WorkflowError('No registered user acceptance')
        if request_id in p.get('acceptance_predispatch_recoveries',{}):return hr.status(w,task,run_id)
        key='P2-'+str(p['attempt'])+p.get('review_suffix','')
        if (row['phase']!='NEEDS_HUMAN' or p.get('failure_domain')!='review_output'
                or p.get('error_type')!='ValueError' or key in p.get('ops',{})
                or key in p.get('reviews',{}) or p.get('last_review',{}).get('attempt')==p['attempt']
                or (hr.run_folder(row)/(key+'-identity.json')).exists()):
            raise WorkflowError('No proved pre-dispatch review preparation failure')
        f=hr.run_folder(row);a=p['attempt'];packet=hr.read(hr.workspace_path(hr.ROOT,p['full_packet']))
        wrapper=hr.read(f/f'P2-{a}-code.json');inputs=hr.read(f/f'P2-{a}-input.json');result=hr.read(f/f'P2-{a}-result.json')
        if (wrapper!={'code':p['full_code'],'source_sha256':hr.sha_file(hr.workspace_path(hr.ROOT,p['full_code_path']))}
                or inputs!={'contract':contract,'job_inputs':packet['job']['inputs']}
                or result!=packet['json_outputs']):
            raise WorkflowError('Prepared review evidence differs from exact original artifacts')
        record={'request_id':request_id,'reason':reason,'binding':p['binding'],'review_stage_key':key,
            'no_reviewer_operation_or_identity':True,'original_failure_preserved':True,
            'attempt':p['attempt'],'retries':p['retries'],'acceptance':p['error_acceptance_addendum']}
        target=f/('acceptance-predispatch-recovery-'+digest(record)[:20]+'.json')
        if not target.exists():hr.write(target,record)
        if hr.read(target)!=record:raise WorkflowError('Recovery record differs')
        hr.seal(row,target);p.setdefault('acceptance_predispatch_recoveries',{})[request_id]={'path':hr.rel(target),'sha256':hr.sha_file(target)}
        hr.save(w,row,'REVIEW_P2');return hr.status(w,task,run_id)


def re_full_id(value):
    import re
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',value) is not None


def archive_author_visual_evidence(row,reason):
    """Preserve old views; changed exports require new actual views, never reuse PASS."""
    p=row['payload'];prior=p.pop('author_visual_evidence',None)
    if prior:p.setdefault('author_visual_evidence_history',[]).append({'record':prior,'reason':reason})
    return prior


def archive_before_new_full(w,task,run_id):
    from . import hand_runtime as hr
    with w.lock(task):
        row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload']
        if row['phase']!='EXECUTE_FULL' or p.get('full_packet') or not p.get('full_code_path'):
            raise WorkflowError('Only a new unexecuted full revision can archive previous visual observations')
        prior=archive_author_visual_evidence(row,'A new full source/export is awaiting execution; re-render and actually view all new PDF pages. Historical evidence and seals retained.')
        if prior:hr.save(w,row)
        return prior
