"""Human-readable model reviews projected from existing contracts and M1 prose."""
import hashlib
from pathlib import Path
import re

from .business_contract import BusinessContractError

RENDERER_VERSION = 'readable-model/1'


def proposal_sources(review, root):
    """Select the latest passing prose for this version, never another version."""
    version=review['pending']['binding']['version']
    runs=[r for r in review['dossier'].get('modeling_runs',[]) if r.get('version')==version]
    if not runs: return []
    attempts=runs[-1].get('payload',{}).get('attempts',[])
    passing=[a for a in attempts if a.get('status')=='PASS' and a.get('proposal_path')]
    if not passing: return []
    path=Path(root)/passing[-1]['proposal_path']
    resolved=path.resolve();base=Path(root).resolve()
    if not resolved.is_relative_to(base):
        raise BusinessContractError('artifact_access_denied','Model review source is outside workspace')
    for part in (path,*path.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise BusinessContractError('artifact_access_denied','Linked model review source')
    data=resolved.read_bytes()
    return [{'path':resolved.relative_to(base).as_posix(),
             'sha256':hashlib.sha256(data).hexdigest(),'text':data.decode('utf-8-sig')}]


def _cell(value):
    return str(value).replace('|',r'\|').replace('\r',' ').replace('\n',' ')


def _table(headers, rows):
    return ['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |',
            *['| '+' | '.join(_cell(v) for v in row)+' |' for row in rows],'']


def _prose(text):
    # Administrative self-reports and the figure plan are retained verbatim in
    # evidence; the latter is rendered from the frozen figure specifications.
    text=text.replace('\r\n','\n').replace('\r','')
    sections=re.split(r'(?=^## )',text,flags=re.M)
    sections=[s for s in sections if not re.match(r'## [^\n]*(?:questions|不造不批|图件计划|方法取舍)',s,re.I)]
    text='\n'.join(sections).strip()
    text=re.sub(r'\b(?:eq|chk|fig|prop|cand):[A-Za-z0-9_-]+\b','',text)
    text=re.sub(r'[（(][、，,\s]*[）)]','',text)
    text=text.replace('checks','下文检查计划')
    return re.sub(r'^## ', '### ',text,flags=re.M)


def render_model(review, root, sources=None):
    """Display meaning first; all unabridged evidence is stored separately."""
    item=review['pending'];d=review['dossier'];c=d['contract']['content']
    p=(d.get('mathematics') or {}).get('content') or {}
    sources=proposal_sources(review,root) if sources is None else sources
    problem=c.get('problem',{});method=p.get('method_selection',{})
    lines=['# 建模方案待审稿','',problem.get('title','建模方案'),'',
           '业务版本：v'+str(item['binding']['version'])+'。本稿等待你的审核。','',
           '本次请审核建模假设、边界条件、求解方法、检验安排和输出口径。回复“通过”可确认当前方案，也可以直接提出修改意见。模型确认不等于结果、论文正文或配图确认。','',
           '## 要解决什么问题','',problem.get('scope',''),'',
           problem.get('objective',{}).get('description',''),'']
    selected=next((v for v in method.get('candidates',[]) if v.get('decision')=='selected'),None)
    lines+=['## 建模思路与求解方案','']
    if method.get('model'): lines += ['采用的模型：'+method['model'],'']
    if method.get('solver'): lines += ['求解方法：'+method['solver'],'']
    if selected: lines += ['选择依据：'+selected.get('reason',''),'']
    if sources:
        lines += [_prose(sources[0]['text']),'']
    else:
        lines += ['以下按当前契约说明求解安排；当前快照没有可引用的建模说明正文，不补造推导或计算结果。','']
        lines += [f'{i}. {step}' for i,step in enumerate(c.get('method',{}).get('steps',[]),1)]+['']
        for constraint in c.get('constraints',[]):
            lines += [constraint.get('meaning','')+'：'+constraint.get('expression',''),'']
    lines += ['### 模型假设','',*[f'- {a["statement"]}' for a in c.get('assumptions',[])],'']
    if c.get('parameters'):
        lines += ['### 参数与单位','']+_table(['参数','取值','单位','依据'],[
            [a['id'].removeprefix('P_'),a['value'],a['unit'],a.get('derivation') or {'given':'题目给定','assumption':'本方案设置，待审阅','derived':'由给定量推导'}.get(a.get('origin'),'见配套证据')]
            for a in c['parameters']])
    lines += ['### 检查计划','','以下是拟执行的检查及验收要求，列出计划不表示已经通过。','']
    lines += _table(['检查内容','实施方式','验收要求'],[
        [v['description'],v['method'],
         '量化报告，不设固定阈值' if v.get('tolerance') is None else '容差 '+str(v['tolerance'])+' '+v.get('unit','')]
        for v in c.get('checks',[])])
    if p.get('figures'):
        lines += ['## 候选图计划','','这些图件仍是计划，未表示已经生成或被选入正文。','']
        lines += _table(['图件要回答的问题','数据依据','展示安排'],[
            [v.get('question',''),v.get('data_origin',''),v.get('specification','')]
            for v in p['figures']])
    lines += ['## 交付内容与输出口径','']
    for output in c.get('outputs',[]):
        fields='；'.join(f'{v["name"]}（单位 {v["unit"]}，尺寸 '+ ' × '.join(map(str,v['shape']))+'）' for v in output.get('fields',[]))
        precision=output.get('decimal_places')
        lines += ['- '+Path(output['path']).name+'：'+fields+('；保留 '+str(precision)+' 位小数。' if precision is not None else '。')]
    lines += ['',c.get('conventions',{}).get('indexing',''),'']
    if c.get('risks'):
        lines += ['## 局限与需要留意的地方','',*[f'- {v}' for v in c['risks']],'']
    lines += ['## 本次确认范围','',
              '请核对以上模型、假设、参数、数值方案、输出口径和检验要求。方案中的“冻结”指当前版本已登记，不表示你已经批准；拟执行的检查和图件也不代表已完成。','',
              '完整契约、数学包、输入结构、检查阈值、来源原文和审计记录保存在配套证据附件中。','']
    return '建模方案待审稿','\n'.join(lines),sources
