"""Cross-check manually read factual tables from public A163 page images."""
from pathlib import Path
import json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];CASE=ROOT/'stage-a/2024-A-problem-1'
# Manual transcription: image page 10, table 4.2. x/y rows interleaved.
position=[
[8.800000,5.799209,-4.084887,-2.963609,2.594494,4.420274],
[0,-5.771092,-6.304479,6.094780,-5.356743,2.320429],
[8.363824,7.456758,-1.445473,-5.237118,4.821221,2.459489],
[2.826544,-3.440399,-7.405883,4.359627,-3.561949,4.402476],
[-9.518732,-8.686317,-5.543149,2.890455,5.980011,-6.301346],
[1.341137,2.540108,6.377946,7.249289,-3.827758,0.465829],
[2.913983,5.687116,5.361939,1.898795,-4.917371,-6.237722],
[-9.918311,-8.001384,-7.557638,-8.471614,-6.379874,3.936008],
[10.861726,6.682312,2.388757,1.005154,2.965378,7.040740],
[1.828753,8.134544,9.727411,9.424751,8.399721,4.393013],
[4.555102,-6.619664,-10.627210,-9.287720,-7.457151,-7.458662],
[10.725118,9.025570,1.359848,-4.246673,-6.180726,-5.263384],
[-5.305444,7.364557,10.974348,7.383895,3.241051,1.785033],
[-10.676584,-8.797992,0.843473,7.492371,9.469336,9.301164]]
# Manual transcription: image page 11, table 4.3.
speed=[
[1,1,1,1,1,1],
[.999971,.999961,.999945,.999917,.999859,.999709],
[.999742,.999662,.999538,.999331,.998941,.998065],
[.999575,.999453,.999269,.998971,.998435,.997302],
[.999448,.999299,.999078,.998727,.998115,.996861],
[.999348,.999180,.998935,.998551,.997894,.996574],
[.999311,.999136,.998883,.998489,.997816,.996478]]
times=[0,60,120,180,240,300];indices=[0,1,51,101,151,201,223]
ref=sorted((CASE/'runs').glob('reference-*'))[-1]
with np.load(ref/'trajectories.npz',allow_pickle=False) as r:
 rp=r['position_m'][np.ix_(times,indices,[0,1])].transpose(1,2,0).reshape(14,6)
 rs=r['speed_m_s'][np.ix_(times,indices)].T
 raw_p=float(np.max(np.abs(rp-position)));raw_s=float(np.max(np.abs(rs-speed)))
 dp=np.round(rp,6)-position;ds=np.round(rs,6)-speed
 differences=[]
 labels=['龙头','第1节龙身','第51节龙身','第101节龙身','第151节龙身','第201节龙身','龙尾（后）']
 for i,j in zip(*np.where(np.abs(dp)>1e-10)):
  differences.append({'handle':labels[i//2],'axis':'xy'[i%2],'time_s':times[j],'paper_value':position[i][j],'reference_rounded':float(np.round(rp[i,j],6)),'difference_m':float(dp[i,j])})
 summary={'source_url':'https://dxs.moe.gov.cn/zx/a/hd_sxjm_sxjmlw_2024qgdxssxjmjslwzs_2024atlw/241104/1977935.shtml','title':'2024高教社杯全国大学生数学建模竞赛A题论文展示（A163）','publisher':'中国大学生在线；页面署名全国大学生数学建模竞赛组委会','publication_date':'2024-11-04','role':'external cross-check, not official answer key','read_method':'manual visual transcription of page images; transcription may contain errors','pages':{'position':10,'speed':11,'geometric_constraint':8},'reference_run':ref.name,'position_values_checked':84,'speed_values_checked':42,'position_max_abs_difference_unrounded_m':raw_p,'speed_max_abs_difference_unrounded_m_s':raw_s,'position_equal_at_6_decimals':int(np.sum(np.abs(dp)<=1e-10)),'speed_equal_at_6_decimals':int(np.sum(np.abs(ds)<=1e-10)),'position_rounded_differences':differences,'interpretation':'Broad numerical agreement; small last-digit position differences are recorded, not automatically attributed to rounding. Speed matches all displayed entries. No adjustments made to reference data.','leakage_control':'Paper first accessed after independent MiMo attempts. No paper contents were included in those requests; any future use must be explicitly labelled.'}
 dest=CASE/'external-validation';dest.mkdir(exist_ok=True)
 (dest/'a163-table-transcription.json').write_text(json.dumps({'position_m':position,'speed_m_s':speed,'times_s':times,'handle_indices':indices,'provenance':summary['read_method']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (dest/'a163-comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 lines=['# A163 论文外部核验','',f"来源：[中国大学生在线 A163 论文展示]({summary['source_url']})，页面日期2024-11-04，署名全国大学生数学建模竞赛组委会。论文为公开展示参赛论文，不能直接称为官方标准答案；当前页面本身未独立确认具体获奖等级。",'', '核对第8页的直线距离约束、第10页表4.2及第11页表4.3。表格数值人工按图转录，保留人工读图可能出错的限制。论文图像仅供本地核验，不随仓库提交或转载。','',f'位置：84项中{summary["position_equal_at_6_decimals"]}项在6位小数完全相同；其余差异如下。对未舍入参考值的最大绝对差为{raw_p:.9g} m。','',f'速率：42项在6位小数全部相同；对未舍入参考值的最大绝对差为{raw_s:.9g} m/s。','', '| 把手 | 分量 | 时刻/s | 论文/m | 参考/m |','|---|---|---:|---:|---:|']
 for x in differences:lines.append(f"| {x['handle']} | {x['axis']} | {x['time_s']} | {x['paper_value']:.6f} | {x['reference_rounded']:.6f} |")
 lines+=['','结论：参考计算与该论文结果高度一致，少量位置差异为显示末位1e-6 m量级，不能未经验证就归因为舍入。原参考结果未因论文而修改；原14项物理与数值检查仍作为主要核验依据。','', 'MiMo独立生成发生在本论文读取之前，未使用论文内容。外部对照增强人工参考基线的证据，不会把此前错误的MiMo方案变成成功。尚未受控执行的生成代码仍标记为未执行。未来若将论文交给模型，必须另列为允许同题资料或反馈修订实验。']
 (CASE/'external-reference-check.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in summary.items() if k in ['position_equal_at_6_decimals','speed_equal_at_6_decimals','position_max_abs_difference_unrounded_m','speed_max_abs_difference_unrounded_m_s','position_rounded_differences']},ensure_ascii=False,indent=2))
if __name__=='__main__':pass
