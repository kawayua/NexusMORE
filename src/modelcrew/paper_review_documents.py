"""Combined paper review and actual candidate-image gallery, with immutable sources."""
import json,re
from pathlib import Path
from .business_contract import BusinessContractError
from .result_review_documents import checked_bytes

RENDERER_VERSION='readable-paper-bundle/1'


def sources(review,root):
    context=review['dossier'].get('writing_review_context') or {};item=review['pending']
    if item.get('confirmation_scope')!='manuscript_and_figures':raise BusinessContractError('invalid_request','Combined paper scope required')
    md=context.get('manuscript');catalog_ref=context.get('catalog');outline=context.get('outline')
    if not md or not catalog_ref:raise BusinessContractError('artifact_changed','Readable manuscript and catalog required')
    if {'manuscript_sha256':md['sha256'],'figure_catalog_sha256':catalog_ref['sha256']}!=item['components']:
        raise BusinessContractError('stale_binding','Combined component versions differ')
    rows=[{**md,'name':'manuscript.md','role':'manuscript'},{**catalog_ref,'name':'figure-catalog.json','role':'catalog'}]
    if outline:rows.append({**outline,'name':'outline.json','role':'outline'})
    catalog=json.loads(checked_bytes(root,catalog_ref));base=(Path(root)/catalog_ref['path']).parent
    expected=item['binding'];b=catalog.get('evidence',{})
    for left,right in ([] if item['decision_operation']=='assembly_decide' else [('task_id','task_id'),('contract_version','version'),('execution_id','execution_id'),('result_revision','result_revision')]):
        if b.get(left)!=expected.get(right):raise BusinessContractError('stale_binding','Gallery belongs to another result')
    if item['decision_operation']=='assembly_decide' and (context.get('assembly_id')!=expected.get('build_id') or b!=context.get('catalog_evidence')):raise BusinessContractError('stale_binding','Gallery belongs to another assembly')
    registered={str(Path(f['local_path']).resolve()):f['sha256'] for f in review.get('review_files',[])}
    for index,fig in enumerate(catalog['figures'],1):
        for fmt in ('png','pdf','svg'):
            asset=fig['files'][fmt];path=(base/asset['path']).resolve()
            if registered.get(str(path))!=asset['sha256']:raise BusinessContractError('artifact_access_denied','Gallery asset is not registered for this review')
            rows.append({'path':str(path),'sha256':asset['sha256'],'name':f'figures/figure-{index:03}.{fmt}',
                         'role':'image','figure_id':fig['id'],'format':fmt,'source_link':asset['path']})
    result=[]
    for row in rows:result.append({**row,'bytes':len(checked_bytes(root,row))})
    return result


def render(review,root,source_refs,urls):
    values={s['name']:checked_bytes(root,s) for s in source_refs if s['role']!='image'}
    manuscript=values['manuscript.md'].decode('utf-8-sig');catalog=json.loads(values['figure-catalog.json']);outline=json.loads(values.get('outline.json',b'{}'))
    bylink={s['source_link']:urls[s['name']] for s in source_refs if s['role']=='image'}
    def image_link(match):
        if match[2] not in bylink:raise BusinessContractError('artifact_changed','Manuscript image is outside the displayed gallery')
        return '!['+match[1]+']('+bylink[match[2]]+')'
    manuscript=re.sub(r'!\[([^]]*)\]\(([^)]+)\)',image_link,manuscript)
    manuscript=re.sub(r'^(#{1,4}) ',lambda m:'#'*min(6,len(m[1])+2)+' ',manuscript,flags=re.M)
    formal=sum(bool(fig['formal']) for fig in catalog['figures']);mapping={f['figure_id']:f['section'] for f in outline.get('figure_plan',[])}
    title='论文正文与配图合并待审稿';bound=review['pending']['binding']
    version_text=f'模型版本 v{bound["version"]} · 结果版本 {bound["result_revision"]} · 尚未确认' if 'version' in bound else '汇编稿 · 尚未确认'
    lines=['# '+title,'',version_text,'',
       f'本页把当前正文与全部 **{len(catalog["figures"])} 组候选图**放在一起，其中 **{formal} 幅暂列正文**，其余为备选。','',
       '**看完后在原对话回复“通过”或“确认”，一次同时确认当前正文和当前暂列入文配图。** 如果要增删、替换图或修改正文，请直接指出，更新合并稿后再确认。','',
       '本次确认绑定这两份内容的具体版本；任一份变更都不能沿用旧确认。它不表示最终导出的排版已经通过检查。','',
       '## 论文正文','',manuscript,'','## 带图的候选清单','',
       '下面每张图都可直接查看；同图在正文与此处重复展示只是方便审阅，不重复计入图件数量。','']
    for i,fig in enumerate(catalog['figures'],1):
        line=next(s for s in source_refs if s.get('figure_id')==fig['id'] and s.get('format')=='png')
        name=fig['title'].replace('[','（').replace(']','）');arrangement='暂列正文图'+str(fig['number']) if fig['formal'] else '备选，当前不入文'
        lines += [f'### 候选图 {i}：{name}','',arrangement+'；类别：'+{'raw':'输入与几何','process':'过程与校核','result':'结果'}.get(fig['category'],'候选')+'。','',
          '用途：'+fig.get('purpose',fig.get('figure_contract',{}).get('claim_or_question','见正文解释')),'',
          '拟放章节：'+mapping.get(fig['id'],'见正文中的实际图号与引用' if fig['formal'] else '备选资料，尚未安排入文'),'','!['+name+']('+urls[line['name']]+')','',
          ' / '.join('['+fmt.upper()+']('+urls[next(s['name'] for s in source_refs if s.get('figure_id')==fig['id'] and s.get('format')==fmt)]+')' for fmt in ('png','pdf','svg')),'']
    lines += ['## 本次确认范围','','一次确认同时记录正文批准和当前暂列配图批准，两个版本都核对一致后才生效；不会只批准一半。最终正式文件还需编译、全页检查及独立终检。','']
    return title,'\n'.join(lines)
