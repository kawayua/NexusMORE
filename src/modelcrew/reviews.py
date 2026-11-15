"""Evidence-bound interpretation review. Free narrative is never silently proved."""
from .project_assets import asset_path
from datetime import datetime,timezone
from pathlib import Path
import json,math,zipfile
import numpy as np
from jsonschema import Draft202012Validator
from .inputs import file_hash
from .config import ROOT
from .contracts import digest

CLAIMS_SCHEMA=json.loads((asset_path(ROOT,'contracts/interpretation-claims-1.0.0.schema.json')).read_text(encoding='utf-8'))

def artifact_status(artifact):
    path=Path(artifact['path'])
    if not path.is_absolute():path=asset_path(ROOT,path)
    try:
        if not path.is_file():return 'missing'
        return 'verified' if file_hash(path).lower()==artifact['sha256'].lower() else 'changed'
    except OSError:return 'unreadable'

def validate_claims(value):
    errors=list(Draft202012Validator(CLAIMS_SCHEMA).iter_errors(value))
    if errors:raise ValueError('Invalid interpretation claims: '+errors[0].message)
    digest(value)
    ids=[c['id'] for c in value['claims']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate interpretation claim IDs')
    return value

def _source_label(source):
    selector=source['selector'];suffix=json.dumps(selector,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return source['output_id']+'.'+source['field']+suffix

def render_claims(value):
    validate_claims(value)
    return '\n'.join(c['id']+': '+_source_label(c['source'])+' '+c['operator']+' '+(_source_label(c['compare_to']) if 'compare_to' in c else repr(c['expected']))+' '+c['unit']+'; abs_tolerance='+repr(c['abs_tolerance']) for c in value['claims'])

class EvidenceUnknown(ValueError):pass

def _read_scalar(source,unit,contract,execution,cache):
    output=next((o for o in contract['content']['outputs'] if o['id']==source['output_id']),None)
    if output is None:raise ValueError('Unknown contract output')
    definition=next((f for f in output['fields'] if f['name']==source['field']),None)
    if definition is None:raise ValueError('Unknown contract output field')
    if definition['unit']!=unit:raise ValueError('Claim unit differs from contract field unit')
    candidates=[a for a in execution['artifacts'] if a['sha256']==source['artifact_sha256'] and Path(a.get('origin_path',a['path'])).name==Path(output['path']).name]
    if not candidates:raise ValueError('Evidence is not an artifact of this execution/output')
    artifact=candidates[0]
    if artifact_status(artifact)!='verified':raise ValueError('Evidence artifact changed or missing')
    key=(artifact['sha256'],source['field'])
    if key not in cache:
        path=Path(artifact['path']);path=path if path.is_absolute() else asset_path(ROOT,path)
        if path.stat().st_size>40*1024*1024:raise ValueError('Evidence size exceeds review limit')
        if output['format'].lower()=='npz':
            with zipfile.ZipFile(path) as archive:
                if sum(x.file_size for x in archive.infolist())>40*1024*1024:raise ValueError('Expanded evidence exceeds review limit')
            with np.load(path,allow_pickle=False) as data:
                if source['field'] not in data.files:raise ValueError('Evidence field missing')
                array=data[source['field']].copy()
        elif output['format'].lower()=='json':
            raw=json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(raw,dict) or source['field'] not in raw:raise ValueError('JSON evidence needs a top-level contract field')
            array=np.asarray(raw[source['field']])
        else:raise EvidenceUnknown('This output format does not yet have a numeric interpretation reviewer')
        if list(array.shape)!=definition['shape']:raise ValueError('Evidence shape differs from contract field shape')
        if not np.issubdtype(array.dtype,np.number) or np.issubdtype(array.dtype,np.complexfloating) or not np.all(np.isfinite(array)):raise ValueError('Evidence must contain finite real numbers')
        cache[key]=array
    array=cache[key];selector=source['selector']
    if 'index' in selector:
        index=tuple(selector['index'])
        if len(index)!=array.ndim:raise ValueError('Claim index must select exactly one scalar')
        try:value=float(array[index])
        except IndexError as exc:raise ValueError('Claim index outside evidence shape') from exc
    else:
        if not array.size:raise ValueError('Cannot reduce empty evidence')
        value=float({'min':np.min,'max':np.max,'mean':np.mean}[selector['reduce']](array))
    if not math.isfinite(value):raise ValueError('Nonfinite selected evidence')
    return value

def review_interpretation(contract,execution,text,claims=None,structured_only=False):
    if claims is not None:validate_claims(claims)
    if structured_only and claims is None:raise ValueError('Structured-only explanation needs claims')
    canonical=render_claims(claims) if claims is not None else None
    if structured_only:text=canonical
    evidence=[{**a,'integrity':artifact_status(a)} for a in execution['artifacts']]
    bound=execution['contract_sha256']==contract['sha256']
    integrity_failed=not bound or not evidence or any(a['integrity']!='verified' for a in evidence)
    checks=[];cache={}
    for claim in claims['claims'] if claims else []:
        check={'id':claim['id'],'claim':claim,'status':'unknown'}
        try:
            if integrity_failed:raise ValueError('Execution binding or artifact integrity failed')
            left=_read_scalar(claim['source'],claim['unit'],contract,execution,cache)
            right=_read_scalar(claim['compare_to'],claim['unit'],contract,execution,cache) if 'compare_to' in claim else claim['expected']
            tolerance=claim['abs_tolerance'];op=claim['operator']
            passed=abs(left-right)<=tolerance if op=='eq' else (left<=right+tolerance if op=='le' else left>=right-tolerance)
            check.update(status='passed' if passed else 'failed',observed=left,expected_or_compared=right,abs_tolerance=tolerance,unit=claim['unit'],reason='Evidence comparison satisfied' if passed else 'Interpretation claim contradicts evidence within declared tolerance')
        except EvidenceUnknown as exc:check.update(status='unknown',reason=str(exc))
        except (ValueError,KeyError,OSError,zipfile.BadZipFile) as exc:check.update(status='failed',reason=str(exc))
        checks.append(check)
    claim_status='failed' if any(c['status']=='failed' for c in checks) else ('passed' if checks and all(c['status']=='passed' for c in checks) else 'unknown')
    narrative_status='structured_only' if structured_only else 'unknown'
    semantic_status='failed' if claim_status=='failed' else ('passed' if structured_only and claim_status=='passed' else 'unknown')
    status='failed' if integrity_failed or semantic_status=='failed' else semantic_status
    return {'status':status,'mode':execution['mode'],'kind':'interpretation_review','reviewed_at':datetime.now(timezone.utc).isoformat(),
            'execution_id':str(execution['id']),'contract_sha256':contract['sha256'],'contract_binding':bound,'artifacts':evidence,
            'interpretation':text,'interpretation_sha256':digest(text),'claims':claims,'claims_status':claim_status,'claim_checks':checks,
            'integrity_status':'failed' if integrity_failed else 'passed','semantic_status':semantic_status,'narrative_status':narrative_status,
            'reviewer':'evidence-claims-review-1.0.0','numeric_rerun':False,
            'note':'Checks source membership, contract field shape/unit and declared numeric predicates. Free narrative and physical modelling remain outside this deterministic review. Fixture claims describe only fixed evidence.',
            'confirmation_policy':'failed blocks approval; unknown requires a nonempty human review reason'}
