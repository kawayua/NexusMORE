"""Restore a proven misrouted full-generation failure; preserve retry history."""
from . import hand_runtime as hr
from .workflow import WorkflowError
from .contracts import digest
from .collaboration import sha_file,workspace_path
from .config import ROOT


def proof(row,baseline,events):
    p=row['payload'];b=baseline['payload'];f=hr.run_folder(row)
    if (row['hand']!='coding' or row['phase']!='GENERATE_MINIMAL'
            or p.get('failure_domain')!='implementation' or p.get('rework_target')!='coding'
            or p.get('attached') or p.get('full_code_path')
            or baseline['phase']!='GENERATE_FULL' or p['attempt']<=b['attempt']):
        raise WorkflowError('Not an unchanged full-generation misroute')
    key=b.get('accepted_reviews',{}).get('P1');review=b.get('reviews',{}).get(key)
    if not review or review['status']!='PASS' or p.get('reviews',{}).get(key)!=review:
        raise WorkflowError('Original independent P1 missing or changed')
    # The whole accepted slice, author lineage and jobs must remain unchanged.
    for name in ('binding','minimal_code','minimal_code_path','minimal_packet','current_author','lineage','jobs','sealed'):
        if p.get(name)!=b.get(name):raise WorkflowError('Accepted slice changed: '+name)
    if p['retries']-b['retries']!=p['attempt']-b['attempt']:
        raise WorkflowError('Unexpected retry history')
    if any(e['payload'].get('minimal_code_path')!=b.get('minimal_code_path')
           or e['payload'].get('current_author')!=b.get('current_author')
           or e['payload'].get('full_code_path') for e in events):
        raise WorkflowError('Author output changed after P1')
    evidence={}
    for a in range(b['attempt'],p['attempt']):
        opkey=('code-full-' if a==b['attempt'] else 'code-minimal-')+str(a)
        op=p.get('ops',{}).get(opkey,{})
        folder=f/'operations'/opkey;paths=list(folder.glob('Coder-*-metadata.json'))
        if op.get('state')!='claimed' or len(paths)!=1 or (folder/'answer.json').exists():
            raise WorkflowError('No unique incomplete author response')
        meta=hr.read(paths[0]);ident=meta.get('call_id')
        request=folder/('Coder-'+str(ident)+'-request.json');response=folder/('Coder-'+str(ident)+'-response.json')
        if (meta.get('http_status')!=200 or meta.get('finish_reason')!='length'
                or meta.get('status')!='invalid_response' or not response.is_file()
                or sha_file(response)!=meta.get('response_sha256')):
            raise WorkflowError('Author outcome is not a known length truncation')
        import json
        data=json.loads(hr.read(request)['messages'][1]['content'])
        raw=hr.read(response)
        if (digest(data)!=op.get('request_sha256') or data.get('binding')!=p['binding']
                or data.get('previous_minimal_code')!=p['minimal_code']
                or raw['choices'][0].get('finish_reason')!='length'):
            raise WorkflowError('Truncated request or response identity differs')
        evidence[opkey]={hr.rel(x):sha_file(x) for x in (paths[0],request,response)}
    if 'code-full-'+str(p['attempt']) in p.get('ops',{}) or 'code-minimal-'+str(p['attempt']) in p.get('ops',{}):
        raise WorkflowError('Current attempt already claimed')
    return {'recovery_kind':'unchanged_p1_after_full_generation_truncation',
            'baseline_event_id':baseline['id'],'P1_key':key,'P1_review':review,
            'attempt':p['attempt'],'retries':p['retries'],'original_evidence':evidence,
            'minimal_sha256':sha_file(workspace_path(ROOT,p['minimal_code_path']))}


def recover(w,task,run,*,request_id,reason,apply=False):
    if not request_id.strip() or not reason.strip():raise WorkflowError('Recovery identity and reason required')
    with w.lock('business:task:'+task),w.lock(task),w.db.transaction():
        from .business_store import BusinessStore
        if BusinessStore(w.db).unresolved('task:'+task):raise WorkflowError('Resolve original business fence first')
        row=hr.load(w,task,run);hr.guard(w,row);p=row['payload']
        if w.task(task)['result_revision']:raise WorkflowError('Result already registered')
        previous=p.get('full_generation_recovery')
        if previous:
            if previous['request_id']!=request_id:raise WorkflowError('Recovery already registered')
            return {'applied':True,'replayed':True,'evidence':previous}
        events=w.db.execute('SELECT id,phase,payload FROM mc_hand_events WHERE run_id=%s ORDER BY id',(run,)).fetchall()
        candidates=[e for e in events if e['phase']=='GENERATE_FULL' and e['payload'].get('accepted_reviews',{}).get('P1')]
        if not candidates:raise WorkflowError('No durable full-stage P1 baseline')
        baseline=candidates[-1];later=[e for e in events if e['id']>baseline['id']]
        evidence=proof(row,baseline,later)
        store=hr.CollaborationStore(hr.run_folder(row)/'records');review=evidence['P1_review']
        receipt=store.load(hr.Receipt,review['receipt_sha256'])
        if store.accept_review(receipt,review['snapshot_sha256'])!=review['receipt_sha256']:
            raise WorkflowError('P1 snapshot or receipt changed')
        evidence.update(request_id=request_id,reason=reason)
        if apply:
            path=hr.run_folder(row)/('full-generation-recovery-'+digest(evidence)+'.json')
            hr.write(path,evidence);hr.seal(row,path)
            p['full_generation_recovery']=evidence;p['accepted_reviews']={'P1':evidence['P1_key']}
            p['coding_failure_stage']='full'
            hr.save(w,row,'GENERATE_FULL')
        return {'applied':apply,'replayed':False,'evidence':evidence}
