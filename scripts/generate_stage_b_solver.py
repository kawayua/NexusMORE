"""Generate solver implementation for the approved stage-B contract, not an independent baseline."""
from pathlib import Path
import json,time,re,ast,hashlib,sys
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from modelcrew.workflow import Workflow
from modelcrew.contracts import digest
from generate_2024_a_q1 import config
import httpx
ROOT=Path(__file__).resolve().parents[1]
def main():
 c=config();key=c['MODELCREW_LLM_API_KEY']
 with Workflow() as w:
  s=w.inspect('dragon-q1')
  if s['task']['current_version']!=2 or not s['task']['model_approved'] or s['task']['result_approved']:raise ValueError('Need approved v2 awaiting result')
  contract=s['contract']['content'];sha=s['contract']['sha256']
 run=ROOT/'stage-b/runs'/datetime.now(timezone.utc).strftime('solver-v2-%Y%m%dT%H%M%S%fZ');run.mkdir(parents=True)
 (run/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding='utf-8')
 parent=ROOT/'stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z/generated_solver.py'
 prompt='''实现已由用户确认的v2契约，只输出一个完整Python代码块，不执行。你之前v1代码附后作为修改起点，不是独立生成实验。必须实际实现全部新增检查，不能只写声明。
只可读取/work/input/result1.xlsx；所有产物写/work/output。无网络、子进程、环境读取或安装依赖。可用numpy/scipy/openpyxl和标准库。独立函数solve(t,xtol)供非整数时刻差分与加严复算，不把六位小数舍入带入内部。
具体实现要求：
1. 弧长方程Brent求龙头极角；连接点用delta∈(0,pi)及稳定平方弦长残差，检查异号与收敛，记录最大残差和索引。由f'(delta)>0的项给出简要证明，记录括区有效性。
2. 速度约束求导递推；分母是d dot Pprime，单位m²，abs值<=1e-10 m²时记录并抛错。记录最小分母及时间节点，不将奇异值冒充通过。
3. trajectories.npz必含time_s(301,),theta_rad(301,224),position_m(301,224,2),velocity_m_s(301,224,2),speed_m_s(301,224)，检查有限性、形状、顺序、时间方向、初始(8.8,0)及速度方向。
4. 全301时刻scipy.integrate.quad独立核验龙头走过的弧长和t，报告epsabs/epsrel、误差估计、最大残差（自适应积分无需伪造固定步长）。
5. h=1e-2,1e-3,1e-4秒，对t=1,60,120,180,240,299全部224节点中心差分；t=0,300二阶单侧差分。保存每种h最大向量误差，h=1e-3的内部与端点误差均<=1e-5；不强制h减小时严格单调。
6. 默认xtol=5e-14、rtol取合法下限；t=0,60,120,180,240,300，用xtol=5e-15复算，位置差<=1e-10 m。保存样本、容差与位置/速度差，不要求浮点每位一致。
7. 在原模板副本生成result1.xlsx，数据数值舍入6位并设0.000000；回读检查表名、所有行标签及时间列未变化、维度449x302和225x302、数据有限、相对内部值舍入误差<=5.00001e-7。
8. 保存checks.json，含contract_sha256(下面提供)、code_sha256(可读取__file__仅用于审阅代码自身哈希，此为唯一路径例外)、checks对象。checks的12个键恰为契约checks的ID，每个值含status(passed/failed/unknown)、evidence(实际数值与样本)。必须保存失败时报告并非零退出；未运行不写passed。v2_execution_status包含actual_solver_run=true和fixture=false，只是容器自述，外部还会独立验证。
9. 原4项检查中head_speed、rod_distance、velocity_fd、completeness需要真实数值证据。新增checks逐项落实。控制程序简明，预计3分钟内执行。
绝不读取参考答案或历史产物。不要复制虚构的误差数字，全部当次计算。'''
 messages=[{'role':'system','content':'你是数值计算实现工程师。只按已确认契约实现代码；不得把未运行结果写成事实。'},{'role':'user','content':'契约hash='+sha+'\n契约='+json.dumps(contract,ensure_ascii=False)+'\nv1代码：\n'+parent.read_text(encoding='utf-8')+'\n实现指令：\n'+prompt}]
 payload={'model':c['MODELCREW_LLM_MODEL'],'max_tokens':24000,'enable_thinking':False,'thinking':{'type':'disabled'},'messages':messages}
 (run/'request.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 meta={'run_id':run.name,'task_id':'dragon-q1','contract_version':2,'contract_sha256':sha,'provider':c.get('MODELCREW_LLM_PROVIDER'),'model':c['MODELCREW_LLM_MODEL'],'mode':'approved_contract_implementation_with_feedback','reference_numeric_answers_sent':False,'v1_model_code_sent':True,'status':'generating'}
 start=time.perf_counter()
 try:
  r=httpx.post(c['MODELCREW_LLM_BASE_URL'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload,timeout=httpx.Timeout(600,connect=30))
  meta.update(status_code=r.status_code,elapsed_generation_s=time.perf_counter()-start)
  if r.status_code>=400:(run/'api-error.txt').write_text(r.text.replace(key,'[REDACTED]'),encoding='utf-8');raise RuntimeError(f'API {r.status_code}')
  data=r.json();(run/'response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');meta['usage']=data.get('usage')
  choice=data['choices'][0];content=choice['message'].get('content') or '';(run/'response.md').write_text(content,encoding='utf-8')
  if choice.get('finish_reason')=='length':raise ValueError('Truncated code')
  blocks=re.findall(r'```(?:python|py)\s*\n(.*?)```',content,re.S)
  if len(blocks)!=1:raise ValueError('Expected single code block')
  ast.parse(blocks[0]);(run/'generated_solver.py').write_text(blocks[0],encoding='utf-8');meta['status']='generated_awaiting_review'
  print('RUN_DIR',run,flush=True)
 except Exception as e:meta.update(status='failed',error=str(e).replace(key,'[REDACTED]'));raise
 finally:
  (run/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  (run/'generation_harness.py').write_bytes(Path(__file__).read_bytes())
if __name__=='__main__':main()
