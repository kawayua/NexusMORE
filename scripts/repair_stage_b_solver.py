"""Feedback repair of a rejected generated v2 implementation, preserving parent evidence."""
from pathlib import Path
import json,hashlib,time,re,ast,sys
from datetime import datetime,timezone
import httpx
from generate_2024_a_q1 import config
ROOT=Path(__file__).resolve().parents[1]
def main():
 c=config();key=c['MODELCREW_LLM_API_KEY'];parent=sorted((ROOT/'stage-b/runs').glob('solver-v2-*'))[-1]
 issues='''静态审阅拒绝当前代码，请修订全部问题后仅输出完整Python代码，不执行。
F1 THETA_I错误为2π*(16+1)，必须为2π*16=32π，初始坐标必须与明确常量[8.8,0]核对，不用同一错误公式自证。
F2 head_theta用F0-F(theta)=t遗漏B，必须B*(F0-F(theta))=HEAD_SPEED*t。quad和闭式核验都必须使用B*sqrt(1+theta²)和B*(F0-F)，单位米，不能同错自证。
F3 原velocity_fd端点一阶不满足误差；两项FD检查都用h=1e-3下的正确二阶单侧公式。t=0用(-3p(0)+4p(h)-p(2h))/(2h)；t=300用(3p(300)-4p(300-h)+p(300-2h))/(2h)。内部用(p(t+h)-p(t-h))/(2h)。不需要所有301时刻重复三种差分，只要求t=1,60,120,180,240,299和两个端点全部224节点。
F4 平方弦长准确导数f'=2B²δ+4rB sin²(δ/2)+4r(r+Bδ)sin(δ/2)cos(δ/2)；之前实现最后系数误为2，要修正，保留严格单调证明和括区检查，记录f(0)、f(pi)符号范围。
F5 Excel回读必须实际逐数据单元检查number_format=="0.000000"，两个表的时间行和所有行标签也要实际检查，不能报告常量来代替验证。
F6 try/except捕获计算失败，checks的12个ID先unknown；异常保存checks.json（绑定代码hash和契约hash、错误节点时间），非零退出；不能只在完全计算结束才写报告。成功时每个检查都附实算证据。
F7 在quad报告记录最大误差估计与epsabs/epsrel，不需要伪造固定步长；原有容差不变。检查全部输出shape/有限性、与实际导出一致性。
F8 可删无用函数、重复导数重写及多余全时刻差分循环，代码控制简洁。代码自述actual_solver_run只作证据，还将由容器退出记录和独立核验确认。
保留契约要求、固定物理参数、只读输入/只写output、自身__file__用于代码哈希。不要给出硬编码误差结果。参考答案与论文未提供。'''
 review={'code_sha256':hashlib.sha256((parent/'generated_solver.py').read_bytes()).hexdigest(),'security_review':{'passed':True,'scope':'Manual static review: permitted input/output and code-self-hash only.'},'math_review':{'passed':False,'findings':issues},'decision':'rejected_before_execution'}
 (parent/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8');m=json.loads((parent/'metadata.json').read_text(encoding='utf-8'));m['status']='rejected_at_math_review';(parent/'metadata.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
 run=ROOT/'stage-b/runs'/datetime.now(timezone.utc).strftime('solver-v2-%Y%m%dT%H%M%S%fZ');run.mkdir()
 (run/'contract.json').write_bytes((parent/'contract.json').read_bytes());(run/'feedback.txt').write_text(issues,encoding='utf-8')
 req=json.loads((parent/'request.json').read_text(encoding='utf-8'))
 req['messages'] +=[{'role':'assistant','content':(parent/'response.md').read_text(encoding='utf-8')},{'role':'user','content':issues}]
 (run/'request.json').write_text(json.dumps(req,ensure_ascii=False,indent=2),encoding='utf-8')
 meta={'run_id':run.name,'task_id':'dragon-q1','contract_version':2,'parent_run':parent.name,'contract_sha256':m['contract_sha256'],'model':c['MODELCREW_LLM_MODEL'],'mode':'feedback_repair','status':'generating','feedback':issues}
 start=time.perf_counter()
 try:
  r=httpx.post(c['MODELCREW_LLM_BASE_URL'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=req,timeout=httpx.Timeout(600,connect=30));meta.update(status_code=r.status_code,elapsed_generation_s=time.perf_counter()-start)
  if r.status_code>=400:(run/'api-error.txt').write_text(r.text.replace(key,'[REDACTED]'),encoding='utf-8');raise ValueError(f'API {r.status_code}')
  data=r.json();(run/'response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');meta['usage']=data.get('usage')
  choice=data['choices'][0];text=choice['message'].get('content') or '';(run/'response.md').write_text(text,encoding='utf-8')
  if choice.get('finish_reason')=='length':raise ValueError('Truncated code')
  blocks=re.findall(r'```(?:python|py)\s*\n(.*?)```',text,re.S)
  if len(blocks)!=1:raise ValueError('Expected one Python block')
  ast.parse(blocks[0]);(run/'generated_solver.py').write_text(blocks[0],encoding='utf-8');meta['status']='generated_awaiting_review';print('RUN_DIR',run,flush=True)
 except Exception as e:meta.update(status='failed',error=str(e).replace(key,'[REDACTED]'));raise
 finally:(run/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
