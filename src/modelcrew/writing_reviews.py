"""B+ file-level, independently scoped manuscript and figure-selection reviews.

Actors label trusted local actions; these functions never infer an approval.
"""
import json
from pathlib import Path
from .contracts import digest
from .collaboration import historical_paper_policy_sha256
from .modeling_paper import sha,inside,POLICY_PATH


def catalog_at(path):
    path=Path(path);value=json.loads(path.read_text(encoding='utf-8'))
    ids=[x['id'] for x in value['figures']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate figure IDs')
    for f in value['figures']:
        for asset in f['files'].values():
            if sha(inside(path.parent,asset['path']))!=asset['sha256']:raise ValueError('Changed figure bytes: '+f['id'])
    return value


def selection_snapshot(catalog_path,selected_ids):
    catalog=catalog_at(catalog_path);by_id={f['id']:f for f in catalog['figures']}
    if not selected_ids or len(selected_ids)!=len(set(selected_ids)) or not set(selected_ids)<=set(by_id):
        raise ValueError('Selection must contain unique known figure IDs')
    # Content identity is independent of numbering, file location and unused candidates.
    items=[]
    for fid in sorted(selected_ids):
        f=by_id[fid]
        items.append({'id':fid,'category':f['category'],'question_ids':f['question_ids'],
                      'title':f['title'],'purpose':f['purpose'],'source_kind':f.get('source_kind'),
                      'time_s':f.get('time_s'),'geometry':f.get('geometry'),
                      'limitation':f.get('limitation'),'statistics':f.get('statistics'),
                      'files':{fmt:asset['sha256'] for fmt,asset in sorted(f['files'].items())}})
    identity={'figures':items,'evidence':catalog.get('evidence'),'question_ids':catalog.get('question_ids')}
    if catalog.get('policy_override'):identity['policy_override']=catalog['policy_override']
    return {'selected_ids':sorted(selected_ids),'figures':items,'sha256':digest(identity),
            'policy_sha256':(historical_paper_policy_sha256() or sha(POLICY_PATH)),'source_catalog_sha256':sha(catalog_path)}


def manuscript_snapshot(markdown_path,catalog_path):
    catalog=catalog_at(catalog_path);formal=[f['id'] for f in catalog['figures'] if f['formal']]
    return {'markdown_sha256':sha(markdown_path),'embedded_figures_sha256':selection_snapshot(catalog_path,formal)['sha256'],
            'policy_sha256':(historical_paper_policy_sha256() or sha(POLICY_PATH))}


def selection_record(catalog_path,selected_ids,*,decision,actor,statement,reason):
    if decision not in ['approve','reject'] or not all(x.strip() for x in [actor,statement,reason]):
        raise ValueError('Explicit decision, actor, statement and reason required')
    return {'review_version':'2.0.0','kind':'figure_selection','decision':decision,
            'actor':actor,'user_statement':statement,'reason':reason,
            'snapshot':selection_snapshot(catalog_path,selected_ids),
            'scope':'Only the enumerated figure content; not manuscript approval, layout approval or permission to run a solver.'}


def manuscript_record(markdown_path,catalog_path,*,decision,actor,statement,reason):
    if decision not in ['approve','reject'] or not all(x.strip() for x in [actor,statement,reason]):
        raise ValueError('Explicit decision, actor, statement and reason required')
    return {'review_version':'2.0.0','kind':'manuscript','decision':decision,'actor':actor,
            'user_statement':statement,'reason':reason,'snapshot':manuscript_snapshot(markdown_path,catalog_path)}


def review_status(markdown_path,catalog_path,manuscript_review=None,figure_review=None, *, historical_policy_sha256=None):
    current=manuscript_snapshot(markdown_path,catalog_path);catalog=catalog_at(catalog_path)
    # Historical validation records what was approved then; it grants no current approval.
    if historical_policy_sha256 is not None:
        current['policy_sha256']=historical_policy_sha256
    text='pending'
    if manuscript_review:
        if manuscript_review.get('decision')=='approve' and manuscript_review.get('kind')=='manuscript' and manuscript_review.get('reason','').strip():
            text='approved' if manuscript_review.get('snapshot')==current else 'stale'
        elif manuscript_review.get('decision')=='reject':text='rejected'
    selected='pending'
    if figure_review:
        if figure_review.get('decision')=='approve' and figure_review.get('kind')=='figure_selection' and figure_review.get('reason','').strip():
            recorded=figure_review.get('snapshot',{});formal=[f['id'] for f in catalog['figures'] if f['formal']]
            if sorted(formal)!=recorded.get('selected_ids'):selected='stale'
            else:
                actual=selection_snapshot(catalog_path,formal)
                if historical_policy_sha256 is not None:actual['policy_sha256']=historical_policy_sha256
                selected='approved' if all(recorded.get(k)==actual[k] for k in ['sha256','policy_sha256']) else 'stale'
        elif figure_review.get('decision')=='reject':selected='rejected'
    return {'review_version':'2.0.0','manuscript':text,'figure_selection':selected,
            'can_export':text=='approved' and selected=='approved',
            'current_manuscript_snapshot':current,'current_catalog_sha256':sha(catalog_path),
            'scope':'File-level scope checks; no database/API authentication or automatic user approval.'}


def write_record_new(path,record):
    """Append-only through the application; existing files are never replaced."""
    with Path(path).open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2);f.write('\n')
