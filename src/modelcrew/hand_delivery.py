"""Explicit local recovery of a proven pre-HTTP reviewer delivery failure.

Read timeouts, HTTP replies and ambiguous transport failures remain fenced.
No cached output is manufactured, no author or review budget is reset.
"""
import json
from .contracts import digest
from .workflow import WorkflowError


def delivery_proof(folder, stage, request_sha256):
    paths=list(folder.glob(stage+'-*-metadata.json'))
    if len(paths)!=1 or (folder/'answer.json').exists() or list(folder.glob('*-response.json')):
        raise WorkflowError('Exactly one undelivered call and no response required')
    path=paths[0];meta=json.loads(path.read_text(encoding='utf-8'))
    if (meta.get('status') not in ('unknown','not_sent')
            or meta.get('error_type') not in ('ConnectError','ConnectTimeout')
            or meta.get('http_status') is not None or meta.get('stage')!=stage):
        raise WorkflowError('Cannot prove HTTP request was not delivered')
    identifier=meta.get('call_id')
    if path.name!=stage+'-'+str(identifier)+'-metadata.json':
        raise WorkflowError('Call metadata identity differs')
    request=folder/(stage+'-'+identifier+'-request.json')
    raw=json.loads(request.read_text(encoding='utf-8'))
    content=raw['messages'][1]['content']
    if isinstance(content,list):
        import base64,hashlib
        if not content or content[0].get('type')!='text':raise WorkflowError('Invalid multimodal request proof')
        data=json.loads(content[0]['text']);images=[p for p in content if p.get('type')=='image_url']
        declared=data.get('actual_image_dispatch',[])
        if len(images)!=len(declared) or len(images)!=meta.get('image_count'):
            raise WorkflowError('Multimodal delivery image coverage differs')
        for image,expected in zip(images,declared):
            url=image['image_url']['url']
            if not url.startswith('data:image/png;base64,'):raise WorkflowError('Unsupported image proof')
            encoded=base64.b64decode(url.split(',',1)[1],validate=True)
            if hashlib.sha256(encoded).hexdigest()!=expected['sha256']:
                raise WorkflowError('Multimodal delivery image bytes differ')
    else:data=json.loads(content)
    if digest(data)!=request_sha256:
        raise WorkflowError('Original provider input differs')
    from .hand_runtime import sha_file
    return {path.name:sha_file(path),request.name:sha_file(request)}


def consume_authorization(w,row,key,folder,stage):
    """Consume an explicit one-use proof before issuing any new HTTP request."""
    from . import hand_runtime as hr
    op=row['payload']['ops'][key];auth=op.get('delivery_retry_authorization')
    if not auth or auth.get('consumed'):return False
    if auth['evidence']!=delivery_proof(folder,stage,op['request_sha256']):
        raise WorkflowError('Delivery recovery evidence changed')
    auth['consumed']=True
    hr.save(w,row)
    return True


def recover_reviewer_delivery(w,task,run,original_request_id,*,retry_id,reason,apply=False):
    """Trusted local maintenance; no model/user approval is created here."""
    from . import hand_runtime as hr
    from .business_adapter import failure
    from .business_adapter import resource_for
    from .business_store import BusinessStore
    from .business_contract import request_digest,validate_response
    if not reason.strip() or not retry_id.strip():raise WorkflowError('Explicit retry identity and reason required')
    scope={'project_id':w.task(task)['project_id'],'task_id':task,'run_id':run}
    with w.lock('business:'+resource_for(scope)),w.lock(task),w.db.transaction():
        store=BusinessStore(w.db);business=store.get(scope,'hand_advance',original_request_id)
        row=hr.load(w,task,run);hr.guard(w,row);p=row['payload']
        if not business or business['request_sha256']!=request_digest(business['request']):
            raise WorkflowError('Original business operation missing or changed')
        args=business['request']['arguments']
        if args!={'task_id':task,'run_id':run}:raise WorkflowError('Only plain original review advance is recoverable')
        last=p.get('last_review',{});key=last.get('stage_key');gate=last.get('gate')
        op=p.get('ops',{}).get(key,{})
        previous=op.get('delivery_retry_authorization')
        if previous:
            if previous['retry_id']!=retry_id:raise WorkflowError('Delivery retry already registered')
            return {'applied':True,'replayed':True,'evidence':previous}
        if (business['state']!='outcome_unknown' or row['phase']!='PROVIDER_UNKNOWN'
                or gate not in ('P1','P2','W1') or last.get('attempt')!=p['attempt']
                or p.get('recovery_phase')!='REVIEW_'+gate or op.get('state')!='claimed'
                or key in p.get('reviews',{})):
            raise WorkflowError('No current unresolved undelivered review')
        folder=hr.run_folder(row)/'operations'/key
        proof=delivery_proof(folder,gate,op['request_sha256'])
        evidence={'recovery_kind':'reviewer_proven_not_sent','retry_id':retry_id,'reason':reason,
                  'original_request_id':original_request_id,'evidence':proof,'consumed':False,
                  'review_key':key,'attempt':p['attempt'],'author_retries_unchanged':p['retries']}
        if apply:
            response=failure('hand_advance','dependency_unavailable',original_request_id)
            response.update(binding=scope,data=evidence,receipt={**store.receipt(business),'state':'failed'})
            validate_response(response);store.save(business,'failed',response)
            op['delivery_retry_authorization']=evidence
            hr.save(w,row,'REVIEW_'+gate)
        return {'applied':apply,'replayed':False,'evidence':evidence}
