"""Deterministic compilation of two separately approved papers; no new scientific prose."""
import json,re,shutil
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from modelcrew.modeling_paper import writing_context,require_review_for_export,validate_draft
from scripts.run_d4_full import workflow
BASE=ROOT/'stage-e/runs/q1-q2-20261109-v1'

def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    source=BASE/'source';source.mkdir(parents=True,exist_ok=False);(source/'figures').mkdir()
    context=writing_context();save(source/'writer-context.json',context)
    parts={};figures=[];sections={};audit=[];orig={}
    with workflow() as w:
        for q,pointer in [('q1','stage-d/d5/current-writing.json'),('q2','stage-d/q2-full/current-writing.json')]:
            current=wh.read(ROOT/pointer);folder=ROOT/current['run_dir'];status=wh.status(folder,w)
            if not status['state']['reviews']['can_export']:raise ValueError('Current separate source approvals required')
            check=require_review_for_export(folder/'单题论文-中文审阅稿.md',folder/'figure-catalog.json',wh.read(folder/'reviews.json'))
            orig[q]={'folder':wh.rel(folder),'markdown_sha256':check['markdown_sha256'],'catalog_sha256':check['catalog_sha256'],'reviews_sha256':wh.sha(folder/'reviews.json'),'binding':current['binding']}
            text=(folder/'单题论文-中文审阅稿.md').read_text(encoding='utf-8');parts[q]=text
            chunks=re.split(r'^##\s+(.+)\s*$',text,flags=re.M);sections[q]={}
            for i in range(1,len(chunks),2):
                heading=chunks[i].strip();name=re.sub(r'^(?:[一二三四五六七八九十]+、|\d+\s+)','',heading)
                sections[q][name]=chunks[i+1].strip()
            catalog=wh.read(folder/'figure-catalog.json')
            for f in catalog['figures']:
                if not f['formal']:continue
                new={**f,'id':q+'-'+f['id'],'question_ids':[q]};new['files']={}
                for fmt,asset in f['files'].items():
                    dst=source/'figures'/f'{q}-{f["id"]}.{fmt}';shutil.copyfile(folder/asset['path'],dst)
                    if wh.sha(dst)!=asset['sha256']:raise ValueError('Original figure bytes changed')
                    new['files'][fmt]={'path':dst.relative_to(source).as_posix(),'sha256':asset['sha256']}
                figures.append(new)
            md=source/(q+'-approved-original.md');shutil.copyfile(folder/'单题论文-中文审阅稿.md',md)
            for suffix in ['manuscript-review.json','figure-selection-review.json','reviews.json']:
                shutil.copyfile(folder/suffix,source/(q+'-'+suffix))
            if q=='q2':
                for extra in ['result2.xlsx','数值精度区间.json']:shutil.copyfile(folder/extra,source/extra)
            else:
                upstream=wh.read(folder/'run.json');shutil.copyfile(ROOT/upstream['source_run']/'output/result1.xlsx',source/'result1.xlsx')
    # Protect every old number with a source-scoped token, resolve only after global ordering.
    def protect(q,text):
        if q=='q2':
            text=text.replace('第一题图1','@@F_q1_1@@').replace('第一题图3','@@F_q1_3@@')
            text='表0 问题二主要符号与单位\n\n'+text if text.startswith('计算索引中') else text
        text=re.sub(r'图\s*(\d+)',lambda m:'@@F_'+q+'_'+m[1]+'@@',text)
        text=re.sub(r'表\s*(\d+)',lambda m:'@@T_'+q+'_'+m[1]+'@@',text)
        text=re.sub(r'\\tag\{(\d+)\}',lambda m:'\\tag{@@E_'+q+'_'+m[1]+'@@}',text)
        text=re.sub(r'式（(\d+)）—（(\d+)）',lambda m:'式（@@E_'+q+'_'+m[1]+'@@）—（@@E_'+q+'_'+m[2]+'@@）',text)
        text=re.sub(r'式（(\d+)）',lambda m:'式（@@E_'+q+'_'+m[1]+'@@）',text)
        text=re.sub(r'^###\s+\d+\.\d+\s+', '#### ',text,flags=re.M)
        # Scope words follow the now-combined manuscript, without changing any result.
        text=text.replace('本文','本部分')
        if '\times' in text:pass
        count=text.count('\times')
        text=text.replace('\times',r'\times') if False else text
        # The approved Q1 file contains literal TAB+'imes' from an old string escape.
        repaired=text.count('\t'+'imes');text=text.replace('\t'+'imes',r'\times')
        if repaired:audit.append({'question':q,'kind':'typesetting_escape_restoration','from':'TAB+imes','to':'backslash times','count':repaired,'original_file_unchanged':True})
        for f in wh.read(ROOT/orig[q]['folder']/'figure-catalog.json')['figures']:
            if f['formal']:text=text.replace(f['files']['png']['path'],f'figures/{q}-{f["id"]}.png')
        return text
    names=['问题重述','问题分析','模型假设','符号说明','模型建立','模型求解','结果分析','误差分析与模型检验','模型评价与推广','结论']
    out='# 板凳龙螺线盘入的位置速度与首次接触求解\n\n## 摘要\n\n'
    for q in ['q1','q2']:out+='### '+('问题一' if q=='q1' else '问题二')+'\n\n'+protect(q,sections[q]['摘要'])+'\n\n'
    out+='## 关键词\n\n板凳龙；阿基米德螺线；弧长反解；隐式微分；矩形外包络；首次接触\n\n'
    for n,name in enumerate(names,1):
        out+=f'## {n} {name}\n\n'
        for qi,q in enumerate(['q1','q2'],1):out+=f'### {n}.{qi} '+('问题一' if q=='q1' else '问题二')+'\n\n'+protect(q,sections[q][name])+'\n\n'
    out+='## 参考文献\n\n[1] 2024年高教社杯全国大学生数学建模竞赛A题“板凳龙”题面，问题一、问题二及附图表。用户提供的题面PDF。\n\n[2] SciPy Developers. scipy.optimize.brentq — SciPy v1.15.3 Manual. https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.brentq.html 。版本化官方文档的本地保存文本。\n\n'
    for name,body in sections['q2'].items():
        if name.startswith('附录'):out+='## '+name+'\n\n'+protect('q2',body)+'\n\n'
    maps={'figures':{},'tables':{},'equations':{}}
    # Actual image order determines the continuous global figure order.
    images=re.findall(r'!\[@@F_(q[12])_(\d+)@@ [^]]*\]\(([^)]+)\)',out)
    bypath={f['files']['png']['path']:f for f in figures}
    for n,(q,old,path) in enumerate(images,1):maps['figures'][q+'_'+old]=n;bypath[path]['number']=n
    caps=re.findall(r'^@@T_(q[12])_(\d+)@@\s+.+$',out,re.M)
    for n,(q,old) in enumerate(caps,1):maps['tables'][q+'_'+old]=n
    tags=re.findall(r'\\tag\{@@E_(q[12])_(\d+)@@\}',out)
    for n,(q,old) in enumerate(tags,1):maps['equations'][q+'_'+old]=n
    for kind,letter,label in [('figures','F','图'),('tables','T','表'),('equations','E','')]:
        for key,value in maps[kind].items():out=out.replace('@@'+letter+'_'+key+'@@',label+str(value))
    if '@@' in out:raise ValueError('Unresolved assembly number token')
    catalog={'question_ids':['q1','q2'],'figures':sorted(figures,key=lambda f:f['number']),'evidence':{'approved_parts':orig,'scope':'user authorized Q1+Q2 assembly only; no new solver results'}}
    save(source/'figure-catalog.json',catalog);md=source/'单题论文-中文审阅稿.md';md.write_text(out,encoding='utf-8')
    check=validate_draft(md,source/'figure-catalog.json')
    if check['status']!='passed':raise ValueError(check['findings'])
    auth={'user_statement':'建议q1和q2一起汇编排版','scope':'typeset previously approved Q1 and Q2 together, with mechanical section/figure/table/equation/reference renumbering; no new body approval inferred','sources':orig,'combined_markdown_sha256':wh.sha(md),'combined_catalog_sha256':wh.sha(source/'figure-catalog.json'),'transformations':maps,'format_repairs':audit,'figure_count':16,'no_new_figures':True,'new_scientific_claims':False,'source_approvals_remain_separate':True,'W2':'pending'}
    save(source/'assembly-authorization.json',auth);save(source/'assembly-check.json',check)
    save(BASE/'source-read-log.json',{'writer_context_sha256':wh.sha(source/'writer-context.json'),'sources':[{'path':p,'sha256':wh.sha(ROOT/p)} for p in ['AGENTS.md','resources/paper/workflow.json','resources/paper/writer-instructions.md','resources/paper/chinese-modeling-policy.json','docs/scientific-figure-contract.md','scripts/assemble_q1_q2.py']]})
    print(json.dumps({'source':wh.rel(source),'figures':len(images),'tables':len(caps),'equations':len(tags),'format_repairs':audit,'mechanical':check['status']},ensure_ascii=False))
if __name__=='__main__':main()
