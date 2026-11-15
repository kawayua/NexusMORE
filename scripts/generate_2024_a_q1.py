"""Generate an independent configured-provider baseline. Does not execute model code."""
from modelcrew.project_assets import asset_path
from pathlib import Path
import os,json,time,hashlib,sys
from datetime import datetime,timezone
import httpx
from pypdf import PdfReader
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1]
CASE=asset_path(ROOT,'stage-a/2024-A-problem-1')
def config():
 d={}
 for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1); d[k.strip()]=v.strip().strip('\"').strip("'")
 return {**d,**os.environ}
def main():
 c=config(); key=c['MODELCREW_LLM_API_KEY']; base=c['MODELCREW_LLM_BASE_URL'].rstrip('/'); candidate=c['MODELCREW_LLM_MODEL']
 provider=c.get('MODELCREW_LLM_PROVIDER','configured')
 run=CASE/'runs'/(provider+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));run.mkdir(parents=True)
 meta={'run_id':run.name,'type':'independent_llm_baseline','provider':provider,'configured_model':candidate,'base_url':base,'reference_data_sent':False,'calls':[],'status':'started'}
 client=httpx.Client(timeout=httpx.Timeout(300,connect=30),headers={'Authorization':'Bearer '+key})
 def save(): (run/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 def request(method,path,**kwargs):
  start=time.perf_counter(); response=client.request(method,base+path,**kwargs)
  record={'method':method,'endpoint':path,'status_code':response.status_code,'elapsed_s':time.perf_counter()-start};meta['calls'].append(record)
  if response.status_code>=400:
   error=response.text.replace(key,'[REDACTED]');(run/f'api-error-{len(meta["calls"])}.txt').write_text(error,encoding='utf-8');save();raise RuntimeError(f'API {response.status_code}; see saved sanitized error')
  return response.json(),record
 try:
  # Some dedicated deployments have no model-list endpoint. Use the exact
  # configured identifier there; a completion must still verify acceptance.
  try:
   models,rec=request('GET','/models')
   ids=[x['id'] for x in models.get('data',[])];(run/'model-list.json').write_text(json.dumps(ids,ensure_ascii=False,indent=2),encoding='utf-8')
   norm=lambda s:''.join(x for x in s.lower() if x.isalnum())
   matches=[x for x in ids if norm(x)==norm(candidate)]
   model=candidate if candidate in ids else (matches[0] if len(matches)==1 else candidate)
   meta['model_resolution']='listed' if model in ids else 'configured_identifier_pending_completion'
  except RuntimeError:
   status=meta['calls'][-1]['status_code']
   if status not in (404,405):raise
   model=candidate;meta['model_resolution']='deployment_without_models_endpoint'
  meta['resolved_model']=model;save();print('Resolved model:',model,flush=True)
  manifest=json.loads((CASE/'input-manifest.json').read_text(encoding='utf-8'))
  source=next(x for x in manifest['files'] if x['role']=='problem_statement');pdf=Path(source['path'])
  assert hashlib.sha256(pdf.read_bytes()).hexdigest().lower()==source['sha256'].lower()
  text='\n'.join(p.extract_text() or '' for p in PdfReader(pdf).pages[:2])
  template=Path(next(x['path'] for x in manifest['files'] if x['role']=='required_output_template'))
  wb=load_workbook(template,read_only=True);layout={s.title:{'rows':s.max_row,'cols':s.max_column,'row_labels_sample':[(i,s.cell(i,1).value) for i in [2,3,4,s.max_row-2,s.max_row-1,s.max_row]],'time_headers':'B列0 s，C列1 s，依次到KP列300 s'} for s in wb};wb.close()
  evidence='题面第1-2页原文：\n'+text+'\n图4视觉说明：A点位于正x轴，箭头朝下表示顺时针盘入。\n模板布局：\n'+json.dumps(layout,ensure_ascii=False)
  (run/'input.txt').write_text(evidence,encoding='utf-8')
  system='你是独立数学建模求解者。只依据用户提供的原始题目和模板信息独立求解，不存在可读取的参考答案。只处理问题1。必须区分题面事实和假设，给出可运行、可复核方案。'
  proposal_prompt=evidence+'\n请独立给出问题1建模方案：方程、初始化、连接约束、根选择、速度计算、数值方法、输出布局和自检方法。此轮不要输出代码。方案务必简洁，不超过1200个中文字；用必要公式表达，避免重复复述题目。'
  messages=[{'role':'system','content':system},{'role':'user','content':proposal_prompt}]
  def chat(stage,msgs,max_tokens):
   payload={'model':model,'messages':msgs,'max_tokens':max_tokens}
   if provider.lower()=='mimo':payload['thinking']={'type':'disabled'}
   (run/f'{stage}-request.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
   data,rec=request('POST','/chat/completions',json=payload);rec.update(stage=stage,usage=data.get('usage'),returned_model=data.get('model'))
   (run/f'{stage}-response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
   choice=data['choices'][0];content=choice['message'].get('content') or ''
   (run/f'{stage}.md').write_text(content,encoding='utf-8');save()
   if choice.get('finish_reason')=='length':raise RuntimeError(stage+' output truncated')
   return content
  proposal=chat('proposal',messages,9000)
  messages +=[{'role':'assistant','content':proposal},{'role':'user','content':'''请根据你的方案输出完整单文件Python程序。只输出一个```python代码块，无需执行。容器工作目录/work，允许读取/work/input/result1.xlsx模板，必须写入/work/output/result1.xlsx副本；不得读取其他目录，不联网，不创建子进程，不安装依赖，不读取环境变量。可用numpy、scipy、openpyxl和标准库。
另保存/work/output/trajectories.npz，数组time_s形状(301,)，position_m形状(301,224,2)，velocity_m_s形状(301,224,2)，speed_m_s形状(301,224)，均使用未舍入数值。时间从0至300每秒；把手按龙头前把手、221节龙身前把手、龙尾前把手、龙尾后把手排序。输出Excel数值保留6位小数。可保存你自己的检查报告到/work/output。代码必须独立完成计算，不得要求外部答案。'''}]
  code_response=chat('code',messages,12000)
  import re,ast
  blocks=re.findall(r'```(?:python|py)\s*\n(.*?)```',code_response,re.S)
  if len(blocks)!=1:raise RuntimeError('Expected exactly one Python code block')
  code=blocks[0];ast.parse(code);(run/'generated_solver.py').write_text(code,encoding='utf-8')
  (run/'generation_harness.py').write_bytes(Path(__file__).read_bytes())
  meta['status']='generated_awaiting_review';save();print('RUN_DIR',run,flush=True)
 except Exception as exc:
  meta['status']='failed';meta['error']=str(exc).replace(key,'[REDACTED]');save();print('FAILED',meta['error'],'RUN_DIR',run,flush=True);raise
 finally:client.close()
if __name__=='__main__':main()
