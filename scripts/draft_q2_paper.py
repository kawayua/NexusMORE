"""Configured API prose authoring after independent W1; fixed evidence tables and assets."""
import argparse,json
from pathlib import Path
import numpy as np
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from modelcrew.model_client import JsonModel
from scripts.recheck_q2_p2 import JsonClient
from scripts.run_d4_full import workflow
from modelcrew.modeling_paper import validate_draft
FOLDER=ROOT/'stage-d/runs/writing/d6-q2-20261109-v2'

def request():
    with workflow() as w:meta=wh.require_W1(FOLDER,w)
    f=ROOT/meta['source_run'];event=wh.read(f/'collision-event.json');sp=wh.read(f/'precision-supplement.json');pos=wh.read(f/'review-recheck/precision-note.json');catalog=wh.read(FOLDER/'figure-catalog.json')
    if list(FOLDER.glob('Writer-provider-*-request.json')):raise ValueError('Provider already requested; inspect saved response, never blindly resend')
    figures=[{'id':x['id'],'number':x['number'],'title':x['title'],'purpose':x['purpose'],'token':'@@FIGURE_'+x['id']+'@@'} for x in catalog['figures'] if x['formal']]
    data={'outline':wh.read(FOLDER/'outline.json'),'figures':figures,'event':{k:event[k] for k in ['time_interval_s','time_estimate_s','active_board_pairs','first_event_enclosure_s','other_pairs_min_gap_lower_bound_m','feature_derivative_m_s','coordinate_error_bound_m']},'safe_segments':15773,'safe_prefix_s':[0,412.46875],'selected_handles':wh.read(f/'results/selected-handles.json'),'precision':{'position_ambiguous_count':len(pos['ambiguous_coordinates']),'speed_ambiguous_count':len(sp['rounding_disclosure']['ambiguous_speed_coordinates']),'speed_bound_m_s':sp['certificate']['max_speed_enclosure_error_m_s'],'coordinate_bound_m':event['coordinate_error_bound_m'],'seven_selected_have_no_6dp_rounding_ambiguity':True},'numerical_checks':wh.read(f/'validation.json')['checks'],'citations':[{'number':x['number'],'title':x['title'],'url':x.get('url')} for x in wh.read(FOLDER/'citations.json')['references']]}
    prompt=r'''你是项目论文手，写中文数学建模“问题二”Markdown审阅稿，只返回JSON对象{"markdown":"完整Markdown"}，不输出代码或解释。遵照中文建模体裁，约3000–4500汉字，标题与章节齐全：摘要、关键词、问题重述、问题分析、模型假设、符号说明、模型建立、模型求解、结果分析、误差分析与模型检验、模型评价与推广、结论、参考文献。最后撰写摘要但交付放开头，摘要给真实主要数值和检验。仅问题二，写成承接第一题的单题稿，第一题图1（板凳实体与孔位）和第一题图3（初态与盘入方向）只文字引用，不重新插入。不提W1/P2/API/数据库/哈希/审批/容器/项目政策等内部流程，不把科研稿写成工程验收报告。
每一幅本题图在正文有“图n”引用，再各使用一次给定@@FIGURE_id@@标记，七幅都须在适当章节出现，按编号1..7，程序会替换成已通过的原字节图片及题注，不得更改或自绘图。结果分析中恰一次@@TERMINAL_TABLE@@，程序插入真实七把手表。附录精度表由程序附加，不要自行生成完整34行表。
下述公式可用且须解释而非堆叠：b=0.55/(2π)，X(θ)=bθ(cosθ,sinθ)，S(θ)=b/2[θ√(1+θ²)+asinhθ]，头角由S(32π)-S(θ0)=v0t且v0=1；杆长ℓ0=2.86m，其余ℓi=1.65m，弦距||Xi+1-Xi||=ℓi。切向T_i=X'(θ_i)，d_i=Pi+1-Pi，头角速度=-v0/[b√(1+θ0²)]，后继角速度=(d_i·T_i)/(d_i·T_i+1)×前驱角速度，速度vi=T_i θdot_i，速率||vi||。说明正分母与外侧最近根分支，核验域θ头≥24弧度只用于本次数学有效域，不是物理停止条件。
碰撞板凳索引0..222、把手0..223。c_i=(Pi+Pi+1)/2，u_i=d_i/ℓi，n_i=(-u_iy,u_ix)，半板长h0=1.705m、其余1.10m，半板宽w=.15m。闭矩形Ri={ci+αui+βni:|α|≤hi,|β|≤w}，孔不扣除；孔距用于运动学、完整板长用于碰撞，禁止混淆。相邻整对与自身豁免，非相邻i<j,j≥i+2共24531对。对任意单位轴a，投影分离间隙g=|a·(cj-ci)|-[hi|a·ui|+w|a·ni|+hj|a·uj|+w|a·nj|]；单时刻SAT取四局部轴的最大值，大于0分离，等于0首次边界接触可停止。终止t*=inf{t≥0:存在非相邻Ri∩Rj≠空}，含孤立切触，不要求穿透。
连续求解不靠固定步长或仅两端采样。任一固定非零轴对整时间区间的状态投影包围严格分离，就证整段分离；轴固定不意味着板不旋转。左优先自适应细分，最早未决不跳过；所有15773段从0连续证到412.46875。本次最终局部区间[412.46875,412.4765625]中其他24530对分离，活动特征是龙头角点到第8节龙身有限边，支撑角点全段稳定、沿边坐标在有限边内、法向特征导数严格负且区间端点异号，才能认证首根。不要假设全局最小间隙随时间单调；本次横穿成功不代表任意孤立相切也能靠Brent异号检出，无证据的最早切触只能记未决。Brent[2]仅给名义根，严格时间括区靠区间特征。解释区间包围是确定性数值误差而非统计置信区间。
结果t*=412.47383768211466s，六位412.473838s，括区[412.4738376736641,412.4738377034664]s，龙头与第8节龙身（整体板序1与9，内部0与8）首次接触。速率是首碰左极限，不模拟碰撞后动力学。图4接触后负间隙曲线是运动学数学延拓非真实穿透运动；图3是认证投影间隙下界不是实际最小欧氏距离；图5整体三代表时刻图用于解释，不代连续证明。
全部224终态与result2.xlsx来自同一首碰状态。主文必须说明10个位置坐标、24个速率区间跨六位小数舍入格，末位可能相差一个单位，不宣称六位唯一；附录报告所有跨格区间，全部未舍入上下界另存精度附件。选定七把手无位置或速率跨格歧义。位置最大包围误差2.1174189818173872e-8m，速率6.756796144813393e-8m/s；加六位量化上界分别5.211741898181738e-7m和5.675679614481339e-7m/s。独立参考位置差1.1801670751765414e-13m、速度差1.4072076837123859e-14m/s，杆长残差8.615330671091215e-14m，左侧差分h=.001s速度差6.370323846283026e-8m/s，17个分段重算输出一致。不能把一致性或数值残差当真实构件误差界，不捏造不同容差收敛实验/基准比较/统计显著性。
假设说明：二维刚体、理想铰接、孔填实完整矩形、相邻整对豁免、非相邻一接触即停。填孔使单对几何更保守，但整对豁免、无厚度/把手凸出/动力学使整体与真实碰撞时间未必有单边界；不宣称现实必安全到此。评价适用性与模型简化局限，不空泛“高精度可靠”。仅引用[1]题面和[2]SciPy brentq已读官方文档，不编引未读SAT或区间分析专著。符号表定义全部主要符号与单位。结论直接回答终止时间、接触对和终态交付。'''
    answer,meta=JsonModel(client=JsonClient()).call(FOLDER,'Writer-provider',prompt,data,max_tokens=13000)
    wh.new(FOLDER/'Writer-provider-answer.json',answer);wh.new(FOLDER/'Writer-provider-call.json',meta)
    if not isinstance(answer.get('markdown'),str):raise ValueError('No prose returned')
    (FOLDER/'provider-draft.md').write_text(answer['markdown'],encoding='utf-8')
    print('WRITER_API_COMPLETED',flush=True)

def assemble():
    with workflow() as w:meta=wh.require_W1(FOLDER,w)
    f=ROOT/meta['source_run'];text=(FOLDER/'provider-draft.md').read_text(encoding='utf-8');catalog=wh.read(FOLDER/'figure-catalog.json')
    captions={'raw-03':'非相邻板凳检查范围。仅检查i<j且j≥i+2的24531对；自身与整对相邻关系豁免。此图说明规则，不是数值安全证据。','process-01':'认证时间分段的宽度随盘入过程变化。横轴为真实认证分段对应时间，细化由整段几何包围难度决定，不代表固定时间积分步长。','process-02':'连续分段证书的投影分离间隙下界。严格正下界支持对应整段全部非相邻板对分离；该量不是实际最小欧氏距离，也不是统计置信区间。','process-03':'活动接触特征的法向间隙。根后曲线仅为同一运动学方程的数学延拓，不表示首碰后仍继续盘入或真实碰撞动力学。','result-01':'初始、代表性中间与终止时刻的整体位置。总览采用相同尺度，绘出实体外轮廓；离散形态图用于解释，不能替代连续碰撞证书。','result-02':'首次接触的局部有限矩形几何。龙头角点接触第8节龙身的有限侧边，整体板序为1与9；接触位置和尺寸来自同一终态。','result-03':'首碰左极限的224把手速率分布。各把手速率由定长连接的隐式微分得到，不假设整列同为1m/s。'}
    for fig in [x for x in catalog['figures'] if x['formal']]:
        token='@@FIGURE_'+fig['id']+'@@'
        if text.count(token)!=1:raise ValueError('Figure token count '+token)
        n=fig['number'];insert=f"![图{n} {fig['title']}]({fig['files']['png']['path']})\n\n图{n} {fig['title']}。{captions[fig['id']]}"
        text=text.replace(token,insert)
    rows=wh.read(f/'results/selected-handles.json')['handles'];names=['龙头前把手','第1节龙身前把手','第51节龙身前把手','第101节龙身前把手','第151节龙身前把手','第201节龙身前把手','龙尾后把手']
    table='表1 首次接触左极限的题目指定把手位置与速率。\n\n|把手|x / m|y / m|速率 / (m/s)|\n|---|---:|---:|---:|\n'+'\n'.join(f"|{name}|{v['x_m']:.6f}|{v['y_m']:.6f}|{v['speed_m_s']:.6f}|" for name,v in zip(names,rows))
    if text.count('@@TERMINAL_TABLE@@')!=1:raise ValueError('Terminal table marker missing or repeated')
    text=text.replace('@@TERMINAL_TABLE@@',table)
    position=wh.read(f/'review-recheck/precision-note.json')['ambiguous_coordinates'];speed=wh.read(f/'precision-supplement.json')['rounding_disclosure']['ambiguous_speed_coordinates']
    appendix='\n\n## 附录A 六位小数舍入歧义与数值区间\n\n以下编号采用计算索引：把手0为龙头前把手，把手223为龙尾后把手。区间为确定性数值包围，非统计置信区间；工作簿显示名义估计，跨格项最后一位不承诺唯一。表2和表3分别列出全部10个跨格位置坐标与24个跨格速率。\n\n表2 跨六位舍入格的位置坐标区间。\n\n|把手索引|坐标|下界 / m|上界 / m|\n|---:|:---:|---:|---:|\n'
    appendix+='\n'.join(f"|{x['handle_index_zero_based']}|{x['coordinate']}|{x['interval_m'][0]:.15f}|{x['interval_m'][1]:.15f}|" for x in position)
    appendix+='\n\n表3 跨六位舍入格的速率区间。\n\n|把手索引|下界 / (m/s)|上界 / (m/s)|\n|---:|---:|---:|\n'+'\n'.join(f"|{x['handle_index_zero_based']}|{x['interval_m_s'][0]:.15f}|{x['interval_m_s'][1]:.15f}|" for x in speed)
    appendix+='\n\n全部224个把手未舍入的位置、速度分量与速率上下界见[数值精度区间附件](数值精度区间.json)，完整终态表见[result2.xlsx](result2.xlsx)。\n'
    text+=appendix
    with np.load(f/'results/terminal-state.npz',allow_pickle=False) as z:precision={k:z[k].tolist() for k in ['position_m','position_lower_m','position_upper_m','velocity_m_s','speed_m_s']}
    certificate=wh.read(f/'precision-supplement.json')['certificate'];precision.update({k:certificate[k] for k in ['time_interval_s','velocity_lower_m_s','velocity_upper_m_s','speed_lower_m_s','speed_upper_m_s']})
    wh.new(FOLDER/'数值精度区间.json',precision);shutil=__import__('shutil');shutil.copyfile(f/'results/result2.xlsx',FOLDER/'result2.xlsx')
    (FOLDER/'author-draft.md').write_text(text,encoding='utf-8')
    wh.new(FOLDER/'authoring.json',{'source':'actual configured supplier Writer API, then deterministic source tables/captions/attachments integration by Codex','supplier_call':wh.read(FOLDER/'Writer-provider-call.json'),'raw_prose_path':'provider-draft.md','no_new_solver_or_figures':True,'appendix_position_rows':len(position),'appendix_speed_rows':len(speed),'duplicate_figures_not_embedded':['raw-01','raw-02']})
    print(json.dumps(validate_draft(FOLDER/'author-draft.md',FOLDER/'figure-catalog.json'),ensure_ascii=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('step',choices=['request','assemble']);a=p.parse_args();{'request':request,'assemble':assemble}[a.step]()
