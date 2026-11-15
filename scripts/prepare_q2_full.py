from modelcrew.project_assets import asset_path
from pathlib import Path
import uuid
from scripts.run_d4_full import workflow
from scripts.run_d3_minimal import approved,read,write
from modelcrew.model_client import JsonModel
from modelcrew.config import ROOT
folder=asset_path(ROOT,'stage-d/runs/full')/('q2full-'+uuid.uuid4().hex[:16]);folder.mkdir();(folder/'sources').mkdir()
with workflow() as w:
 s=approved(w,'d6-bench-q2-20261109',2)
 write(folder/'contract.json',s['contract']['content']);write(folder/'mathematics.json',s['mathematics']['content']);write(folder/'inputs.json',{'inputs':s['contract']['content']['inputs']})
write(asset_path(ROOT,'stage-d/q2-coding/full-active.json'),{'folder':folder.relative_to(ROOT).as_posix()})
print('FOLDER '+str(folder),flush=True)
answer,meta=JsonModel().call(folder,'coding','你是项目代码手。只返回JSON对象，含code和implementation_notes。提供两个可直接拼入现有Python数值程序的函数：branch_domain_certificate()和left_children(a,b)。不执行代码，不修改模型，不输出最终数值答案。branch_domain_certificate使用调用方已定义的向外舍入区间函数iv/add/sub/mul/div/sqr/fiv及PI/BI；证明theta_head>=24时所有后继外侧唯一根delta<pi/2，隐式导数0<N/D<1，速度分母D>0。用区间计算r_min=BI*24、F(pi/2;r_min,ellmax=2.86)严格正，以及r_min>b*pi^2/8严格正；返回包含最低半径、F下界、N正性阈值下界、证明公式、passed的JSON原生字典，失败raise。fiv(delta,prev,ell)已有且自带b区间，prev是theta，不是radius。left_children(a,b)返回两个子区间的入栈顺序，供LIFO从左优先：[(mid,b),(a,mid)]；遇浮点无法细分raise。不导入新模块，允许numpy已经np、math已导入。theta>=24是计算适用域，不是碰撞终点，失败只代表UNKNOWN。',{'contract':read(folder/'contract.json'),'interval_api':'iv(x,y=None) -> (numpy lower,upper); elementwise outward-rounded add/sub/mul/div/sqr; fiv(delta,theta_prev,ell); PI and BI enclosures','proof':'D=b^2 delta+b*r*(1-cos delta)+r(r+b delta)sin delta; N=b^2 delta cos delta-b*r*(1-cos delta)+r(r+b delta)sin delta; D-N=(1-cos delta)(b^2 delta+2br)>0. For delta<pi/2, N>=delta*(2r^2/pi-br*pi/4)>0 if r>b*pi^2/8.'},max_tokens=4500)
write(folder/'supplier-coding-answer.json',answer);write(folder/'supplier-coding-call.json',meta)
(folder/'supplier-functions.py').write_text(answer['code'],encoding='utf-8');print('CODER_DONE',flush=True)
