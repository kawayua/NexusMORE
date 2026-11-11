"""Compose approved generic Writer snapshots; preserve originals and record transformations."""
import json,re,shutil
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.collaboration import sha_file
from modelcrew.modeling_paper import writing_context,validate_draft
BASE=ROOT/'stage-e/runs/generic-q1-q2-20261110-v1'
OUT=BASE/'assembly/source-v6'
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 manifest=json.loads((BASE/'input-freeze-manifest.json').read_text(encoding='utf-8'))
 assert all(sha_file(BASE/x['snapshot'])==x['sha256'] for x in manifest['files'])
 OUT.mkdir(parents=True,exist_ok=False);(OUT/'figures').mkdir();context=writing_context();save(OUT/'writer-context.json',context)
 sections={};figures=[];edits=[];parts={};sources={}
 for chapter in manifest['chapters']:
  q=chapter['question_id'];folder=(BASE/chapter['snapshot_manuscript']).parent;text=(BASE/chapter['snapshot_manuscript']).read_text(encoding='utf-8');parts[q]=text
  assert sha_file(BASE/chapter['snapshot_manuscript'])==chapter['manuscript_sha256']
  chunks=re.split(r'^##\s+(.+?)\s*$',text,flags=re.M);sections[q]={chunks[i]:chunks[i+1].strip() for i in range(1,len(chunks),2)}
  sources[q]={'generic_writer_run_id':chapter['generic_writer_run_id'],'binding':chapter['binding'],'snapshot_folder':folder.relative_to(ROOT).as_posix(),'markdown_sha256':chapter['manuscript_sha256'],'catalog_sha256':chapter['figure_catalog_sha256'],'W1':chapter['W1'],'original_approvals_preserved':True}
  cat=json.loads((folder/'figure-catalog.json').read_text(encoding='utf-8'))
  for figure in cat['figures']:
   if not figure['formal']:continue
   new={**figure,'id':q+'-'+figure['id'],'question_ids':[q],'files':{}}
   for fmt,item in figure['files'].items():
    dst=OUT/'figures'/(q+'-'+figure['id']+'.'+fmt);shutil.copyfile(folder/item['path'],dst);assert sha_file(dst)==item['sha256'];new['files'][fmt]={'path':dst.relative_to(OUT).as_posix(),'sha256':item['sha256']}
   figures.append(new)
  shutil.copyfile(BASE/chapter['snapshot_manuscript'],OUT/(q+'-approved-original.md'))
 def edit(q,text,before,after,kind):
  count=text.count(before)
  if count:edits.append({'question':q,'kind':kind,'before':before,'after':after,'count':count,'original_unchanged':True})
  return text.replace(before,after)
 def protect(q,text):
  if q=='q1':
   text=edit(q,text,'其余223个孔距','其余222个孔距','count_typo_consistency_with_224_handles_and_223_segments')
   text=edit(q,text,'本文只回答问题1，不含碰撞、调头和优化问题1。','本部分只回答问题一，不含碰撞、调头和优化问题。','scope_copyedit')
   text=edit(q,text,'$T$',' $T_1$ '.strip(),'sampling_horizon_symbol')
   text=edit(q,text,'$T=300$','$T_1=300$','sampling_horizon_symbol')
   text=edit(q,text,'终止时刻，$T_1=300$','问题一观测终点，$T_1=300$','sampling_scope_clarification')
  else:
   text=edit(q,text,'但六个面显示的位小数存在近似性','但六位小数显示存在近似性','copy_typo')
   text=edit(q,text,'；结果仍待用户最终确认','','remove_obsolete_internal_approval_note')
   text=edit(q,text,'各把手速率由定长约束递推得到且略低于龙头','除龙头外，其余把手速率由定长约束递推得到且略低于龙头','exclude_head_from_comparison')
   text=edit(q,text,'上述核验说明数值实现与模型约束一致。','上述核验说明数值实现与模型约束一致。\n\n独立差分误差用于交叉核验实现；终止事件区间内的严格速率包络误差上界为 $6.756796144813393\\times10^{-8}$ m/s，同样低于 $10^{-5}$ m/s 容差。全体把手中有24个的包络跨越六位小数舍入分界，因此小误差不等于全部末位唯一；表2所列七个代表把手均不在该集合中。','distinguish_finite_difference_check_from_frozen_strict_speed_enclosure')

  if q=='q2' and '速度递推分母与分子在旋转坐标系' in text:
   start=text.index('对已确认分支，可写出速度递推分母与分子在旋转坐标系')
   prefix,local=text[:start],text[start:]
   revised=re.sub(r'\bN\b',lambda m:r'N_{\mathrm{num}}',local)
   revised=revised.replace('显式形式：','显式形式（其中 $N_{\\mathrm{num}}$ 为局部分子，区别于把手总数 $N$）：')
   before=r'D=b^2\delta+br(1-\cos\delta)+rR\sin\delta,\qquad'+'\n'+r'N_{\mathrm{num}}=b^2\delta\cos\delta-br(1-\cos\delta)+rR\sin\delta,\qquad R=r+b\delta .'
   after=r'\begin{aligned}'+'\n'+r'D&=b^2\delta+br(1-\cos\delta)+rR\sin\delta,\\'+'\n'+r'N_{\mathrm{num}}&=b^2\delta\cos\delta-br(1-\cos\delta)+rR\sin\delta,\\'+'\n'+r'R&=r+b\delta .'+'\n'+r'\end{aligned}'
   assert before in revised
   revised=revised.replace(before,after)
   edits.append({'question':q,'kind':'disambiguate_local_numerator_and_multiline_equation','before':local,'after':revised,'original_unchanged':True})
   text=prefix+revised
  text=text.replace('本文','本部分')
  text=re.sub(r'图\s*(\d+)',lambda m:'@@F_'+q+'_'+m[1]+'@@',text)
  text=re.sub(r'表\s*(\d+)',lambda m:'@@T_'+q+'_'+m[1]+'@@',text)
  text=re.sub(r'!\[([^]]+)\]\((figures/[^)]+)\)',lambda m:'!['+m[1]+'](figures/'+q+'-'+m[2].removeprefix('figures/')+')',text)
  text=re.sub(r'(!\[[^]]+\]\([^)]+\))\n(@@F_[^\n]+)',r'\1\n\n\2',text)
  if q=='q2':text=re.sub(r'\[([123])\]',lambda m:'['+str({1:1,2:1,3:2}[int(m[1])])+']',text)
  return text
 names=['问题重述','问题分析','模型假设','符号说明','模型建立','模型求解','结果分析','误差分析与模型检验','模型评价与推广','结论']
 out='# 板凳龙螺线盘入运动与首次接触分析\n\n## 摘要\n\n'
 for q in ['q1','q2']:out+='### '+('问题一' if q=='q1' else '问题二')+'\n\n'+protect(q,sections[q]['摘要'])+'\n\n'
 out+='## 关键词\n\n板凳龙；等距螺线；定长弦约束；弧长反解；分离轴定理；首次接触\n\n'
 for number,name in enumerate(names,1):
  out+=f'## {number} {name}\n\n'
  if name=='符号说明':out+='两部分沿用同一套螺线与运动学符号。角度统一记为 rad，角速度记为 rad/s；rad 为无量纲角度的惯用记法。$T_1=300$ s 仅为问题一观测终点，$t_*$ 为问题二首次非相邻接触时刻。把手索引为 $0,\\ldots,223$，板凳索引为 $0,\\ldots,222$；$g_{ij}$ 中的 $i,j$ 专指板凳索引。\n\n'
  for idx,q in enumerate(['q1','q2'],1):
   body=sections[q][name]
   if name=='符号说明':
    if q=='q2':
     rows=body.splitlines();new=[]
     for line in rows:
      if line.startswith('|'):
       cells=[c.strip() for c in line.strip('|').split('|')]
       if len(cells)==3:
        if cells[0]=='符号':cells=['符号','含义','单位']
        elif cells[0].startswith('---'):pass
        else:
         cells=[cells[0],cells[2],cells[1]]
         if cells[0] in ['$\\theta_i(t)$','$\\theta_{\\mathrm{init}}$']:cells[2]='rad'
         if cells[0]=='$\\omega_i$':cells[2]='rad/s'
         if cells[0]=='$r,\\delta$':cells[2]='m, rad'
        line='| '+' | '.join(cells)+' |'
      new.append(line)
     body='\n'.join(new)
    body='表0 '+('问题一符号与单位' if q=='q1' else '问题二符号与单位')+'\n\n'+body
   out+=f'### {number}.{idx} '+('问题一' if q=='q1' else '问题二')+'\n\n'+protect(q,body)+'\n\n'
 out+='## 参考文献\n\n[1] 2024年高教社杯全国大学生数学建模竞赛A题“板凳龙”题目及附件，问题一、问题二。用户提供的题面版本。\n\n[2] SciPy Developers. scipy.optimize.brentq. SciPy 1.15.3 Manual. https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.brentq.html 。采用已读取的本地文档版本。\n'
 mapping={'figures':{},'tables':{},'equations':{}}
 images=re.findall(r'!\[@@F_(q[12])_(\d+)@@ [^]]*\]\(([^)]+)\)',out);bypath={x['files']['png']['path']:x for x in figures}
 for number,(q,old,path) in enumerate(images,1):mapping['figures'][q+'_'+old]=number;bypath[path]['number']=number
 for number,(q,old) in enumerate(re.findall(r'^@@T_(q[12])_(\d+)@@\s+.+$',out,re.M),1):mapping['tables'][q+'_'+old]=number
 for kind,letter,label in [('figures','F','图'),('tables','T','表')]:
  for key,value in mapping[kind].items():out=out.replace('@@'+letter+'_'+key+'@@',label+str(value))
 assert '@@' not in out and len(images)==16
 cross='问题二沿用第5.1节的螺线、弧长反解与速度递推，螺线与弧长关系分别见式（1）—（5）和式（13）—（17），定长约束与速度关系分别见式（6）—（11）和式（18）—（25）；板凳尺寸与初始状态见图2、图3。第5.1节对300 s观测区间的半径认证不外推至首次接触时刻，问题二采用下述独立连续证书。\n\n'
 out=out.replace('### 5.2 问题二\n\n','### 5.2 问题二\n\n'+cross)
 edits.append({'question':'q2','kind':'explicit_cross_question_references','after':cross,'original_unchanged':True})
 counter=0
 def equation(m):
  nonlocal counter
  counter+=1;mapping['equations'][str(counter)]={'global':counter,'scope':'display equation in source order'}
  return '$$\n'+m[1].strip()+'\n\\tag{'+str(counter)+'}\n$$'
 out=re.sub(r'\$\$\s*([\s\S]*?)\s*\$\$',equation,out)
 catalog={'question_ids':['q1','q2'],'figures':sorted(figures,key=lambda f:f['number']),'evidence':{'frozen_input_manifest':(BASE/'input-freeze-manifest.json').relative_to(ROOT).as_posix(),'frozen_input_manifest_sha256':sha_file(BASE/'input-freeze-manifest.json'),'approved_generic_writer_sources':sources}}
 md=OUT/'单题论文-中文审阅稿.md';md.write_text(out,encoding='utf-8');save(OUT/'figure-catalog.json',catalog)
 check=validate_draft(md,OUT/'figure-catalog.json');assert check['status']=='passed',check['findings']
 auth={'user_statement':'进行统一符号、编号和跨题引用，再排版并进行独立 W2','scope':'User-authorized assembly/typesetting of two approved generic Writer inputs; no new combined manuscript approval inferred','frozen_input_manifest':str((BASE/'input-freeze-manifest.json').relative_to(ROOT)),'frozen_input_manifest_sha256':sha_file(BASE/'input-freeze-manifest.json'),'sources':sources,'combined_markdown_sha256':sha_file(md),'combined_catalog_sha256':sha_file(OUT/'figure-catalog.json'),'transformations':mapping,'editorial_adjustments':edits,'figure_count':16,'new_figures_generated':0,'new_solver_results':False,'W2':'pending'}
 save(OUT/'assembly-authorization.json',auth);save(OUT/'assembly-check.json',check);save(OUT/'symbol-reference-map.json',{'common_symbols':['p','b','t','v_0','N','theta_i','X_i','V_i','U_i'],'horizons':{'T_1':'Q1 sampling endpoint 300s','t_*':'Q2 first nonadjacent contact','T_origin':'analytic origin bound, not physical event'},'units':{'theta':'rad','omega':'rad/s'},'reference_mapping':{'q1':{'1':1,'2':2},'q2':{'1':1,'2':1,'3':2}},'numbering':mapping,'editorial_adjustments':edits})
 assert all(sha_file(BASE/x['snapshot'])==x['sha256'] for x in manifest['files'])
 print(json.dumps({'source':str(OUT.relative_to(ROOT)),'figures':16,'tables':len(mapping['tables']),'numbered_equations':counter,'mechanical':check['status'],'editorial_adjustments':len(edits)}))
if __name__=='__main__':main()
