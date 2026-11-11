"""Retry only a truncated code stage without introducing mathematical feedback."""
from pathlib import Path
import json,time,re,ast,hashlib
from datetime import datetime,timezone
from generate_2024_a_q1 import config,CASE
import httpx

def main():
 c=config();parent=sorted((CASE/'runs').glob('bailian-*'))[-1]
 run=CASE/'runs'/('bailian-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));run.mkdir()
 payload=json.loads((parent/'code-request.json').read_text(encoding='utf-8'))
 if payload['model']!=c['MODELCREW_LLM_MODEL']:raise ValueError('Model configuration changed')
 payload['max_tokens']=32000
 payload['messages'][-1]['content']+='\n请保持代码精简，避免不必要的扩展功能；只需完成以上文件接口。'
 for name in ['input.txt','proposal.md','proposal-request.json','proposal-response.json']:(run/name).write_bytes((parent/name).read_bytes())
 (run/'code-request.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 meta={'run_id':run.name,'provider':c['MODELCREW_LLM_PROVIDER'],'configured_model':c['MODELCREW_LLM_MODEL'],'parent_run':parent.name,'type':'code_stage_retry_reusing_independent_proposal','reference_data_sent':False,'mathematical_feedback_sent':False,'calls':[],'status':'started','proposal_usage_inherited_not_newly_billed':True}
 start=time.perf_counter();key=c['MODELCREW_LLM_API_KEY']
 try:
  r=httpx.post(c['MODELCREW_LLM_BASE_URL'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload,timeout=httpx.Timeout(600,connect=30))
  meta['calls'].append({'stage':'code','status_code':r.status_code,'elapsed_s':time.perf_counter()-start})
  if r.status_code>=400:
   (run/'api-error.txt').write_text(r.text.replace(key,'[REDACTED]'),encoding='utf-8');raise RuntimeError(f'API {r.status_code}')
  data=r.json();meta['calls'][-1]['usage']=data.get('usage');meta['calls'][-1]['returned_model']=data.get('model')
  (run/'code-response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
  choice=data['choices'][0];text=choice['message'].get('content') or '';(run/'code.md').write_text(text,encoding='utf-8')
  if choice.get('finish_reason')=='length':raise RuntimeError('code output truncated')
  blocks=re.findall(r'```(?:python|py)\s*\n(.*?)```',text,re.S)
  if len(blocks)!=1:raise ValueError('Expected one Python block')
  ast.parse(blocks[0]);(run/'generated_solver.py').write_text(blocks[0],encoding='utf-8');meta['status']='generated_awaiting_review'
 except Exception as e:meta['status']='failed';meta['error']=str(e).replace(key,'[REDACTED]');raise
 finally:
  (run/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
  (run/'retry_harness.py').write_bytes(Path(__file__).read_bytes())
  print(run,meta['status'],flush=True)
if __name__=='__main__':main()
