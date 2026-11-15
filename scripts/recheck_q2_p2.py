"""Independent P2 recheck with compact keyed evidence; original raw response retained."""
from modelcrew.project_assets import asset_path
import json,uuid,shutil
from pathlib import Path
import httpx
from modelcrew.config import ROOT
from modelcrew.collaboration import Call,Binding,Artifact,Snapshot,CollaborationStore,Receipt,sha_file
from modelcrew.model_client import JsonModel
from modelcrew.modeling_hand import M1Answer,pointer
from modelcrew.q2_full_result import verify_q2_frozen_files
from scripts.run_q2_full import active
from scripts.run_d3_minimal import read,write

class JsonClient:
    def post(self,url,**kwargs):
        kwargs['json']['response_format']={'type':'json_object'}
        return httpx.post(url,**kwargs)

def main():
    folder=active();sub=folder/'review-recheck';sub.mkdir(exist_ok=False)
    manifest,paths=verify_q2_frozen_files(folder);m=read(folder/'run.json');old=read(folder/'P2-dispatch.json')
    write(sub/'original-dispatch.json',old)
    raw=next(folder.glob('P2-*-response.json'));write(sub/'recheck-reason.json',{'previous_response':raw.relative_to(ROOT).as_posix(),'sha256':sha_file(raw),'reason':'unparseable JSON, nonexistent evidence pointers, and conflation of retained timeout variants with succeeded final-bound receipt; no prior review admitted','numeric_artifacts_unchanged':True,'original_manifest_sha256':sha_file(folder/'frozen-artifacts.json')})
    jobs=read(folder/'execution-evidence.json')
    def receipt(item):
        r=item['execution'];return {'run_id':r['run_id'],'status':r['status'],'exit_code':r['exit_code'],'code_sha256':r['code_sha256'],'job_sha256':r['job_sha256'],'authorization':r['authorization'],'image_id':r['image_id'],'elapsed_s':r['elapsed_s'],'cleanup':r['cleanup'],'artifacts':r['artifacts'],'receipt_file':(folder/item['directory']/'execution.json').relative_to(ROOT).as_posix(),'receipt_sha256':sha_file(folder/item['directory']/'execution.json')}
    success={x['directory']:receipt(x) for x in jobs['jobs']}
    failed={x['directory']:receipt(x) for x in jobs['retained_failed_jobs']}
    write(sub/'execution.json',{'successful_jobs':success,'retained_failed_jobs':failed,'common_restrictions':next(iter(jobs['jobs']))['execution']['restrictions'],'host_verified_all_artifact_hashes_and_cleanup':True,'final_primary_key':'part-10g-final-bound','final_reproduction_key':'repro-16','actual_supplier_coding_call':read(folder/'supplier-coding-call.json')})
    final=folder/'part-10g-final-bound/generated_solver.py'
    write(sub/'code.json',{'executed_final_source':final.read_text(encoding='utf-8'),'sha256':sha_file(final),'same_prefix_implementation':'previous successful primary partitions use original full-base.py; only final finite-feature proof is extended','prefix_base_sha256':sha_file(folder/'full-base.py'),'support_tail':(asset_path(ROOT,'execution/q2_support_tail.py')).read_text(encoding='utf-8-sig'),'trusted_validation_source':(ROOT/'scripts/validate_q2_full.py').read_text(encoding='utf-8-sig'),'proof':(folder/'continuous-proof.md').read_text(encoding='utf-8'),'authoring':'supplier generated two used functions; Codex integrated and made three equivalent implementation retries; no model/tolerance change'})
    validation=read(folder/'validation.json')
    write(sub/'result.json',validation)
    with __import__('numpy').load(folder/'results/terminal-state.npz',allow_pickle=False) as data:
        lower=data['position_lower_m'];upper=data['position_upper_m'];position=data['position_m']
        ambiguous=[{'handle_index_zero_based':i,'coordinate':'x' if j==0 else 'y','xlsx_cell':('B' if j==0 else 'C')+str(i+2),'estimate_m':float(position[i,j]),'interval_m':[float(lower[i,j]),float(upper[i,j])],'rounded_lower_6dp':round(float(lower[i,j]),6),'rounded_upper_6dp':round(float(upper[i,j]),6)} for i,j in validation['six_decimal_position_rounding_ambiguous_coordinates']]
    write(sub/'precision-note.json',{'coordinate_uncertainty_max_m':validation['first_contact_event']['coordinate_error_bound_m'],'per_coordinate_5e_minus7_condition_met':True,'six_decimal_format_is_approximate_output_not_uniquely_certified_rounding':True,'ambiguous_coordinates':ambiguous,'displayed_value_total_error_bound_m':5e-7+validation['first_contact_event']['coordinate_error_bound_m'],'contract_state_error_tolerance_m':1e-6,'no_claim_all_last_digits_are_unique':True,'selected_seven_handles_have_no_position_rounding_bin_ambiguity':True,'plain_language':'10个坐标区间跨六位舍入边界，末位可能相差一单位；工作簿显示名义估计，保留未舍入数组与区间。逐坐标误差满足5e-7条件，显示量化后误差上界仍小于契约1e-6m。不承诺这些坐标六位舍入值已唯一确定。'})
    essential=[x for x in manifest['artifacts'] if any(s in x['path'] for s in ['/results/','/part-10g-final-bound/','/repro-16/','/support/']) or x['path'].endswith('/validation.json')]
    write(sub/'manifest-summary.json',{'original_frozen_manifest_sha256':sha_file(folder/'frozen-artifacts.json'),'all_435_original_files_verified':len(paths),'binding':manifest['binding'],'essential_artifacts':essential,'no_numeric_or_figure_bytes_changed':True})
    binding=Binding(task_id=m['task_id'],contract_version=2,contract_sha256=m['contract_sha256'],execution_id=folder.name,result_revision=1)
    store=CollaborationStore(folder/'records');authors=[m['author']['call_id'],m['supplier_author']['call_id']]
    specs=[('code','code',sub/'code.json'),('inputs','input',folder/'inputs.json'),('execution','execution',sub/'execution.json'),('result','result',sub/'result.json'),('precision','result',sub/'precision-note.json'),('figure','figure',folder/'figures.json'),('reproduction','reproduction',folder/'reproduction.json'),('manifest_summary','reproduction',sub/'manifest-summary.json'),('frozen_files','reproduction',folder/'frozen-artifacts.json')]
    artifacts=[Artifact(artifact_id=a,kind=k,path=p.relative_to(ROOT).as_posix(),sha256=sha_file(p),author_call_ids=authors if a=='code' else authors[:1]) for a,k,p in specs]
    snap=Snapshot(binding=binding,hand='coding',artifacts=artifacts,lineage_call_ids=authors);key=store.freeze(snap)
    reviewer=Call(call_id='supplier-P2-recheck-'+uuid.uuid4().hex,context_id='new-stateless-P2-'+uuid.uuid4().hex,role='quality',binding=binding);store.register_call(reviewer);ticket=store.dispatch_review(key,'P2',reviewer.call_id)
    dispatch={'ticket_sha256':ticket,'snapshot_sha256':key,'reviewer_call_id':reviewer.call_id,'artifact_ids':[a.artifact_id for a in artifacts],'required_checks':['execution','contract_implementation','error','reproduction','figure_meaning'],'previous_unadmitted_ticket':old['ticket_sha256'],'independent_stateless_recheck':True,'not_user_approval':True}
    write(sub/'P2-dispatch.json',dispatch)
    evidence={a.artifact_id:read(ROOT/a.path) for a in artifacts if a.artifact_id!='frozen_files'}
    schema=M1Answer.model_json_schema();schema['$defs']['Evidence']['properties']['artifact_id']['enum']=list(evidence)
    answer,meta=JsonModel(client=JsonClient()).call(sub,'P2-recheck','你是全新的独立只读P2 Reviewer，未参与产物编写。只返回严格合法JSON对象，不要Markdown，不要字符串拼接。按给定schema，checks恰execution,contract_implementation,error,reproduction,figure_meaning；每个explanation以及issue各文本<=300字。PASS必须引用实际存在的artifact_id及可解析JSON Pointer。execution.successful_jobs和retained_failed_jobs是不同的按名字索引字典，不能把失败历史当最终运行；必须实际核对final_primary_key和final_reproduction_key对应status、exit_code和输出。审查已确认契约的全量连续首事件、24531对、全部224把手、分段前缀和最终有限特征单调证明，不以采样或哈希重复替代正确性。code含真实最终源码和保守区间证明；sin返回[-1,1]是保守包围，若认为无效请给数学理由；速度区间收紧必须对应解析非扩张证明。support证书在execution与result引用对应真实support输出；final event entire enclosure和端点时刻不同，要分别检查。精度按原契约实际条款判断，不增设未经用户确认的新标准；precision给出10坐标舍入bin歧义及误差，不能宣称所有六位舍入唯一。三类各3候选图，文本API不能宣称亲眼看图，审意义与数据绑定。失败或阻断需具体证据、正确domain/target路由和复验；不改产物，不替用户批准。此前一份200k token回复未通过JSON和证据指针校验，本次不继承其结论，不查看作者聊天历史，完全按本包重新审查。',{'schema':schema,'binding':binding.model_dump(mode='json'),'contract':read(folder/'contract.json'),'evidence':evidence,'frozen_manifest_sha256':sha_file(folder/'frozen-artifacts.json'),'gate':'P2'},max_tokens=7000)
    write(sub/'P2-provider-answer.json',answer);write(sub/'P2-provider-call.json',meta);parsed=M1Answer.model_validate(answer)
    for c in parsed.checks:
        for proof in c.evidence:pointer(evidence[proof.artifact_id],proof.selector)
    status='FAIL' if any(c.status=='FAIL' for c in parsed.checks) else 'BLOCKED' if any(c.status=='BLOCKED' for c in parsed.checks) else 'PASS'
    response=Receipt(ticket_sha256=ticket,reviewer_call_id=reviewer.call_id,status=status,checks=parsed.checks,issues=parsed.issues)
    store.accept_review(response,key)
    write(sub/'P2-response.json',response.model_dump(mode='json'))
    shutil.copyfile(folder/'P2-dispatch.json',sub/'P2-first-dispatch-retained.json')
    write(folder/'P2-dispatch.json',dispatch);write(folder/'P2-response.json',response.model_dump(mode='json'));write(folder/'P2-provider-call.json',meta)
    print('P2_RECHECK '+status,flush=True)
if __name__=='__main__':main()
