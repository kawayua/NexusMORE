"""One bounded reviewer citation correction; preserve original review and snapshot."""
from modelcrew.config import ROOT
from modelcrew.collaboration import CollaborationStore,Snapshot,Receipt
from modelcrew.modeling_hand import M1Answer,pointer
from modelcrew.model_client import JsonModel
from scripts.recheck_q2_p2 import JsonClient
from scripts.run_q2_full import active
from scripts.run_d3_minimal import read,write
import shutil

def main():
    f=active();sub=f/'review-final/provider';fix=sub/'citation-correction';fix.mkdir(exist_ok=False)
    d=read(sub/'P2-dispatch.json');store=CollaborationStore(f/'records');snap=store.load(Snapshot,d['snapshot_sha256']);store.validate_snapshot(snap)
    evidence={a.artifact_id:read(ROOT/a.path) for a in snap.artifacts};original=read(sub/'P2-provider-answer.json')
    problems=[]
    for c in original['checks']:
        for e in c['evidence']:
            try:pointer(evidence[e['artifact_id']],e['selector'])
            except Exception:problems.append({'check_id':c['check_id'],**e})
    available={}
    for key,val in evidence.items():
        if isinstance(val,dict):available[key]=list(val)
    shown={'code':evidence['code'],'speed_precision':{'rounding_disclosure':evidence['speed_precision']['rounding_disclosure'],'certificate_summary':{k:evidence['speed_precision']['certificate'][k] for k in ['time_interval_s','source_primary_sha256','code_sha256','max_speed_enclosure_error_m_s']}},'retained_failed_job_names':list(evidence['execution']['retained_failed_jobs'])}
    write(fix/'validation-errors.json',{'invalid_pointers':problems,'failed_job_count':len(evidence['execution']['retained_failed_jobs']),'same_snapshot_sha256':d['snapshot_sha256'],'original_review_unchanged':True})
    system='''你是同一逻辑独立P2审查的引用校正步骤，不是作者。原P2语义审查已输出但三处JSON Pointer不解析，故尚未接纳。严格返回给定schema的完整checks/issues JSON，无额外键，check无issue字段，解释<=300字。只修正实际错误引用并核对其证据；不为得到PASS而改变判断，若源内容不支持可降为FAIL/BLOCKED。code源文件完整字符串实际在/executed_final_source，函数并非独立JSON键；速率舍入披露实际在speed_precision的/rounding_disclosure/ambiguous_speed_coordinates，非certificate下。请实际检查所给源文/披露后自行选择合法路径。其余已合法指针保持，五项检查全部保留，不删实质证据。execution保留失败作业实际有四个，代码等价改进为最多三次重试，请修正“三次timeout失败历史”的计数表述。你原审查和更正均绑定同一冻结snapshot，前一原始回复不得修改。'''
    answer,meta=JsonModel(client=JsonClient()).call(fix,'P2-citation-correction',system,{'schema':M1Answer.model_json_schema(),'previous_independent_review':original,'validation_errors':problems,'available_actual_top_level_paths':available,'actual_evidence_for_three_repairs':shown,'ticket_sha256':d['ticket_sha256'],'snapshot_sha256':d['snapshot_sha256']},max_tokens=4000)
    write(fix/'P2-provider-answer.json',answer);write(fix/'P2-provider-call.json',meta);parsed=M1Answer.model_validate(answer)
    for c in parsed.checks:
        for proof in c.evidence:pointer(evidence[proof.artifact_id],proof.selector)
    status='FAIL' if any(c.status=='FAIL' for c in parsed.checks) else 'BLOCKED' if any(c.status=='BLOCKED' for c in parsed.checks) else 'PASS'
    response=Receipt(ticket_sha256=d['ticket_sha256'],reviewer_call_id=d['reviewer_call_id'],status=status,checks=parsed.checks,issues=parsed.issues)
    store.accept_review(response,d['snapshot_sha256']);write(fix/'P2-response.json',response.model_dump(mode='json'))
    metadata={**meta,'logical_reviewer_call_id':d['reviewer_call_id'],'original_full_independent_review':read(sub/'P2-provider-call.json'),'citation_correction_only':True,'same_frozen_snapshot_sha256':d['snapshot_sha256'],'raw_original_and_correction_retained':True}
    shutil.copyfile(f/'P2-dispatch.json',fix/'previous-root-dispatch.json')
    write(f/'P2-dispatch.json',d);write(f/'P2-response.json',response.model_dump(mode='json'));write(f/'P2-provider-call.json',metadata)
    print('P2_VALIDATED '+status,flush=True)
if __name__=='__main__':main()
