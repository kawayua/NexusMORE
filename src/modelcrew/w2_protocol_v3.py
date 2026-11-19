"""W2 v3: derived aggregate status and lossless long-form finding storage.

Only NEW packets opt in. Historical v2 responses are never reinterpreted.
"""
from copy import deepcopy
from typing import Literal
from pydantic import Field
from . import w2_protocol as v2
from .contracts import digest
from .workflow import WorkflowError

VERSION='3.0.0'

class Check(v2.Strict):
    check_id: Literal['claims','figures','citations','layout','snapshot_consistency']
    status: v2.Status
    evidence_refs: list[str]=Field(max_length=3)
    explanation: str=Field(min_length=1)

class Issue(v2.Strict):
    check_id: Literal['claims','figures','citations','layout','snapshot_consistency']
    severity: Literal['error','warning','blocking']
    issue_kind: Literal['model','implementation','writing','infrastructure','explanation_coding','explanation_writing']
    reason: str=Field(min_length=1)
    recheck: str=Field(min_length=1)

class Page(v2.Strict):
    page_ref: str
    status: v2.Status
    finding: str=Field(min_length=1)

class Answer(v2.Strict):
    protocol_version: Literal['3.0.0']
    checks: list[Check]=Field(min_length=5,max_length=5)
    issues: list[Issue]=Field(max_length=30)
    pages_reviewed: list[Page]=Field(min_length=2,max_length=100)


def registry(packet):
    refs=v2.registry(packet)
    refs['protocol_version']=VERSION
    return refs


def prepare(packet):
    # Reuse v2 presentation, not its immutable frozen protocol or output contract.
    _,view,_=v2.prepare(packet)
    refs=registry(packet);schema=Answer.model_json_schema()
    schema['properties']['pages_reviewed'].update(minItems=len(refs['pages']),maxItems=len(refs['pages']))
    schema['$defs']['Check']['properties']['evidence_refs']['items']['enum']=[r['ref_id'] for r in refs['entries']]
    schema['$defs']['Page']['properties']['page_ref']['enum']=[p['page_ref'] for p in refs['pages']]
    by_id={i['artifact_id']:i for i in packet['images']}
    images=[{**by_id[p['artifact_id']],'label':p['page_ref']+' '+p['label']} for p in refs['pages']]
    view.update(output_protocol='w2_evidence_refs_v3',protocol_version=VERSION,schema=schema,
                reference_registry_sha256=digest(refs))
    view['evidence']=[{'ref_id':r['ref_id'],'kind':r['kind'],'label':r['label'],
        'value':v2.pointer(packet['evidence'][r['artifact_id']],r['selector'])} for r in refs['entries']]
    view['instructions'] += (' Protocol v3 has NO top-level status field: return only per-check and per-page verdicts, issues and exact references. '
        'The host derives the aggregate without changing your check verdicts. All finding text is preserved verbatim in a hashed detail report; no truncation. '
        'Runtime reproduction evidence describes completed external execution; generator PENDING_RUNTIME fields describe what the program could know before external rerun. '
        'Do not confuse byte reproduction with independent scientific validation. User acceptance of an error does NOT change its original threshold FAIL to PASS. '
        'A disclosed originally failing check plus a scoped user acceptance is not a contradiction by itself. '
        'Manuscript statements must still match external facts; flag genuinely stale statements and any actual remaining defect. '
        'Original W1 claim statements are provenance and may precede registered assembly edits: inspect the actual approved manuscript, edit trail and runtime proofs together, without treating historical claims as automatic current assertions.')
    view['output_limits']={'evidence_refs_per_check_max':3,'issues_max':30,
        'explanation_target_characters':160,'detail_storage':'Full text retained verbatim; native receipt may link to the hashed detail report. No legacy 300-character limit applies to v3 reviewer prose.'}
    view['status_aggregation']={'FAIL':'Any check FAIL','BLOCKED':'No FAIL and any check BLOCKED','PASS':'Every check PASS, no failing/unreadable page, and no unresolved error/blocking issue',
        'rule':'Do not output a top-level status. Every nonpassing check needs a matching issue; page verdicts must agree with layout.'}
    return refs,view,images


def _native_text(text,selector,detail_key):
    if len(text)<=v2.NATIVE_TEXT_LIMIT:return text
    return 'Full reviewer text preserved verbatim in review-details.json; selector='+selector+'; canonical_sha256='+detail_key


def compile_answer(raw,packet,refs):
    if refs!=registry(packet):raise WorkflowError('W2 v3 registry differs from frozen evidence')
    answer=Answer.model_validate(raw)
    verdict='FAIL' if any(c.status=='FAIL' for c in answer.checks) else 'BLOCKED' if any(c.status=='BLOCKED' for c in answer.checks) else 'PASS'
    # Validate all established reference/page/issue rules with a bounded projection.
    # This is a declared v3 encoding, NOT repair of a historical v2 answer.
    key=digest(raw);projection={'protocol_version':'2.2.0','status':verdict,
        'checks':[],'issues':[],'pages_reviewed':[]}
    for n,c in enumerate(answer.checks):
        projection['checks'].append({**c.model_dump(),'explanation':_native_text(c.explanation,f'/checks/{n}/explanation',key)})
    for n,i in enumerate(answer.issues):
        projection['issues'].append({**i.model_dump(),
            'reason':_native_text(i.reason,f'/issues/{n}/reason',key),
            'recheck':_native_text(i.recheck,f'/issues/{n}/recheck',key)})
    for n,p in enumerate(answer.pages_reviewed):
        projection['pages_reviewed'].append({**p.model_dump(),'finding':_native_text(p.finding,f'/pages_reviewed/{n}/finding',key)})
    native_refs=deepcopy(refs);native_refs['protocol_version']=v2.VERSION
    native,proof=v2.compile_answer(projection,packet,native_refs)
    proof.update(protocol_version=VERSION,raw_sha256=key,registry_sha256=digest(refs),
        compiled_sha256=digest(native),aggregate_status_source='per_check_verdicts',
        detail_report={'canonical_sha256':key,'file':'review-details.json','full_text_preserved':True},
        verdict_preserved=True)
    return native,proof

