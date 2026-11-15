"""Structural validation deliberately separated from mathematical review."""
from .project_assets import asset_path
import hashlib,json,math
from pathlib import Path
from jsonschema import Draft202012Validator
from .config import ROOT
SCHEMAS={v:json.loads((asset_path(ROOT,f'contracts/model-contract-{v}.schema.json')).read_text(encoding='utf-8')) for v in ['1.0.0','1.1.0']}
SCHEMA=SCHEMAS['1.0.0']
class ContractError(ValueError):pass
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def validate(contract):
    schema=SCHEMAS.get(contract.get('schema_version')) if isinstance(contract,dict) else None
    if schema is None:raise ContractError('Unsupported contract schema version')
    errors=sorted(Draft202012Validator(schema).iter_errors(contract),key=lambda e:str(list(e.path)))
    if errors:raise ContractError('; '.join(f'{list(e.path)}: {e.message}' for e in errors))
    digest(contract) # JSON NaN/Infinity are not valid contract values.
    for group in ['sources','inputs','parameters','variables','assumptions','constraints','outputs','checks']:
        ids=[v['id'] for v in contract[group]]
        if len(ids)!=len(set(ids)):raise ContractError(f'duplicate {group} IDs')
    sources={v['id'] for v in contract['sources']};checks={v['id'] for v in contract['checks']}
    for group in ['inputs','parameters','assumptions']:
        for item in contract[group]:
            if item['source_id'] not in sources:raise ContractError(f'unknown source: {item["source_id"]}')
    for item in contract['constraints']:
        if item['check_id'] not in checks:raise ContractError(f'unknown check: {item["check_id"]}')
    for item in contract['parameters']:
        if item['origin']=='derived' and not item['derivation']:raise ContractError('derived parameter needs derivation')
    for item in contract['inputs']:
        structure=item.get('structure')
        if not structure:continue
        ids=[q['id'] for q in structure['pending']]
        if len(ids)!=len(set(ids)):raise ContractError('Duplicate input question IDs')
        for q in structure['pending']:
            if q['status']=='resolved' and (not q['resolution'] or not q['resolution'].strip()):raise ContractError('Resolved question needs a resolution')
            if q['status']=='unresolved' and q['resolution'] is not None:raise ContractError('Unresolved question cannot have a resolution')
        if structure['template_id']=='unsupported' and not any(q['blocking'] and q['status']=='unresolved' for q in structure['pending']):raise ContractError('Unsupported input needs a blocking question; supply a supported profile before approval')
        if structure['template_id'] in ['nested','parameters']:
            try:Draft202012Validator.check_schema(structure['observed']['data_schema'])
            except Exception as exc:raise ContractError('Invalid nested data schema') from exc
    return contract

def bench_review(contract):
    """Case-specific checks, not a general mathematical proof or auto approval."""
    validate(contract)
    p={v['id']:v for v in contract['parameters']}
    findings=[]
    for target,raw in [('head_gap','head_length'),('body_gap','body_length')]:
        if all(k in p for k in [target,raw,'hole_offset']):
            expected=p[raw]['value']-2*p['hole_offset']['value']
            if not math.isclose(p[target]['value'],expected,abs_tol=1e-10,rel_tol=0):findings.append(f'{target}: expected {expected}, got {p[target]["value"]}')
    return {'status':'failed' if findings else 'unknown','findings':findings,'note':'Only case-specific derived-distance checks; remaining mathematics requires human review.'}
