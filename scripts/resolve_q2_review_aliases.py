"""Resolve only a recorded compact-view alias, preserving reviewer judgments verbatim."""
import copy,json
from modelcrew.config import ROOT
from modelcrew.collaboration import CollaborationStore,Snapshot,Receipt,sha_file
from modelcrew.modeling_hand import M1Answer,pointer
from scripts.run_q2_full import active
from scripts.run_d3_minimal import read,write

def resolve_aliases(answer,evidence,projection):
    result=copy.deepcopy(answer);changes=[]
    fields={'time_interval_s','source_primary_sha256','code_sha256','max_speed_enclosure_error_m_s'}
    for check in result['checks']:
        for proof in check['evidence']:
            artifact=proof['artifact_id'];old=proof['selector']
            try:pointer(evidence[artifact],old);continue
            except Exception:pass
            # This alias was introduced by the trusted citation-correction request view.
            if artifact!='speed_precision' or not old.startswith('/certificate_summary/'):raise ValueError('Unmapped reviewer citation; fail closed')
            field=old.removeprefix('/certificate_summary/')
            if field not in fields:raise ValueError('Not a projected certificate field')
            new='/certificate/'+field
            shown=pointer(projection[artifact],old);actual=pointer(evidence[artifact],new)
            if json.dumps(shown,sort_keys=True)!=json.dumps(actual,sort_keys=True):raise ValueError('View alias does not equal frozen evidence')
            proof['selector']=new;changes.append({'check_id':check['check_id'],'artifact_id':artifact,'provider_view_selector':old,'frozen_selector':new,'view_and_frozen_value':actual,'equal_verified':True})
    # Only selector strings may change; all status/explanation/issues/evidence sets remain.
    reconstructed=copy.deepcopy(result)
    for check,original in zip(reconstructed['checks'],answer['checks']):
        for proof,old in zip(check['evidence'],original['evidence']):proof['selector']=old['selector']
    if reconstructed!=answer:raise ValueError('Review judgments changed')
    return result,changes

def main():
    f=active();sub=f/'review-final/provider';fix=sub/'citation-correction'
    d=read(sub/'P2-dispatch.json');store=CollaborationStore(f/'records');snap=store.load(Snapshot,d['snapshot_sha256']);store.validate_snapshot(snap)
    evidence={a.artifact_id:read(ROOT/a.path) for a in snap.artifacts};raw=read(fix/'P2-provider-answer.json')
    request=next(fix.glob('P2-citation-correction-*-request.json'));payload=json.loads(read(request)['messages'][1]['content']);projection=payload['actual_evidence_for_three_repairs']
    normalized,maps=resolve_aliases(raw,evidence,projection);parsed=M1Answer.model_validate(normalized)
    for c in parsed.checks:
        for proof in c.evidence:pointer(evidence[proof.artifact_id],proof.selector)
    write(fix/'view-alias-resolution.json',{'policy':'only the previously recorded trusted view alias certificate_summary -> frozen certificate; compare actual leaf values; no judgment changes','raw_answer_path':(fix/'P2-provider-answer.json').relative_to(ROOT).as_posix(),'raw_answer_sha256':sha_file(fix/'P2-provider-answer.json'),'original_projection_request_path':request.relative_to(ROOT).as_posix(),'original_projection_request_sha256':sha_file(request),'snapshot_sha256':d['snapshot_sha256'],'mappings':maps,'statuses_explanations_issues_unchanged':True})
    write(fix/'resolved-provider-answer.json',normalized)
    status='FAIL' if any(c.status=='FAIL' for c in parsed.checks) else 'BLOCKED' if any(c.status=='BLOCKED' for c in parsed.checks) else 'PASS'
    response=Receipt(ticket_sha256=d['ticket_sha256'],reviewer_call_id=d['reviewer_call_id'],status=status,checks=parsed.checks,issues=parsed.issues)
    write(fix/'resolved-P2-response.json',response.model_dump(mode='json'))
    print('CANDIDATE_RECEIPT '+status+'; '+str(len(maps))+' proven view aliases; not yet admitted',flush=True)
if __name__=='__main__':main()
