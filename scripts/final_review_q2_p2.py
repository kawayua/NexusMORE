"""Final independent configured-provider P2 after separately audited precision supplement."""
import json,uuid,shutil
from modelcrew.config import ROOT
from modelcrew.collaboration import Call,Binding,Artifact,Snapshot,CollaborationStore,Receipt,sha_file
from modelcrew.model_client import JsonModel
from modelcrew.modeling_hand import M1Answer,pointer
from modelcrew.q2_full_result import verify_q2_frozen_files,verify_q2_precision
from scripts.run_q2_full import active
from scripts.run_d3_minimal import read,write
from scripts.recheck_q2_p2 import JsonClient
import numpy as np

def main():
    folder=active();sub=folder/'review-final/provider';sub.mkdir(exist_ok=False)
    manifest,paths=verify_q2_frozen_files(folder);m=read(folder/'run.json')
    closure=read(folder/'review-final/independent-precision-recheck.json')
    with np.load(folder/'results/terminal-state.npz',allow_pickle=False) as z:
        precision_paths=verify_q2_precision(folder,read(folder/'collision-event.json'),z['velocity_m_s'],z['speed_m_s'])
    write(sub/'precision-manifest.json',{'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha_file(p)} for p in precision_paths],'verified_again_before_P2':True,'unchanged_original_frozen_files':len(paths)})
    write(sub/'author-response.json',{'fixed_axis_clarification':read(folder/'review-final/author-clarification.json'),'approved_design_exact_excerpt':read(folder/'review-final/approved-design-excerpt.json'),'previous_supplier_review_retained':{'path':(folder/'review-recheck/P2-provider-answer.json').relative_to(ROOT).as_posix(),'sha256':sha_file(folder/'review-recheck/P2-provider-answer.json'),'not_admitted':True},'independent_original_adjudication':read(folder/'review-recheck/adjudication.json'),'independent_precision_recheck':closure,'purpose':'new evidence and independently adjudicated mathematical dispute; make your own final P2 judgment; no prior API receipt rewritten'})
    bind=Binding(task_id=m['task_id'],contract_version=2,contract_sha256=m['contract_sha256'],execution_id=folder.name,result_revision=1)
    store=CollaborationStore(folder/'records');authors=[m['author']['call_id'],m['supplier_author']['call_id']]
    specs=[('code','code',folder/'review-recheck/code.json'),('inputs','input',folder/'inputs.json'),('execution','execution',folder/'review-recheck/execution.json'),('result','result',folder/'review-recheck/result.json'),('precision','result',folder/'review-recheck/precision-note.json'),('speed_precision','result',folder/'precision-supplement.json'),('precision_manifest','reproduction',sub/'precision-manifest.json'),('author_response','reproduction',sub/'author-response.json'),('figure','figure',folder/'figures.json'),('reproduction','reproduction',folder/'reproduction.json'),('manifest_summary','reproduction',folder/'review-recheck/manifest-summary.json'),('frozen_files','reproduction',folder/'frozen-artifacts.json')]
    artifacts=[Artifact(artifact_id=a,kind=k,path=p.relative_to(ROOT).as_posix(),sha256=sha_file(p),author_call_ids=authors if a=='code' else authors[:1]) for a,k,p in specs]
    snapshot=Snapshot(binding=bind,hand='coding',artifacts=artifacts,lineage_call_ids=authors);key=store.freeze(snapshot)
    reviewer=Call(call_id='supplier-P2-final-'+uuid.uuid4().hex,context_id='new-stateless-final-P2-'+uuid.uuid4().hex,role='quality',binding=bind);store.register_call(reviewer);ticket=store.dispatch_review(key,'P2',reviewer.call_id)
    dispatch={'ticket_sha256':ticket,'snapshot_sha256':key,'reviewer_call_id':reviewer.call_id,'artifact_ids':[a.artifact_id for a in artifacts],'required_checks':['execution','contract_implementation','error','reproduction','figure_meaning'],'provider_request_stateless':True,'independence':'fresh supplier context, read-only frozen evidence and newly executed precision supplement','previous_unadmitted_tickets':[read(folder/'P2-dispatch.json')['ticket_sha256'],read(folder/'review-recheck/P2-dispatch.json')['ticket_sha256']],'not_user_approval':True}
    write(sub/'P2-dispatch.json',dispatch)
    evidence={a.artifact_id:read(ROOT/a.path) for a in artifacts if a.artifact_id!='frozen_files'}
    schema=M1Answer.model_json_schema();schema['$defs']['Evidence']['properties']['artifact_id']['enum']=list(evidence)
    write(sub/'request-options.json',{'response_format':{'type':'json_object'},'no_automatic_retry':True})
    system='''你是全新独立只读P2 Reviewer，未参与待审产物编写。仅返回严格JSON对象，遵守schema；禁止额外键。顶层仅checks、issues（status可省略）；checks恰execution,contract_implementation,error,reproduction,figure_meaning。每个check仅check_id,status,evidence,explanation，没有issue字段，不能添加issue:null。issue只能放顶层issues列表，PASS通常issues=[]。解释和issue文本均<=300字。PASS引用实际artifact_id和可解析JSON Pointer。
审查完整首碰而非采样：24531非相邻整对、完整矩形填孔、整对相邻豁免；15773严格正裕量分段从0连续到412.46875，再由局部有限特征的稳定支撑角点、有限边内部、严格负导数、端点异号及其他24530对排除延伸至首根。代码pair_margins使用全时段c/u/n和完整支撑投影；author_response含固定投影轴争议的数学证明与独立只读裁定。请独立检验，不能因轴固定便认定未考虑旋转，也不能因为作者或其他审查说PASS就接受。隐式N/D非扩张、sin保守包围和解析导数均需核验。execution明确成功最终键与保留失败历史，不得混淆。
此前独立裁定仅阻断E1速度区间缺失；现speed_precision含真实受控容器新执行的224速度及速率上下界、同一括区、源码/契约哈希、全部名义终态包含关系及24速率跨六位格的完整披露。precision_manifest绑定真实新文件。核对其足以关闭E1；不能重复声称尚无速度区间。precision披露10位置坐标跨舍入格。精度按原确认model-design原句：坐标/速率若无法落同六位格，继续加严或同时报告区间，不声称唯一六位。不能增加“所有显示值必须唯一舍入”的新要求，也不能隐瞒歧义。实际模板224全部终态、独立参考/左差分检查与17组Docker全量重跑哈希均核对。
三类各3图需审意义与来源，过程正下界不是实际几何距离，接触后曲线仅数学延拓；独立上下文实际看图记录可引用，文本API不能声称亲眼看图。原435冻结文件未变，新精度文件另行哈希绑定。你的PASS/FAIL/BLOCKED均需证据，不是用户确认；发现阻断请具体指出，不修改产物。implementation问题target=coding，model→modeling，infrastructure→recovery，explanation→coding或writing，writing→writing。不得把实现问题路由recovery。'''
    answer,meta=JsonModel(client=JsonClient()).call(sub,'P2-final',system,{'schema':schema,'gate':'P2','binding':bind.model_dump(mode='json'),'contract':read(folder/'contract.json'),'evidence':evidence},max_tokens=7000)
    write(sub/'P2-provider-answer.json',answer);write(sub/'P2-provider-call.json',meta)
    parsed=M1Answer.model_validate(answer)
    for c in parsed.checks:
        for proof in c.evidence:pointer(evidence[proof.artifact_id],proof.selector)
    status='FAIL' if any(c.status=='FAIL' for c in parsed.checks) else 'BLOCKED' if any(c.status=='BLOCKED' for c in parsed.checks) else 'PASS'
    response=Receipt(ticket_sha256=ticket,reviewer_call_id=reviewer.call_id,status=status,checks=parsed.checks,issues=parsed.issues)
    store.accept_review(response,key);write(sub/'P2-response.json',response.model_dump(mode='json'))
    shutil.copyfile(folder/'P2-dispatch.json',sub/'previous-root-dispatch.json')
    write(folder/'P2-dispatch.json',dispatch);write(folder/'P2-response.json',response.model_dump(mode='json'));write(folder/'P2-provider-call.json',meta)
    print('P2_FINAL '+status,flush=True)
if __name__=='__main__':main()
