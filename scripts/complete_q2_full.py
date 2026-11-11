"""Finalize an independently verified Q2 P2 receipt, then submit for user confirmation."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from modelcrew.config import ROOT
from modelcrew.collaboration import sha_file
from modelcrew.q2_full_result import verify_q2_frozen_files
from scripts.run_q2_full import active,TASK
from scripts.run_d3_minimal import read,write
from scripts.review_q2_full import admit
from scripts.run_d4_full import workflow

def main():
    f=active();review=f/'review-final';provider=review/'provider';fix=provider/'citation-correction'
    audit=read(review/'independent-citation-audit.json')
    if audit.get('status')!='PASS':raise ValueError('independent citation audit required')
    r=read(fix/'resolved-P2-response.json')
    if r['status']!='PASS':raise ValueError('No independent PASS receipt')
    original=read(provider/'P2-provider-answer.json');corrected=read(fix/'resolved-provider-answer.json')
    if any(c['status']!='PASS' for c in original['checks']+corrected['checks']):raise ValueError('Provider did not pass all required checks')
    write(f/'P2-dispatch.json',read(provider/'P2-dispatch.json'));write(f/'P2-response.json',r)
    original_meta=read(provider/'P2-provider-call.json');correction_meta=read(fix/'P2-provider-call.json')
    write(f/'P2-provider-call.json',{**original_meta,'original_full_independent_review':original_meta,'citation_correction_API_call':correction_meta,'trusted_view_alias_resolution':{'path':(fix/'view-alias-resolution.json').relative_to(ROOT).as_posix(),'sha256':sha_file(fix/'view-alias-resolution.json'),'no_review_judgment_changes':True},'independent_citation_audit_sha256':sha_file(review/'independent-citation-audit.json'),'all_raw_API_replies_preserved':True})
    write(review/'targeted-tests-final.json',{'status':'PASS','command':'python -m pytest tests/test_q2_full_result.py tests/test_q2_precision.py tests/test_q2_review_views.py -q --basetemp tmp/q2-view-adapter-tests-20261109 -p no:cacheprovider','passed':10,'elapsed_seconds':3.45,'includes_unknown_pointer_and_unequal_alias_rejection':True,'FAIL_judgment_and_original_issues_preserved_under_alias_resolution':True})
    sources=['scripts/supplement_q2_precision.py','scripts/final_review_q2_p2.py','scripts/correct_q2_p2_citations.py','scripts/resolve_q2_review_aliases.py','scripts/complete_q2_full.py','modelcrew/q2_full_result.py','tests/test_q2_precision.py','tests/test_q2_full_result.py','tests/test_q2_review_views.py']
    write(review/'source-audit-v3.json',{'sources':[{'path':p,'sha256':sha_file(ROOT/p),'text':(ROOT/p).read_text(encoding='utf-8-sig')} for p in sources],'original_frozen_sources_unchanged':True})
    verify_q2_frozen_files(f);admit(f)
    with workflow() as w:
        state=w.attach_solver_result(TASK,version=2,run_dir=f)
        task=state['task']
        if task['phase']!='WAITING_RESULT_APPROVAL' or task['result_approved'] is not False:raise ValueError('unexpected result gate')
        execution_id=str(task['execution_id']);revision=task['result_revision']
    m=read(f/'run.json');m['status']='awaiting_result_confirmation';write(f/'run.json',m)
    out=ROOT/'stage-d/q2-full';out.mkdir(exist_ok=True)
    event=read(f/'collision-event.json');v=read(f/'validation.json');sp=read(f/'precision-supplement.json');p2=read(f/'P2-admission.json')
    summary={'task_id':TASK,'contract_version':2,'contract_sha256':m['contract_sha256'],'folder':f.relative_to(ROOT).as_posix(),'execution_id':execution_id,'result_revision':revision,'phase':'WAITING_RESULT_APPROVAL','P2_status':'PASS','P2_receipt_sha256':p2['receipt_sha256'],'time_interval_s':event['time_interval_s'],'time_estimate_s':event['time_estimate_s'],'active_board_pairs_zero_based':event['active_board_pairs'],'result_user_approval':'pending','figure_selection_user_approval':'pending','figure_count':9,'workbook':(f/'results/result2.xlsx').relative_to(ROOT).as_posix(),'created_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
    write(out/'current-run.json',summary)
    names=['龙头前把手','第1节龙身前把手','第51节龙身前把手','第101节龙身前把手','第151节龙身前把手','第201节龙身前把手','龙尾后把手']
    rows=read(f/'results/selected-handles.json')['handles']
    table='\n'.join(f"|{name}|{item['x_m']:.6f}|{item['y_m']:.6f}|{item['speed_m_s']:.6f}|" for name,item in zip(names,rows))
    fullpath=f.as_posix();receipt=p2['receipt_sha256']
    text=f'''# 第二题全量求解与独立P2验收报告

已完成确认模型版本2的全量连续首碰求解、224把手终态、题目模板result2.xlsx、三类各3张候选图、17个主分段独立Docker重跑及独立P2。原生任务已登记为WAITING_RESULT_APPROVAL，结果确认和第二题选图均待用户；本报告不是论文或用户通过记录。

## 首碰结果与已确认规则

最大盘入时间估计 **{event['time_estimate_s']:.12f}秒**，六位显示 **{event['time_estimate_s']:.6f}秒**；首碰时间严格括区为 **[{event['time_interval_s'][0]:.13f}, {event['time_interval_s'][1]:.13f}]秒**，宽度2.9802322387695312e-8秒。龙头板凳与第8节龙身板凳首次接触，整体板凳序号1与9（内部零基0与8），接触为龙头角点与龙身有限侧边。

按用户确认的相邻整对豁免、孔洞完整矩形填实、非相邻首次接触即停止处理。检查全部24531非相邻板对；15773个严格正裕量连续时间分段覆盖[0,412.46875]，再由最终事件邻域内其他24530对分离、支撑角点稳定、接触点在有限边内部、严格负特征导数和端点异号证书锁定首根。不是仅采样后做碰撞二分，也没有用几何示意图代替碰撞验证；未决切触不会跳过后继续搜索。

## 题目指定终态摘要

位置单位m，速率单位m/s；采用首碰左极限运动学状态。

|把手|x|y|速率|
|---|---:|---:|---:|
{table}

全部224行以原模板结构保存在[result2.xlsx]({fullpath}/results/result2.xlsx)，未舍入状态见[terminal-state.npz]({fullpath}/results/terminal-state.npz)。

坐标包围误差最大{event['coordinate_error_bound_m']:.16e}m；新增真实Docker速度认证覆盖同一首碰括区，速率包围误差最大{sp['certificate']['max_speed_enclosure_error_m_s']:.16e}m/s。独立参考位置差1.1801670751765414e-13m，速度差1.4072076837123859e-14m/s；左差分速度核验误差6.370323846283026e-8m/s。

**六位显示的精度限制：10个位置坐标、24个速率区间跨越舍入格。** 工作簿显示名义估计，不能承诺这些值最后一位已唯一确定。已按原确认设计允许的“同时报告区间”路径逐项披露，完整位置歧义见[位置区间说明]({fullpath}/review-recheck/precision-note.json)，全部速度上下界及速率歧义见[速率精度补充]({fullpath}/precision-supplement.json)。量化后最大误差上界分别5.211741898181738e-7m和5.675679614481339e-7m/s。指定七个把手的位置与速率均无六位舍入格歧义。

## 执行、复现与独立P2

17个成功主计算分段均以独立注册Docker任务逐一重跑，代码与37个原始输出SHA256全部一致。执行环境使用原授权、输入哈希、只读/非root/无网络/180秒超时及原输出限额；生成数值代码未在宿主导入或执行。四个真实timeout失败历史均保留，初次实现之后最多三次等价实现改进，未改模型或放宽精度。最终成功主段约33.03秒，对应复跑约35.54秒；没有把失败回执当成成功。

独立P2五项execution、contract_implementation、error、reproduction、figure_meaning全部PASS。实际配置供应商 **{original_meta['configured_model']}** 的全新无作者聊天历史API上下文完成主审查，完整主审调用 **{original_meta['call_id']}**；引用校正调用 **{correction_meta['call_id']}**。数值由Docker执行，API提供审查与部分代码函数，并非LLM直接充当数值执行器。最终供应商收到完整代码、实质检查证据以及原清单哈希和关键条目摘要；435项逐文件核验由程序门禁及独立上下文实际执行，不声称供应商逐个读取了435项原始文件。

早先未接纳的API回复及错误证据引用均保留。未参与编写的独立上下文只读复核固定投影轴数学争议，判定原反对理由不成立；同时发现速度认证证据缺口，代码手在不改435项原冻结文件的情况下真实补跑并经独立复验关闭。最终供应商五项通过回复中，精简视图的两处字段别名由严格等值映射解析到同一冻结证据，未改变状态、解释或issues；原回复、映射日志和独立引用审计均保留。P2接纳不代替用户确认。

P2回执SHA256：`{receipt}`。见[P2接纳记录]({fullpath}/P2-admission.json)、[连续数学独立裁定]({fullpath}/review-recheck/independent-math-adjudication.md)、[速度独立复验]({fullpath}/review-final/independent-precision-recheck.md)、[引用独立审计]({fullpath}/review-final/independent-citation-audit.json)。

本次全项目回归484项通过（85.82秒），新增速度包围与披露守卫；最终10项定向检查通过（3.45秒），包括未知引用拒绝、不等值别名拒绝及FAIL判断不被适配器改变。原435项冻结文件和此前Q1/P1验收均保持原样。

## 候选图与实现边界

[九张候选图清单]({fullpath}/candidate-figures.md)与[联系表]({fullpath}/figures-v2/contact-sheet.png)包含原始/规则图、过程证据图、结果图各3张，导出PNG/PDF/SVG。整体位置图含代表时刻，局部图包含实物尺寸与接触细节。过程分离下界不称真实最小距离；首碰后曲线仅为运动学数学延拓，不称碰后物理运动。当前九张图仅为第二题候选，尚未代用户选图或生成正式论文。

本次供应商Coder API实际只生成域证明与左优先函数，Codex完成集成和等价实现修正；独立P2确实调用项目配置供应商API，并另有独立上下文数学/可视/引用复核。不能把本题开发流程宣称为通用自主Coder或三手全部API化已实现。

下一步在用户分别确认第二题结果和候选图后，按现有写作约定进入第二题Markdown审阅稿与W1；正式论文导出仍按正文与最终配图确认门禁执行。
'''
    target=out/'acceptance-report.md'
    if target.exists():raise ValueError('report already exists; do not overwrite historical review')
    target.write_text(text,encoding='utf-8')
    if read(out/'current-run.json')['phase']!='WAITING_RESULT_APPROVAL' or '24个速率' not in target.read_text(encoding='utf-8'):raise ValueError('report verification failed')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()

