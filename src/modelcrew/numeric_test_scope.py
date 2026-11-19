"""Local-operator adoption of a single-run, explicitly confirmed zero-figure test.

No MCP/HTTP registration. This is a numerical engineering acceptance scope,
never a paper-policy override or a result/user approval.
"""
from .collaboration import sha_file, workspace_path
from .modeling_paper import POLICY_PATH
from .workflow import WorkflowError

PROTOCOL='nexusmore-numeric-only-test/1'
FIGURE_FAILURES={'Full run needs real figure-catalog.json','Candidate/formal figure policy incomplete'}


def pre_p2_figure_failure(row):
    p=row['payload'];stage='P2-'+str(p['attempt'])
    return (row['hand']=='coding' and row['phase']=='NEEDS_HUMAN' and p['retries']==3
        and p.get('feedback',{}).get('error') in FIGURE_FAILURES
        and p.get('failure_domain') in ('implementation','review_output')
        and p.get('last_review',{}).get('gate')=='P1'
        and not any(k.startswith(stage) for k in p.get('ops',{})))


def validate(row):
    p=row['payload'];ref=p.get('numeric_only_scope')
    if ref is None:return None
    from . import hand_runtime as hr
    if not isinstance(ref,dict) or set(ref)!={'path','sha256'}:raise WorkflowError('Invalid numeric-only scope reference')
    path=workspace_path(hr.ROOT,ref['path'])
    if p['sealed'].get(ref['path'])!=ref['sha256'] or sha_file(path)!=ref['sha256']:
        raise WorkflowError('Numeric-only scope changed or not sealed')
    value=hr.read(path)
    _validate_value(row,value)
    return value


def _validate_value(row,value):
    p=row['payload']
    if (value.get('protocol')!=PROTOCOL or value.get('run_id')!=str(row['id'])
        or value.get('binding')!=p['binding'] or value.get('actor')!='user'
        or not value.get('user_statement','').strip() or not value.get('decision_context','').strip()
        or not value.get('reason','').strip() or value.get('base_paper_policy_sha256')!=sha_file(POLICY_PATH)
        or value.get('figures')!={'minimum_candidates':0,'minimum_formal':0,'allowed_count':0}
        or value.get('scope')!='numeric_result_acceptance_only'
        or value.get('required_gates')!=['P1','full_execution','byte_reproduction','P2','user_result_confirmation']
        or value.get('paper_export_allowed') is not False):
        raise WorkflowError('Numeric-only scope does not match this engineering run')


def adopt(w,task,run_id,source):
    """Trusted operator supplies the user's actual scoped decision record."""
    from . import hand_runtime as hr
    with w.lock(task):
        row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload']
        path=workspace_path(hr.ROOT,source)
        if path.is_symlink() or path.is_junction() or path.stat().st_size>20000:
            raise WorkflowError('Unsafe numeric-only scope record')
        value=hr.read(path)
        _validate_value(row,value)
        if p.get('numeric_only_scope'):
            if p['numeric_only_scope']['sha256']!=sha_file(path):raise WorkflowError('Numeric-only scope already frozen')
            validate(row);return hr.status(w,task,run_id)
        if not pre_p2_figure_failure(row) or p.get('attached') or w.task(task)['result_revision']:
            raise WorkflowError('Only exhausted pre-P2 figure preparation may adopt this test scope')
        # Do not exempt a declared graphical/PDF deliverable in the approved model.
        contract=hr.read(hr.run_folder(row)/'contract.json')
        if any(not item['path'].endswith('.json') for item in contract['outputs']):
            raise WorkflowError('Declared non-JSON deliverables cannot use a numeric-only scope')
        target=hr.run_folder(row)/'numeric-only-test-scope.json'
        if not target.exists():hr.write(target,value)
        if hr.read(target)!=value:raise WorkflowError('Numeric-only scope recovery differs')
        previous=dict(p['sealed'])
        ref={'path':hr.rel(target),'sha256':sha_file(target)}
        p['numeric_only_scope']=ref;hr.seal(row,target)
        try:validate(row)
        except BaseException:
            p.pop('numeric_only_scope',None);p['sealed']=previous;raise
        hr.save(w,row)
        return hr.status(w,task,run_id)


def validate_empty_catalog(row,packet,catalog):
    from pathlib import Path
    scope=validate(row)
    if scope is None:raise WorkflowError('Explicit run-scoped numeric-only decision required')
    if catalog.get('figures')!=[] or catalog.get('numeric_only_scope_sha256')!=row['payload']['numeric_only_scope']['sha256']:
        raise WorkflowError('Numeric-only catalog must explicitly declare zero figures and scope hash')
    forbidden={'.png','.pdf','.svg','.jpg','.jpeg','.tif','.tiff','.webp','.docx','.tex'}
    if any(Path(a['path']).suffix.lower() in forbidden for a in packet['artifacts']):
        raise WorkflowError('Numeric-only run contains graphical or paper outputs')
    return scope
