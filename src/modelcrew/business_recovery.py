"""Trusted local recovery of proven pre-dispatch rejections; never redispatch."""
import argparse
import getpass
import json

from .business_adapter import failure
from .business_contract import BusinessContractError, request_digest, validate_response
from .business_store import BusinessStore
from .contracts import digest


def recover_missing_math(w, task_id, request_id, *, apply=False):
    """Resolve only the missing-math rejection, under business and native locks.

    Absence of a receipt alone is never proof. Require a mathematical baseline
    committed before the claim, a request that necessarily fails the core guard,
    and no new-version effects. Anything else remains fenced for investigation.
    """
    with w.lock('business:task:'+task_id), w.lock(task_id), w.db.transaction():
        task=w.task(task_id)
        scope={'project_id':task['project_id'],'task_id':task_id}
        store=BusinessStore(w.db)
        row=store.get(scope,'task_revise',request_id)
        if row is None:
            raise ValueError('No matching task revision record')
        if row['request_sha256']!=request_digest(row['request']) or row['scope_sha256']!=digest(scope):
            raise ValueError('Stored request identity differs')
        request=row['request'];args=request['arguments'];body=args['body']
        if (request['operation']!='task_revise' or request['request_id']!=request_id
                or args['task_id']!=task_id or body['kind']!='revise_model'
                or body.get('math_package') is not None
                or row['resource_key']!='task:'+task_id
                or row['legacy_domain']!='actions:'+task_id):
            raise ValueError('Not a missing-math model revision')
        # An already saved recovery is replayed without appending another event.
        if row['state']=='failed' and (row.get('response') or {}).get('data',{}).get('recovery_kind')=='missing_math_pre_dispatch_rejection':
            return {'applied':True,'replayed':True,'receipt':store.receipt(row),
                    'evidence':row['response']['data']}
        if row['state'] not in ('claimed','dispatched','outcome_unknown'):
            raise ValueError('Operation is not unresolved')
        version=body['version']
        if (task['current_version']!=version or task['phase']!='WAITING_MODEL_APPROVAL'
                or task['model_approved']):
            raise ValueError('Task has advanced; recovery refused')
        source=w.db.execute('SELECT revision,sha256,created_at FROM mc_math_packages '
            'WHERE task_id=%s AND version=%s AND created_at<%s ORDER BY revision LIMIT 1',
            (task_id,version,row['created_at'])).fetchone()
        receipt=w.db.execute('SELECT 1 FROM mc_requests WHERE task_id=%s AND request_id=%s',
            (task_id,request_id)).fetchone()
        contracts=w.db.execute('SELECT 1 FROM mc_contracts WHERE task_id=%s AND version>%s',
            (task_id,version)).fetchone()
        mathematics=w.db.execute('SELECT 1 FROM mc_math_packages WHERE task_id=%s AND version>%s',
            (task_id,version)).fetchone()
        if source is None or receipt or contracts or mathematics:
            raise ValueError('Cannot prove the revision was rejected before writes')
        evidence={'recovery_kind':'missing_math_pre_dispatch_rejection',
                  'task_id':task_id,'version':version,'original_request_sha256':row['request_sha256'],
                  'source_math_revision':source['revision'],'source_math_sha256':source['sha256'],
                  'source_math_predates_claim':True,'core_receipt_present':False,
                  'new_contract_present':False,'new_math_present':False,
                  'previous_state':row['state'],'operator':getpass.getuser(),
                  'reason':'Core rejects a revision that drops an existing mathematical package'}
        if apply:
            response=failure('task_revise','invalid_request',request_id)
            response['binding']=scope;response['data']=evidence
            response['receipt']={**store.receipt(row),'state':'failed'}
            validate_response(response)
            row=store.save(row,'failed',response)
        return {'applied':apply,'replayed':False,'receipt':store.receipt(row),'evidence':evidence}



def recover_used_hand_recheck(w, task_id, request_id, *, apply=False):
    """Resolve only a second recheck proven rejected before any core effect."""
    from . import hand_runtime as hr
    with w.lock('business:task:'+task_id), w.lock(task_id), w.db.transaction():
        row=w.db.execute('SELECT * FROM mc_business_operations WHERE resource_key=%s AND operation=%s AND request_id=%s',
                         ('task:'+task_id,'hand_recheck',request_id)).fetchone()
        if row is None:raise ValueError('No matching hand recheck record')
        req=row['request'];args=req['arguments'];run_id=args['run_id'];task=w.task(task_id)
        scope=dict(project_id=task['project_id'],task_id=task_id,run_id=run_id)
        if (req.get('operation')!='hand_recheck' or req.get('request_id')!=request_id
                or args['task_id']!=task_id or row['scope']!=scope
                or row['scope_sha256']!=digest(scope) or row['request_sha256']!=request_digest(req)
                or row['legacy_domain'] is not None):
            raise ValueError('Stored request identity differs')
        store=BusinessStore(w.db)
        if row['state']=='failed' and (row.get('response') or {}).get('data',{}).get('recovery_kind')=='used_hand_recheck_pre_dispatch_rejection':
            return dict(applied=True,replayed=True,receipt=store.receipt(row),evidence=row['response']['data'])
        if row['state'] not in ('claimed','dispatched','outcome_unknown'):
            raise ValueError('Operation is not unresolved')
        run=hr.load(w,task_id,run_id);hr.guard(w,run)
        event=w.db.execute('SELECT id,phase,payload FROM mc_hand_events WHERE run_id=%s AND created_at<%s ORDER BY id DESC LIMIT 1',
                           (run_id,row['created_at'])).fetchone()
        previous=w.db.execute("SELECT request_id,response FROM mc_business_operations WHERE scope_sha256=%s AND operation='hand_recheck' AND state='succeeded' AND updated_at<%s ORDER BY created_at DESC LIMIT 1",
                              (row['scope_sha256'],row['created_at'])).fetchone()
        if (not event or event['payload'].get('recheck_used') is not True
                or not hr.recheck_attempt_usage(event['payload'])['used_this_attempt']
                or event['phase']!=run['phase'] or digest(event['payload'])!=digest(run['payload'])
                or run['phase']!='NEEDS_HUMAN' or run['payload'].get('failure_domain')!='review_output'
                or not previous or previous['response'].get('data',{}).get('run_id')!=run_id
                or previous['response'].get('phase') not in ('REVIEW_P1','REVIEW_P2','REVIEW_W1')):
            raise ValueError('Cannot prove prior spent recheck and unchanged rejected core state')
        evidence=dict(recovery_kind='used_hand_recheck_pre_dispatch_rejection',task_id=task_id,run_id=run_id,
                      original_request_sha256=row['request_sha256'],prior_request_id=previous['request_id'],
                      prior_event_id=event['id'],core_payload_sha256=digest(run['payload']),
                      recheck_used_before_claim=True,core_state_unchanged=True,previous_state=row['state'],
                      operator=getpass.getuser(),reason='Core rejects a second recheck before saving or calling a reviewer')
        if apply:
            response=failure('hand_recheck','workflow_conflict',request_id)
            response.update(binding=scope,data=evidence,receipt={**store.receipt(row),'state':'failed'})
            validate_response(response);row=store.save(row,'failed',response)
        return dict(applied=apply,replayed=False,receipt=store.receipt(row),evidence=evidence)

def recover_unchanged_contract(w, task_id, request_id, *, apply=False, root=None):
    """Resolve the core's deterministic unchanged-contract guard, never resend.

    A version staying unchanged is insufficient: verify original file hashes,
    canonical input identity, predating baseline and no committed core request.
    """
    from .business_artifacts import ArtifactRegistry
    from .revision_files import resolve
    from .config import ROOT
    import copy
    root=ROOT if root is None else root
    with w.lock('business:task:'+task_id), w.lock(task_id), w.db.transaction():
        task=w.task(task_id);scope={'project_id':task['project_id'],'task_id':task_id}
        store=BusinessStore(w.db);row=store.get(scope,'task_revise',request_id)
        if row is None:raise ValueError('No matching revision')
        req=row['request'];args=req['arguments'];body=copy.deepcopy(args['body'])
        if (row['scope_sha256']!=digest(scope) or row['request_sha256']!=request_digest(req)
                or row['resource_key']!='task:'+task_id or row['legacy_domain']!='actions:'+task_id
                or req['operation']!='task_revise' or req['request_id']!=request_id
                or args['task_id']!=task_id or body['request_id']!=request_id
                or body['kind']!='revise_model'):
            raise ValueError('Original request identity differs')
        kind='unchanged_contract_pre_write_rejection'
        if row['state']=='failed' and (row.get('response') or {}).get('data',{}).get('recovery_kind')==kind:
            return dict(applied=True,replayed=True,receipt=store.receipt(row),evidence=row['response']['data'])
        if row['state'] not in ('claimed','dispatched','outcome_unknown'):raise ValueError('Not unresolved')
        version=body['version']
        if (task['current_version']!=version or task['model_approved'] or task['phase']!='WAITING_MODEL_APPROVAL'
                or task['executor_key']!='pending-code' or body.get('executor_key') not in (None,'pending-code')
                or body.get('executor_config') or task['executor_config']):
            raise ValueError('Current task/backend differs')
        source=w.db.execute('SELECT content,sha256,created_at FROM mc_contracts WHERE task_id=%s AND version=%s',
            (task_id,version)).fetchone()
        if not source or source['created_at']>=row['created_at']:raise ValueError('Baseline must predate dispatch')
        expected=req.get('expected_binding',{})
        if (expected.get('version')!=version or expected.get('contract_sha256')!=source['sha256']
                or expected.get('task_id')!=task_id):raise ValueError('No exact expected baseline')
        if args.get('revision_files'):body.update(resolve(root,args['revision_files']))
        if body.get('contract') is None:raise ValueError('No contract submitted')
        registry=ArtifactRegistry(w,root)
        for item in body['contract'].get('inputs',[]):
            path,sha=registry.resolve_input(item['path'],{**scope,'version':version})
            if sha!=item['sha256']:raise ValueError('Input changed')
            item['path']=path
        if digest(body['contract'])!=source['sha256']:raise ValueError('Contract really changed')
        receipt=w.db.execute('SELECT 1 FROM mc_requests WHERE task_id=%s AND request_id=%s',
            (task_id,request_id)).fetchone()
        future=w.db.execute('SELECT 1 FROM mc_contracts WHERE task_id=%s AND version>%s',(task_id,version)).fetchone()
        math_future=w.db.execute('SELECT 1 FROM mc_math_packages WHERE task_id=%s AND version>%s',(task_id,version)).fetchone()
        if receipt or future or math_future:raise ValueError('Committed/advanced state prevents failure recovery')
        evidence=dict(recovery_kind=kind,task_id=task_id,version=version,
            original_request_sha256=row['request_sha256'],contract_sha256=source['sha256'],
            baseline_predates_claim=True,canonical_contract_unchanged=True,backend_unchanged=True,
            core_receipt_present=False,new_version_present=False,no_redispatch=True,
            previous_state=row['state'],reason='Core revise_model rejects an unchanged contract before version writes; use revise_mathematics for math-only changes')
        if apply:
            response=failure('task_revise','invalid_request',request_id)
            response.update(binding=scope,data=evidence,receipt={**store.receipt(row),'state':'failed'})
            validate_response(response);row=store.save(row,'failed',response)
        return dict(applied=apply,replayed=False,receipt=store.receipt(row),evidence=evidence)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',required=True)
    parser.add_argument('--request-id',required=True)
    parser.add_argument('--kind',choices=['missing-math','used-hand-recheck','unchanged-contract'],default='missing-math')
    parser.add_argument('--apply',action='store_true',help='Save proven failure; default is read-only inspection')
    args=parser.parse_args()
    from .workflow import Workflow
    try:
        with Workflow() as w:
            recover={'missing-math':recover_missing_math,'used-hand-recheck':recover_used_hand_recheck,
                     'unchanged-contract':recover_unchanged_contract}[args.kind]
            result=recover(w,args.task,args.request_id,apply=args.apply)
    except (ValueError,BusinessContractError):
        parser.exit(1,'Recovery refused: evidence does not establish this pre-dispatch rejection.\n')
    print(json.dumps(result,ensure_ascii=False,default=str))


if __name__=='__main__':
    main()
