"""Apply the actual user's select-all decision; changed manuscript remains pending."""
import argparse,copy,json,re,shutil
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.modeling_paper import sha,validate_draft,writing_context,require_review_for_export
from modelcrew.writing_reviews import selection_record,selection_snapshot,review_status,write_record_new

STATEMENT='接下来推进B+  然后我选择每一种候选图 即每一张图都要出现'

def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def build(original,output):
    context=writing_context();original=original.resolve();output=output.resolve()
    if output.exists():raise ValueError('Refusing to overwrite manuscript/review bundle')
    checked=validate_draft(original/'单题论文-中文审阅稿.md',original/'figure-catalog.json')
    if checked['status']!='passed':raise ValueError(str(checked['findings']))
    catalog_path=original/'figure-catalog.json';catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    all_ids=[f['id'] for f in catalog['figures']]
    if len(all_ids)!=15:raise ValueError('This actual user selection refers to the current 15-figure candidate set')
    selection=selection_record(catalog_path,all_ids,decision='approve',actor='local-user',statement=STATEMENT,
        reason='用户明确要求当前每一张候选图都出现；绑定原15张图的内容与用途，不推断新正文通过。')
    old_review=json.loads((original/'user-review.json').read_text(encoding='utf-8'))
    if old_review['decision']!='approve' or old_review['markdown_sha256']!=checked['markdown_sha256']:raise ValueError('Previous manuscript approval snapshot mismatch')
    # Preserve old manuscript approval as historical evidence only. Never reapprove changed text.
    text=(original/'单题论文-中文审阅稿.md').read_text(encoding='utf-8')
    output.mkdir(parents=True,exist_ok=False);(output/'figures').mkdir()
    for f in catalog['figures']:
        for asset in f['files'].values():
            source=original/asset['path'];target=output/asset['path'];target.parent.mkdir(parents=True,exist_ok=True)
            if sha(source)!=asset['sha256']:raise ValueError('Source candidate changed')
            shutil.copyfile(source,target)
    for name in ['selected-results.csv','constraint-diagnostics.csv']:
        if (original/name).exists():shutil.copyfile(original/name,output/name)
    old_numbers={f['id']:f['number'] for f in catalog['figures'] if f['formal']}
    order=['raw_q1_spiral','raw_q1_lengths','raw_q1_dimensions','process_q1_branch',
           'result_q1_configuration']+[f'result_q1_boards_t{t:03d}' for t in [0,60,120,180,240,300]]+[
           'result_q1_speedmap','result_q1_speeds','process_q1_rod','process_q1_velocity']
    if set(order)!=set(all_ids):raise ValueError('Unexpected candidate IDs; review insertion mapping')
    by_id={f['id']:copy.deepcopy(f) for f in catalog['figures']}
    numbers={fid:i for i,fid in enumerate(order,1)}
    number_map={old:numbers[fid] for fid,old in old_numbers.items()}
    text=re.sub(r'图([0-9]+)(?![0-9])',lambda m:'图'+str(number_map[int(m[1])]),text)
    f=by_id['raw_q1_dimensions'];n=numbers[f['id']]
    dim=f'图{n}汇总题目输入尺寸，与前一幅孔距示意分别提供参数量级对照和几何定义。该图仅展示给定参数，不是独立实验测量。\n\n![图{n} {f["title"]}]({f["files"]["png"]["path"]})\n\n图{n} {f["title"]}。区分板长、孔距与螺距等不同含义的输入长度，单位为米。\n\n'
    anchor='### 2.3 模型和算法的选择';assert anchor in text;text=text.replace(anchor,dim+anchor,1)
    blocks=['### 7.2 六个指定时刻的板凳轮廓与局部细节',
        '为体现实物尺寸，在已确认的把手中心位置上重建刚性矩形轮廓：龙头板长3.41 m，其余板长2.20 m，板宽0.30 m；孔中心距板端0.275 m，孔径0.055 m。下列六图采用题目指定时刻，左侧总览使用同一坐标尺度，右侧放大龙头及前两节龙身。图中宽度仅用于示意，不改变前述中心点运动学模型；各时刻局部范围可不同，不能通过局部显示大小判断相对尺度。']
    for t in [0,60,120,180,240,300]:
        f=by_id[f'result_q1_boards_t{t:03d}'];n=numbers[f['id']]
        blocks += [f'图{n}展示{t} s时的全部223节板凳及前三节局部。'+('该时刻为初始状态，用于核对螺线方向和初始位置。' if t==0 else ('该时刻为输出区间终态，可与表中300 s结果对应。' if t==300 else '该中间状态与前后时刻共同说明给定输出采样下的盘入形态。')),
            f'![图{n} {f["title"]}]({f["files"]["png"]["path"]})',
            f'图{n} {f["title"]}。左：全部板凳的统一尺度总览；右：龙头及前两节龙身局部。位置来自未舍入结果，轮廓采用题面尺寸；为平面几何重建，不构成碰撞或净空验证。']
    anchor='### 7.2 速度传递特征';assert anchor in text;text=text.replace(anchor,'\n\n'.join(blocks)+'\n\n### 7.3 速度传递特征',1)
    for fid in order:
        f=by_id[fid];f.update(formal=True,number=numbers[fid],selection_status='selected_by_explicit_user')
    catalog['figures']=[by_id[fid] for fid in order];catalog['selection_status']='all_15_selected_by_user_new_manuscript_pending'
    write(output/'figure-catalog.json',catalog)
    md=output/'单题论文-中文审阅稿.md';md.write_text(text,encoding='utf-8')
    # New numbers and paths do not change the chosen figure content.
    new_snapshot=selection_snapshot(output/'figure-catalog.json',all_ids)
    if new_snapshot['sha256']!=selection['snapshot']['sha256']:raise ValueError('Selected content changed while applying choice')
    write_record_new(output/'figure-selection-review.json',selection)
    write(output/'previous-manuscript-review.json',{'source_path':str(original/'user-review.json'),'source_sha256':sha(original/'user-review.json'),'record':old_review,'scope':'Historical original manuscript approval; never applied to modified manuscript.'})
    review={'review_version':'2.0.0','manuscript_review':None,'figure_selection_review':selection,
            'note':'全部选图已由用户明确批准；补入图片和说明后的新正文尚未确认。'}
    write(output/'user-review.json',review);write(output/'writer-context.json',context)
    state=review_status(md,output/'figure-catalog.json',None,selection);write(output/'review-status.json',state)
    report=validate_draft(md,output/'figure-catalog.json');write(output/'paper-check.json',report)
    if report['status']!='passed':raise ValueError(str(report['findings']))
    try:require_review_for_export(md,output/'figure-catalog.json',review)
    except ValueError as exc:write(output/'export-gate-check.json',{'status':'correctly_blocked','reason':str(exc),'manuscript':'pending','figure_selection':'approved'})
    else:raise AssertionError('New manuscript must not be implicitly approved')
    mapping=[{'id':fid,'old_number':old_numbers.get(fid),'new_number':numbers[fid],'png':by_id[fid]['files']['png']['path']} for fid in order]
    write(output/'figure-number-map.json',mapping)
    (output/'变更与审阅说明.md').write_text('# 全部15图入文的新版审阅说明\n\n已按用户原话记录全部选图批准，15张图均已嵌入中文正文并连续编号。图片文件与数值结果未改；只调整图号、正文引用，并新增尺寸对照图及六时刻轮廓图说明。原稿及原正文批准文件保留。\n\n当前状态：选图已确认；新版正文待审阅。原有“正文通过”只适用于旧稿，不能自动批准这次增加的段落、题注与图号。可先查看[新版中文正文](单题论文-中文审阅稿.md)。\n\n正式排版仍被阻断；本次未生成论文PDF/Word，未调用模型或重算题目。文件级审批已实现，数据库/API写作审批及状态图写作等待节点未在本轮接入。\n',encoding='utf-8')
    write(output/'build-manifest.json',{'date':'2026-11-07','source_bundle':str(original),'source_markdown_sha256':checked['markdown_sha256'],'new_markdown_sha256':sha(md),'source_catalog_sha256':sha(catalog_path),'new_catalog_sha256':sha(output/'figure-catalog.json'),'selected_figures':15,'source_selection_sha256':selection['snapshot']['sha256'],'script_sha256':sha(__file__),'new_llm_calls':0,'new_solver_runs':0,'new_figures_generated':0,'paper_exported':False,'review_status':state,'source_record_hashes':{str(original/name):sha(original/name) for name in ['单题论文-中文审阅稿.md','figure-catalog.json','user-review.json']}})
    print(json.dumps({'output':str(output),'checks':report['status'],'figures':15,'manuscript':state['manuscript'],'selection':state['figure_selection'],'can_export':state['can_export']},ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--original',type=Path,default=ROOT/'output/md/modeling-q1-candidates-v3');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();build(args.original,args.output)
