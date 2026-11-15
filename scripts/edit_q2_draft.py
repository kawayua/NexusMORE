"""Editorial integration under admitted W1; preserve raw provider text and verified results."""
from modelcrew.project_assets import asset_path
from pathlib import Path
import re,json
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING
from modelcrew.config import ROOT
from modelcrew.collaboration import sha_file
from modelcrew import writing_hand as wh
f=asset_path(ROOT,'stage-d/runs/writing/d6-q2-20261109-v2');p=f/'author-draft.md'
text=p.read_text(encoding='utf-8');before=sha_file(p)
text=re.sub(r'图\s+(\d+)',r'图\1',text)
text=text.replace('**关键词**：','## 关键词\n\n')
a=text.index('本文研究板凳龙');b=text.index('## 关键词')
text=text[:a]+r'''针对板凳龙沿螺距0.55 m的阿基米德螺线盘入时何时应停止的问题，本文在第一题运动学模型上加入完整矩形外包络，检查全部24531对非相邻板凳。相邻整对豁免、孔洞按实心外包络处理、非相邻一经接触即停止均作为模型约定。为防止离散时间检查漏掉首次接触，采用整时间区间投影分离认证与左优先自适应细分，再在最早未决邻域验证有限边—角点接触特征。

计算得到首次接触时间为412.473838 s，严格括区为$[412.4738376736641,\,412.4738377034664]$ s，接触发生在龙头与第8节龙身之间。本文列出题目指定七个把手的终态，另交付全部224个把手的位置与首碰左极限速率。最大位置与速率包围误差分别约为$2.12\times10^{-8}$ m和$6.76\times10^{-8}$ m/s；全部结果中10个坐标、24个速率跨六位小数舍入格，均报告区间而不声称末位唯一。数值一致性检验支持此外包络模型的求解结果，不能据此给出真实构件的碰撞时间误差界。

'''+text[b:]
# Correct problem/model attribution and the full-pair rather than head-only objective.
a=text.index('第一题已给出');b=text.index('\n## 2 问题分析')
text=text[:a]+'''题目要求舞龙队沿第一题给定的螺线继续盘入，确定板凳之间首次不能再继续盘入的时刻，并给出当时全部把手的位置与速度；同时列出龙头前把手、第1、51、101、151、201节龙身前把手及龙尾后把手的结果[1]。螺距保持0.55 m，龙头前把手速率保持1 m/s。龙头板长3.41 m，其余板长2.20 m，板宽均为0.30 m，孔中心距最近板端0.275 m。

第一题图1已说明板凳实体与孔位，第一题图3已展示初态与盘入方向，本题不重复插入。本文承接第一题的运动学关系，新增二维刚体外包络、相邻整对豁免与非相邻首次接触即停等建模假设。检查对象为所有非相邻板对，不预先限定碰撞一定涉及龙头；龙头参与首碰是计算结果。本文速度表沿用题目工作簿的标量速率口径，运动学计算同时保留速度向量。
'''+text[b:]
text=text.replace('对任一固定非零轴，如果整时间区间内所有非相邻板对的投影包围严格分离，则该整段可证安全；','对每一非相邻板对分别选择固定非零投影轴；若该对在整个时间区间内的投影包围严格分离，且所有待检板对均满足这一条件，则该整段可证安全；')
text=text.replace('这与题面规则一致，但意味着模型不宣称整条龙在任意时刻均与真实实体无碰。','这是新增模型约定，并非题面明确规定的豁免规则；它使本模型不覆盖相邻构件连接处的真实碰撞。')
# LaTeX equations and notation with correct units.
a=text.index('| 符号 |');b=text.index('\n## 5 模型建立')
text=text[:a]+r'''计算索引中，把手为$i=0,\ldots,223$，板凳为$i=0,\ldots,222$。涉及相邻板对时另用$j$表示第二块板凳的索引。主要符号如下。

|符号|含义|单位|
|---|---|---|
|$b$|螺线常数$0.55/(2\pi)$|m/rad|
|$\theta_i$|第$i$个把手的螺线参数角|rad|
|$\mathbf X(\theta),\mathbf P_i$|螺线位置映射与把手位置|m|
|$S(\theta)$|由原点计的螺线弧长|m|
|$v_0$|龙头前把手给定速率，取1|m/s|
|$t,t_*$|经过时间与首次接触时间|s|
|$\ell_i$|第$i$块板凳两孔中心距|m|
|$\mathbf T_i$|曲线参数导向量$\mathbf X'(\theta_i)$|m/rad|
|$\mathbf d_i$|相邻把手差$\mathbf P_{i+1}-\mathbf P_i$|m|
|$\dot\theta_i,\mathbf v_i$|把手参数角速度、速度向量|rad/s，m/s|
|$\mathbf c_i,\mathbf u_i,\mathbf n_i$|板凳中心、长轴及法向单位向量|m，无量纲，无量纲|
|$h_i,w$|半板长与半板宽|m|
|$R_i$|第$i$块板凳的闭矩形外包络|平面集合|
|$\mathbf a,g_{ij},G_{ij}$|单位投影轴、轴上分离间隙、四轴最大间隙|无量纲，m，m|
|$I,\varphi$|待认证时间区间、活动角点到有限边的有向法向间隙|s区间，m|
'''+text[b:]
a=text.index('沿用第一题，阿基米德');b=text.index('\n### 5.2')
text=text[:a]+r'''沿用第一题的螺线及弧长关系，令$b=0.55/(2\pi)$，则

$$
\mathbf X(\theta)=b\theta(\cos\theta,\sin\theta),\qquad
S(\theta)=\frac b2\left[\theta\sqrt{1+\theta^2}+\operatorname{asinh}\theta\right]. \tag{1}
$$

龙头前把手从第16圈的正横轴位置开始盘入。设其参数角为$\theta_0(t)$，由恒定线速率得到

$$
S(32\pi)-S(\theta_0(t))=v_0t,\qquad v_0=1\ \mathrm{m/s}. \tag{2}
$$

因为$S'(\theta)=b\sqrt{1+\theta^2}>0$，式（2）可单调反解。令$\mathbf P_i=\mathbf X(\theta_i)$，各连接同时满足

$$
\|\mathbf P_{i+1}-\mathbf P_i\|=\ell_i,\qquad
\ell_0=2.86\ \mathrm m,\quad \ell_i=1.65\ \mathrm m\ (i\ge1). \tag{3}
$$

两种孔距分别由完整板长减去两端各0.275 m得到。每一步取前一把手外侧的最近有效根，不能任意选择其他螺线圈的交点。对式（3）的平方形式求时间导数，设$\mathbf d_i=\mathbf P_{i+1}-\mathbf P_i$、$\mathbf T_i=\mathbf X'(\theta_i)$，有$\mathbf d_i\cdot(\mathbf v_{i+1}-\mathbf v_i)=0$，从而

$$
\dot\theta_0=-\frac{v_0}{b\sqrt{1+\theta_0^2}},\qquad
\dot\theta_{i+1}=\frac{\mathbf d_i\cdot\mathbf T_i}{\mathbf d_i\cdot\mathbf T_{i+1}}\dot\theta_i,\qquad
\mathbf v_i=\mathbf T_i\dot\theta_i. \tag{4}
$$

各把手的速率为$\|\mathbf v_i\|$。本次在龙头参数角不小于24 rad的计算域内，验证了外侧最近根的唯一性及分母$\mathbf d_i\cdot\mathbf T_{i+1}>0$；附录B说明其依据。24 rad是分支认证的有效域边界，不能当作物理停止条件。若分支或分母不能继续认证，计算必须记为未决，而不是把该时刻当作碰撞。
'''+text[b:]
a=text.index('对第 i 块板凳');b=text.index('\n![图1 ')
text=text[:a]+r'''对第$i$块板凳，定义

$$
\mathbf c_i=\frac{\mathbf P_i+\mathbf P_{i+1}}2,\qquad
\mathbf u_i=\frac{\mathbf d_i}{\ell_i},\qquad
\mathbf n_i=(-u_{i,y},u_{i,x}). \tag{5}
$$

由于两孔距板端的偏移相同，孔位连线中点也是板体中心。半板长为$h_0=1.705$ m、其余$h_i=1.10$ m，半板宽为$w=0.15$ m，闭矩形为

$$
R_i=\{\mathbf c_i+\alpha\mathbf u_i+\beta\mathbf n_i:|\alpha|\le h_i,\ |\beta|\le w\}. \tag{6}
$$

孔洞不从碰撞体中扣除。图1说明候选板对规则：只检查$i<j$且$j\ge i+2$，共$\binom{223}{2}-222=24531$对。对单位轴$\mathbf a$，投影分离间隙为

$$
\begin{aligned}
g_{ij}(\mathbf a,t)={}&|\mathbf a\cdot(\mathbf c_j-\mathbf c_i)|
-h_i|\mathbf a\cdot\mathbf u_i|-w|\mathbf a\cdot\mathbf n_i|\\
&-h_j|\mathbf a\cdot\mathbf u_j|-w|\mathbf a\cdot\mathbf n_j|.
\end{aligned} \tag{7}
$$

在单时刻，令$G_{ij}(t)$为式（7）在四条局部轴$\{\mathbf u_i,\mathbf n_i,\mathbf u_j,\mathbf n_j\}$上的最大值。$G_{ij}>0$表明矩形分离，$G_{ij}=0$表明边界接触，$G_{ij}<0$表明重叠。按闭集首次接触定义终止时间

$$
t_*=\inf\{t\ge0:\exists\,i<j,\ j\ge i+2,\ R_i(t)\cap R_j(t)\ne\varnothing\}. \tag{8}
$$

式（8）包含孤立切触，不要求先出现穿透，也不预先指定活动板对。
'''+text[b:]
text=text.replace('对任一固定非零轴 a，若整时间区间内所有非相邻板对的状态投影包围严格分离，则证该整段分离。','对每一非相邻板对分别选择固定非零轴，将整个时间区间$I$的中心和旋转方向一起包围；若该轴上的分离间隙下界严格为正，即可证明该对在$I$内始终分离。不同板对允许使用不同轴，只有全部板对均通过，才认证整段安全。')
text=text.replace('Brent 方法给出名义根','Brent带括方法[2]给出名义根')
text=text.replace('下表列出七个选定把手的真实终态位置与速率（六位小数）。','表1列出题目指定七个把手在模型首碰左极限的终态位置与速率，均按六位小数显示。')
text=text.replace('龙头前把手速率接近 1 m/s','龙头前把手速率保持题设的1 m/s')
text=text.replace('主表全部 10 个位置坐标与 24 个速率分量跨六位小数舍入格','全部224个把手的结果中，有10个位置坐标与24个速率值跨六位小数舍入格')
text=text.replace('速率分量','速率值')
text=text.replace('图5给出终止时刻整体位置，来自同一已验证运动学状态','图5展示0 s、200 s与终止时刻的整体位置，三个面板采用相同总览尺度')
text=text.replace('本文未进行不同容差收敛实验、基准比较或统计显著性检验，也不捏造此类结果。','上述数值包围的严格性来自整段区间证据及事件特征条件，重复计算本身只验证可复现性。')
text=text.replace('整体模型与真实碰撞时间未必具有单边界等价性','整体模型终止时间与真实碰撞时间未必存在可保证的单侧大小关系')
# Printed interval endpoints must be rounded outward, preserving the enclosure.
src=ROOT/wh.read(f/'run.json')['source_run'];pos=wh.read(src/'review-recheck/precision-note.json')['ambiguous_coordinates'];spd=wh.read(src/'precision-supplement.json')['rounding_disclosure']['ambiguous_speed_coordinates']
def outward(x,lower):return format(Decimal.from_float(x).quantize(Decimal('0.000000000000001'),rounding=ROUND_FLOOR if lower else ROUND_CEILING),'f')
for x in pos:
    lo,hi=x['interval_m'];old=f"|{x['handle_index_zero_based']}|{x['coordinate']}|{lo:.15f}|{hi:.15f}|";new=f"|{x['handle_index_zero_based']}|{x['coordinate']}|{outward(lo,True)}|{outward(hi,False)}|";assert old in text;text=text.replace(old,new)
for x in spd:
    lo,hi=x['interval_m_s'];old=f"|{x['handle_index_zero_based']}|{lo:.15f}|{hi:.15f}|";new=f"|{x['handle_index_zero_based']}|{outward(lo,True)}|{outward(hi,False)}|";assert old in text;text=text.replace(old,new)
text=text.replace('以下编号采用计算索引：','表中区间下界向负无穷、上界向正无穷舍入到小数点后15位，保留包围性。以下编号采用计算索引：')
text+=r'''

## 附录B 有效分支与误差传播的依据

设某前驱把手参数角为$\theta$，半径$r=b\theta$，后继角差为$\delta>0$，对应孔距为$\ell$。式（3）等价于

$$
F(\delta)=(b\delta)^2+4r(r+b\delta)\sin^2(\delta/2)-\ell^2=0. \tag{9}
$$

在$0<\delta<\pi$时，$F$对$\delta$严格递增。$F(0)<0$，而在本次验证域$\theta\ge24$、最大孔距2.86 m处，$F(\pi/2)$的区间下界大于$1.2441\ \mathrm{m^2}$；半径增大或孔距减小时此正性保持。因此所选最近外侧根唯一且$0<\delta<\pi/2$。

为说明绝对参数角的误差传播，令$R=r+b\delta$，式（4）的分子、分母分别记为$N,D$。直接展开得到

$$
\begin{aligned}
D&=b^2\delta+br(1-\cos\delta)+rR\sin\delta,\\
N&=b^2\delta\cos\delta-br(1-\cos\delta)+rR\sin\delta,\\
D-N&=(1-\cos\delta)(b^2\delta+2br)>0.
\end{aligned} \tag{10}
$$

利用$\sin\delta\ge2\delta/\pi$及$1-\cos\delta\le\pi\delta/4$，有$N\ge\delta(2r^2/\pi-br\pi/4)>0$；最后一步由本次域内$r>b\pi^2/8$保证。故$0<N/D<1$，后继绝对参数角随前驱绝对参数角单调且非扩张。它不是角差$\delta$映射的收缩结论，也不等价于各把手线速率相等。

端点参数角的验证包围可据此向外传播；由于各把手参数角随时间单调递减，两端包围进一步给出整时间段状态区间。将该区间映射到式（5）—（7），得到包含板体转动的投影分离下界。即使测试轴固定，只要存在严格正下界，假设两矩形有公共点就会导致其投影同时落入两个严格分离的投影区间，形成矛盾。这说明固定轴可以证明运动矩形整段分离，而不要求把板凳姿态冻结在中点。
'''
p.write_text(text,encoding='utf-8')
wh.new(f/'editorial-integration.json',{'raw_API_prose_preserved':True,'assembled_before_sha256':before,'final_author_draft_sha256':sha_file(p),'changes':['corrected head-only objective to all nonadjacent board pairs','distinguished model assumptions from original problem wording','fixed separate fixed axis per board pair','converted equations and symbols to LaTeX with units','added body figure references and keyword section','added actual citations and branch explanation under confirmed model','clarified 10 positions and 24 scalar speeds refer to all 224, not selected table','rounded all printed lower/upper bounds outward with Decimal','kept original image bytes, numerical results, and W1 claim scope'],'not_manuscript_approval':True})
print('EDITORIAL_INTEGRATION_DONE')
