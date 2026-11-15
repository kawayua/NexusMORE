"""Versioned algorithm references and fixed educational checks, shared by harnesses.

Reading requires core only. Example execution requires the evidence extra, is
bounded to trusted packaged functions and never dispatches business model jobs.
"""
import argparse
import hashlib
import json
from .package_resources import resource,verify_resources

CATALOG='algorithms/knowledge/catalog.json'

def load_catalog():
    verify_resources()
    catalog=json.loads(resource(CATALOG).read_text(encoding='utf-8'))
    if catalog.get('schema_version')!='1.0.0' or catalog.get('knowledge_version')!='1.0.0':raise ValueError('Unsupported algorithm knowledge version')
    cards=catalog['algorithms'];ids=[c['id'] for c in cards]
    if len(ids)!=len(set(ids)) or len(ids)!=catalog['canonical_algorithm_count']:raise ValueError('Algorithm identity/count differs')
    categories={c['id']:c for c in catalog['categories']}
    coverage=catalog['source_coverage']
    if len(categories)!=7 or len(coverage)!=catalog['source_row_count']:raise ValueError('Algorithm coverage differs')
    for row in coverage:
        if row['category'] not in categories or row['algorithm_id'] not in categories[row['category']]['algorithm_ids']:raise ValueError('Invalid topic coverage')
    for card in cards:
        if not card['categories'] or not card['conditions'] or not card['failure_boundary'] or not card['counterexample']:raise ValueError('Missing mathematical conditions')
        if card['example']['id']!=card['id'] or card['example']['scope'] not in {'small_complete_solution','single_update','core_equation_check','stochastic_estimate'}:raise ValueError('Missing example scope')
        for category in card['categories']:
            if category not in categories or card['id'] not in categories[category]['algorithm_ids']:raise ValueError('Algorithm category differs')
    return catalog

def list_algorithms(category=None):
    catalog=load_catalog()
    if category is not None and category not in {c['id'] for c in catalog['categories']}:raise ValueError('Unknown algorithm category')
    return [{'id':c['id'],'name':c['name'],'categories':c['categories'],'case_scope':c['example']['scope'],'implementation_status':c['implementation_status']} for c in catalog['algorithms'] if category is None or category in c['categories']]

def read_algorithm(algorithm_id,category=None):
    catalog=load_catalog();card=next((c for c in catalog['algorithms'] if c['id']==algorithm_id),None)
    if card is None:raise ValueError('Unknown algorithm id')
    category=category or card['categories'][0]
    if category not in card['categories']:raise ValueError('Algorithm not in requested category')
    path,anchor=card['sections'][category].split('#')
    raw=resource(path).read_bytes();text=raw.decode('utf-8');marker='<a id="'+anchor+'"></a>'
    if text.count(marker)!=1:raise ValueError('Missing/duplicate algorithm section')
    section=marker+text.split(marker,1)[1].split('<a id="',1)[0]
    return {'knowledge_version':catalog['knowledge_version'],'algorithm':card,'category':category,'source':path,'source_sha256':hashlib.sha256(raw).hexdigest(),'catalog_sha256':hashlib.sha256(resource(CATALOG).read_bytes()).hexdigest(),'section_sha256':hashlib.sha256(section.encode('utf-8')).hexdigest(),'text':section,'formal_approval':False,'general_business_solver_registered':False}

def run_examples(ids=None,category=None):
    catalog=load_catalog();selected={c['id']:c for c in catalog['algorithms']}
    if category is not None:selected={c['id']:selected[c['id']] for c in list_algorithms(category)}
    if ids is not None:
        if not ids or len(ids)!=len(set(ids)) or any(i not in selected for i in ids):raise ValueError('Unknown, duplicate or empty example selection')
        selected={i:selected[i] for i in ids}
    import numpy as np
    from .algorithm_examples import EXAMPLES
    if set(EXAMPLES)!={c['id'] for c in catalog['algorithms']}:raise ValueError('Packaged code/case coverage differs')
    results=[]
    for key,card in selected.items():
        example=card['example']
        try:
            actual=np.asarray(EXAMPLES[key](),dtype=float);expected=np.asarray(example['expected'],dtype=float)
            passed=actual.shape==expected.shape and np.isfinite(actual).all() and np.isfinite(expected).all() and np.allclose(actual,expected,atol=example['absolute_tolerance'],rtol=example['relative_tolerance'])
            result={'id':key,'status':'passed' if passed else 'failed','actual':actual.tolist(),'expected':expected.tolist(),'max_absolute_error':float(np.max(abs(actual-expected))) if actual.shape==expected.shape else None,'scope':example['scope'],'absolute_tolerance':example['absolute_tolerance'],'relative_tolerance':example['relative_tolerance']}
        except Exception as exc:result={'id':key,'status':'failed','error':str(exc),'error_type':type(exc).__name__,'scope':example['scope']}
        results.append(result)
    return {'status':'passed' if all(r['status']=='passed' for r in results) else 'failed','knowledge_version':catalog['knowledge_version'],'cases':len(results),'results':results,'case_scope':'Fixed packaged educational examples; each result retains complete-solution vs component/update distinction','negative_boundaries':'Documented per algorithm; numeric boundary rejection separately tested, not all counterexamples executed','formal_approval':False,'independent_review':'NOT_RUN','general_business_solvers_registered':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('list');a.add_argument('--category')
    a=sub.add_parser('read');a.add_argument('--id',required=True);a.add_argument('--category')
    a=sub.add_parser('check-examples');a.add_argument('--id',action='append');a.add_argument('--category');a.add_argument('--output')
    args=p.parse_args()
    result=list_algorithms(args.category) if args.command=='list' else read_algorithm(args.id,args.category) if args.command=='read' else run_examples(args.id,args.category)
    if getattr(args,'output',None):
        with open(args.output,'x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    else:print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 1 if isinstance(result,dict) and result.get('status')=='failed' else 0

if __name__=='__main__':raise SystemExit(main())
