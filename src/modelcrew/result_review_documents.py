"""Chinese result approval views, derived only from hash-verified registered outputs."""
import hashlib,json,math
from pathlib import Path,PurePosixPath
from urllib.parse import quote
from .business_contract import BusinessContractError
from .review_documents import _table

RESULT_RENDERER_VERSION='readable-result/1'


def checked_bytes(root,ref):
    base=Path(root).resolve();path=Path(ref['path']);path=path if path.is_absolute() else base/path
    resolved=path.resolve()
    if not resolved.is_relative_to(base):raise BusinessContractError('artifact_access_denied','Result source outside workspace')
    for part in (path,*path.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise BusinessContractError('artifact_access_denied','Linked result source')
    if path.stat().st_size>16*1024*1024:raise BusinessContractError('artifact_access_denied','Result source too large')
    data=resolved.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ref['sha256']:
        raise BusinessContractError('artifact_changed','Result source bytes changed')
    return data


def result_context(w,task,execution):
    """Supplement the trusted review with logical names and actual accepted QA."""
    from . import hand_runtime as hr
    run=execution.get('run_id')
    if not run:return None
    row=hr.verify_result(w,task,str(run));p=row['payload']
    if p['binding']['execution_id']!=str(execution['id']):raise BusinessContractError('stale_binding','Result execution differs')
    registered={a['sha256']:a for a in execution['artifacts']}
    packet=hr.read(hr.workspace_path(hr.ROOT,p['full_packet']));sources=[]
    for a in packet['artifacts']:
        if a['sha256'] not in registered:raise BusinessContractError('artifact_changed','Unregistered result output')
        item=registered[a['sha256']]
        sources.append({'name':a['path'].split('/artifacts/',1)[1],'path':Path(item['path']).as_posix(),
                        'sha256':a['sha256'],'role':'output'})
    p2=p['reviews'][p['accepted_reviews']['P2']]
    receipt=hr.run_folder(row)/'records/Receipt'/(p2['receipt_sha256']+'.json')
    sources.append({'name':'independent-p2.json','path':hr.rel(receipt),'sha256':hr.sha_file(receipt),'role':'review'})
    visual=p.get('visual_reviews',{}).get(p['accepted_reviews']['P2'])
    if visual:sources.append({'name':'independent-visual.json','path':visual['path'],'sha256':visual['sha256'],'role':'review'})
    accepted=p.get('error_acceptance_addendum')
    if accepted:sources.append({'name':'user-accepted-deviations.json','path':accepted['path'],'sha256':accepted['sha256'],'role':'decision'})
    return {'protocol':'result-review-sources/1.0.0','binding':p['binding'],'sources':sources,
            'independent_P2':p2,'artifact_count':len(packet['artifacts'])}


def result_sources(review,root):
    context=review['dossier'].get('result_review_evidence') or {}
    sources=context.get('sources',[])
    result=[]
    for item in sources:
        name=item['name'];pure=PurePosixPath(name)
        if pure.is_absolute() or '\\' in name or ':' in name or '..' in pure.parts:
            raise BusinessContractError('artifact_access_denied','Unsafe logical result filename')
        data=checked_bytes(root,item)
        result.append({**item,'bytes':len(data)})
    return result


def source_objects(sources,root):
    return {s['name']:json.loads(checked_bytes(root,s).decode('utf-8-sig')) for s in sources if s['name'].endswith('.json')}


def _number(value,places=4):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise BusinessContractError('artifact_changed','Result table contains invalid numeric value')
    return f'{value:.{places}f}'


def render_result(review,root,sources=None,urls=None):
    sources=result_sources(review,root) if sources is None else sources;urls=urls or {}
    objects=source_objects(sources,root);d=review['dossier'];bound=review['pending']['binding'];c=(d.get('contract') or {}).get('content') or {}
    result=objects.get('result.json') or {};tables=result.get('tables') or {};catalog=objects.get('figure-catalog.json') or {}
    binding=result.get('binding')
    if binding:
        for key,other in [('task_id','task_id'),('contract_version','version'),('contract_sha256','contract_sha256'),('execution_id','execution_id'),('result_revision','result_revision')]:
            if binding.get(key)!=bound.get(other):raise BusinessContractError('stale_binding','Displayed result binding differs')
    title='计算结果待审稿';lines=['# '+title,'',f'业务版本 v{bound.get("version","")} · 结果第 {bound.get("result_revision",(d.get("result") or {}).get("revision",""))} 版 · 等待你的确认','',
        '**这次请确认计算结果及其已披露误差是否可用于后续论文。** 回复“通过”只确认这份结果；论文正文、最终选图和正式导出仍需分别确认。','']
    scope=c.get('problem',{}).get('scope','')
    lines+=['## 本次算了什么','']
    if scope:lines+=[scope,'']
    config=result.get('config') or {};history=result.get('histories') or {}
    if config.get('duration_s') is not None:
        lines += [f'计算覆盖 {_number(config.get("start_time_s",0),0)}—{_number(config["duration_s"]+config.get("start_time_s",0),0)} 秒；时间步长 {_number(config["dt_s"],1)} 秒。', '']
    if 'z_m' in history:lines += [f'以下表格对应轴向位置 z = {_number(history["z_m"],2)} m；本题 z = 0 表示药材长度方向的中间截面，不代表整根药材处处相同。','']
    if config.get('Nr_nodes') and config.get('Nz_nodes'):
        lines+=['模型同时考虑径向和轴向的传热、水分扩散及暴露表面的交换；这里展示已确认方案的计算结果，不要求你重新批准建模方案。','']
    lines += ['这些是模型预测值，并非药材内部实测数据。保留四位小数是输出格式，不等于已证明误差小于万分之一。','']
    temp=tables.get('table1_temperature');moist=tables.get('table2_moisture')
    if temp and moist and 1800 in temp['times_s'] and 1800 in moist['times_s']:
        t=temp['values'][temp['times_s'].index(1800)];m=moist['values'][moist['times_s'].index(1800)]
        lines += ['## 先看主要结果','',f'在 1800 秒（30 分钟）时，报告截面的中心温度为 **{_number(t[0])} ℃**，表面温度为 **{_number(t[-1])} ℃**；中心干基含水率为 **{_number(m[0])} kg/kg**，表面为 **{_number(m[-1])} kg/kg**。','']
        if t[-1]>t[0] and m[-1]<m[0]:
            lines += ['这组结果呈现出表层先升温、先失水，中心响应较慢的分布。中心含水率在四位小数下接近初值，不能据此断言完全没有水分迁移，也不能把表层情况当成整根药材的均匀状态。','']
    for key,heading,unit in [('table1_temperature','指定时刻的温度','℃'),('table2_moisture','指定时刻的干基含水率','kg 水/kg 干物质')]:
        table=tables.get(key)
        if not table:continue
        times=table['times_s'];radii=table['radii_cm'];values=table['values']
        if len(times)!=len(values) or any(len(v)!=len(radii) for v in values):raise BusinessContractError('artifact_changed','Result table shape differs')
        lines+=['## '+heading,'','单位：'+unit+'。列标题为到中心的径向距离；行标题为时间。','']
        lines+=_table(['时间 / 秒',*[f'{float(r):g} cm' for r in radii]],[[str(t),*[_number(v) for v in row]] for t,row in zip(times,values)])
    if not tables:
        lines+=['## 结果说明','',(d.get('result') or {}).get('interpretation') or '当前记录没有可直接展示的结果说明。','',
            '当前审阅材料没有可读取的结构化结果表，不能仅凭“执行成功”或文件哈希推断具体数值。请补齐已登记结果的可读数据后再确认。','']
    accepted=objects.get('user-accepted-deviations.json') or {};deviations=accepted.get('accepted_checks',{})
    failed=[v for v in result.get('checks',[]) if v.get('status')=='FAIL']
    lines+=['## 误差与检查：哪些通过，哪些由你接受','']
    if deviations:
        rows=[]
        if 'chk_dt' in deviations:
            check=deviations['chk_dt'];value=check['value']['dt21']['C']
            rows.append(['含水率时间步对照',f'最大差不超过 {check["tolerance"]} kg/kg',f'全时段最大差 {value["maximum_all_times"]:.8f} kg/kg；共同偶数时刻 {value["maximum_common_even_times"]:.8f} kg/kg','未达到原要求；你已接受本次已披露偏差'])
        if 'chk_analytic2d' in deviations:
            check=deviations['chk_analytic2d'];value=check['value']['maximum']
            rows.append(['二维解析验证',f'相对误差不超过 {check["tolerance"]*100:g}%',f'本次最大约 {value*100:.5f}%','未达到原要求；你已接受本次已披露偏差'])
        lines+=_table(['检查','原验收要求','本次实测','处置'],rows)
        lines+=['上述两项是项目自行设置的数值验证要求，不是题面明文规定；接受记录限定于这次已披露的结果。它们在原始检查中仍保留“未通过”，没有被改写成原精度已达标。','']
    for item in failed:
        if item['id'] not in deviations:lines += ['**仍需处理的未通过检查：** '+item['id']+'。当前材料没有显示你接受了这一项，不能按已接受处理。','']
    p2=objects.get('independent-p2.json') or {};labels={'execution':'全量程序真实运行','contract_implementation':'约定输出与实现','error':'误差与已接受偏差的处置','reproduction':'独立复跑逐文件一致','figure_meaning':'独立审图与图件意义'}
    if p2.get('checks'):
        lines+=_table(['独立检查','结论'],[[labels.get(v['check_id'],'其他检查'),{'PASS':'通过','FAIL':'未通过','BLOCKED':'待补证据'}.get(v['status'],v['status'])] for v in p2['checks']])
    visual=objects.get('independent-visual.json') or {}
    if visual.get('status')=='PASS':lines += [f'独立视觉审查实际接收并审阅了 **{visual["page_count"]} 页图像**，每页均有观察记录；这不同于只做机械检查或只由作者自检。','']
    figures=catalog.get('figures') or []
    preferred=['fig:res-profiles','fig:res-temp-field','fig:res-moist-field']
    shown=[]
    for figure_id in preferred:
        fig=next((v for v in figures if v['id']==figure_id),None)
        if not fig:continue
        png=fig['files']['png']['path'];link=urls.get(png)
        if link:
            if not shown:lines+=['## 结果图预览','','以下只是帮助理解结果的候选图预览，不表示你已选定论文配图。','']
            caption=fig.get('title',figure_id).replace(']','）').replace('[','（');lines += ['### '+caption,'',f'![{caption}]({link})',''];shown.append(figure_id)
    lines+=['## 完整文件与其余候选图','']
    display={'outputs/result1.xlsx':('完整 Excel：两张表，每张 '+str(history['nsteps'])+' × '+str(history['columns'])+' 个数据（不含表头与时间列）') if history.get('nsteps') and history.get('columns') else '完整 Excel 结果文件','outputs/table1_temperature.csv':'温度汇总表（CSV）','outputs/table2_moisture.csv':'含水率汇总表（CSV）','outputs/axial_profiles.csv':'轴向剖面数据（CSV）','outputs/diagnostics.json':'完整数值检查数据（技术附件）'}
    for name,label in display.items():
        if name in urls:lines += ['- ['+label+']('+urls[name]+')']
    lines+=['']
    rows=[]
    for fig in figures:
        links=[]
        for fmt in ['png','pdf','svg']:
            name=fig['files'][fmt]['path']
            if name in urls:links.append('['+fmt.upper()+']('+urls[name]+')')
        rows.append([fig.get('title','候选图'),{'raw':'输入与几何','process':'过程与校核','result':'结果'}.get(fig.get('category'),'候选'),' / '.join(links)])
    if rows:lines+=_table(['候选图','类别','查看或下载'],rows)
    risks=c.get('risks',[])
    if risks:
        lines+=['## 适用范围与局限','',*[ '- '+str(v).replace('A8 的','') for v in risks],'']
    lines+=['## 这次需要你确认什么','','请确认这些计算结果、表格和已披露的误差/局限，是否可以作为后续论文的结果依据。你也可以直接提出需要修改或补充的地方。','',
            '回复“通过”只确认当前结果及其版本；不代表已确认论文正文、最终配图或正式导出。完整数据、来源和独立审查记录保存在配套证据附件中。','']
    return title,'\n'.join(lines),sources
