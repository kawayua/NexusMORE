"""Freeze updated A+ evidence plan separately; never alter old approvals or drafts."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from modelcrew.config import ROOT
from modelcrew.modeling_paper import writing_context,sha,validate_draft
from modelcrew.evidence_planning import geometry_evidence,check_catalog,representative_times

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def build(output,bundle):
    if output.exists():raise ValueError('Refusing to overwrite an existing A+ evidence-planning bundle')
    context=writing_context()
    params_path=ROOT/'stage-a/2024-A-problem-1/parameters.json'
    params=json.loads(params_path.read_text(encoding='utf-8'))
    input_path=ROOT/'stage-a/2024-A-problem-1/input-manifest.json'
    inputs=json.loads(input_path.read_text(encoding='utf-8'))
    statement=next(i for i in inputs['files'] if i['role']=='problem_statement')
    if sha(statement['path'])!=statement['sha256']:raise ValueError('Original statement bytes changed')
    catalog_path=bundle/'figure-catalog.json';catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    evidence=catalog['evidence'];data_path=ROOT/evidence['path']
    if sha(data_path)!=evidence['sha256']:raise ValueError('Confirmed trajectory bytes changed')
    old_binding=json.loads((ROOT/'stage-a-plus/figure-evidence-plan.json').read_text(encoding='utf-8'))['evidence']
    if evidence!=old_binding:raise ValueError('Candidate data must retain the A+ historical execution binding')
    with np.load(data_path,allow_pickle=False) as d:geometry=geometry_evidence(params,d['time_s'],d['position_m'])
    consistency=check_catalog(geometry,catalog)
    if consistency['status']!='passed':raise ValueError(str(consistency['findings']))
    draft_path=bundle/'单题论文-中文审阅稿.md';review_path=bundle/'user-review.json'
    review=json.loads(review_path.read_text(encoding='utf-8'))
    if sha(draft_path)!=review['markdown_sha256']:raise ValueError('Previously approved manuscript bytes changed')
    checked=validate_draft(draft_path,catalog_path)
    if checked['status']!='passed':raise ValueError(str(checked['findings']))
    # Read-only comparison: existing approvals are evidence, never new approval actions.
    from modelcrew.workflow import Workflow
    with Workflow() as w,w.lock('dragon-q1'),w.db.transaction():
        w.db.execute('SET TRANSACTION READ ONLY')
        t=w.task('dragon-q1')
        contract=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=2',('dragon-q1',)).fetchone()
        result=w.db.execute('SELECT execution_id FROM mc_results WHERE task_id=%s AND version=2 AND revision=2',('dragon-q1',)).fetchone()
        if t['current_version']!=2 or t['result_revision']!=2 or not t['model_approved'] or not t['result_approved'] or str(result['execution_id'])!=evidence['execution_id']:raise ValueError('Existing confirmed result binding no longer current')
        production={'task_id':'dragon-q1','version':2,'result_revision':2,'execution_id':str(result['execution_id']),'contract_sha256':contract['sha256'],'model_approved':True,'result_approved':True,'inspection':'read_only'}
    sources=[params_path,input_path,Path(statement['path']),data_path,catalog_path,review_path,draft_path,
             ROOT/'resources/paper/workflow.json',ROOT/'resources/paper/chinese-modeling-policy.json',
             ROOT/'resources/algorithms/numerical-geometry.md',ROOT/'modelcrew/evidence_planning.py',ROOT/'scripts/prepare_aplus_evidence_plan.py']
    source_records=[{'path':str(p),'sha256':sha(p)} for p in sources]
    output.mkdir(parents=True,exist_ok=False)
    figures=[]
    for f in catalog['figures']:
        assets=[]
        for fmt,asset in f['files'].items():
            path=bundle/asset['path']
            if sha(path)!=asset['sha256']:raise ValueError('Candidate asset changed: '+f['id'])
            assets.append({'format':fmt,'path':str(path),'sha256':asset['sha256']})
        figures.append({'figure_id':f['id'],'category':f['category'],'question_ids':f['question_ids'],
            'question_or_purpose':f['purpose'],'time_s':f.get('time_s'),'existing_manuscript_uses_figure':f['formal'],
            'status':'existing_candidate_not_new_approval','source_kind':f['source_kind'],'assets':assets})
    plan={'plan_version':'2.0.0','date':'2026-11-07','stage':'A+','status':'implemented_and_verified',
          'supersedes_for_current_planning':'stage-a-plus/figure-evidence-plan.json; original file unchanged',
          'scope':'Updated A+ evidence planning only; reuse existing C+ candidate assets without regenerating, selecting or exporting.',
          'evidence':evidence,'production_read_only_recheck':production,'representative_times':representative_times('spiral_chain',params['report_times_s']),
          'geometry':geometry,'figure_contracts':figures,'catalog_consistency':consistency,
          'policy':context['workflow'],'cross_structure_control':representative_times('resource_allocation'),
          'handoff':{'B+':'Bind manuscript/selection decisions separately; do not infer approval from this plan.','C+':'Render/check planned views and report visual inspection; existing candidates are referenced, not newly generated.'},
          'new_model_calls':0,'new_solver_runs':0,'new_figures_generated':0,'source_records':source_records}
    write(output/'evidence-plan.json',plan);write(output/'writing-context.json',context)
    write(output/'verification.json',{'status':'passed','checks':{'original_statement_hash':True,'confirmed_npz_hash_and_result_binding':True,'all_time_geometry_dimensions':True,'six_exact_report_times':True,'shared_overview_bounds':True,'local_first_three_boards':True,'catalog_policy_and_assets':True,'unchanged_approved_manuscript':True,'other_structure_no_imposed_times':True},'catalog_check':consistency,'existing_paper_mechanical_check':checked,'source_records':source_records,'limits':['Metadata and geometry checks do not inspect image pixels or certify collisions.','No new manuscript/figure approval, model call, solver run or paper export.']})
    lines=['# A+ 配图证据规划增补（2026-11-07）','本次补齐更新后的A+要求，旧数学稿、验收、正文和入文图保持原字节。下面引用已有C+候选图，不生成或批准新图。',
    '## 时刻与证据问题','按题目report_times_s选取0、60、120、180、240、300 s。每幅总览回答该时刻223节板凳的平面形态；局部回答龙头及前两节龙身的长度、宽度、孔位如何随已确认中心点重建。时刻预先来自题目要求，不按视觉效果筛选。',
    '## 尺寸与重建边界','龙头板长3.41 m，其余2.20 m，宽0.30 m；孔中心距端0.275 m，孔径0.055 m；相邻孔中心距分别2.86/1.65 m。参数来自已保存题面提取，题面与参数哈希已核对；官方在线版本未新增核验。仅为刚性平面轮廓示意，不证明无碰撞、不量化净空、不做受力模拟。',
    '所有301个时刻、223节板凳均参与尺寸与总览范围检查，禁止只取六个时刻确定一个会裁切其他数据的范围。共享总览x/y范围为'+str(geometry['overview']['xlim_m'])+' m，等比例；局部均取板0、1、2，边界独立记录，局部图不用于比较不同时间的视觉大小。',
    '## 候选与交接','现有15张逻辑候选覆盖raw/process/result，每类至少3张；原稿暂选8幅不是新的最终选图批准。六张新增位置图仍未入文，两面板与三种文件格式均不重复计图数。',
    '| 时刻/s | 候选ID | 数据行 | 用途 |','|---:|---|---:|---|']
    for t,i in zip(geometry['report_times_s'],geometry['sample_indices']):lines.append(f'| {t} | result_q1_boards_t{int(t):03d} | {i} | 全局轮廓与前三节局部 |')
    lines+=['完整15张候选的用途、输入类型、资产位置及哈希见evidence-plan.json。现有预览：['+'六时刻轮廓总览]('+str(bundle/'新增位置图-总览.png').replace('\\','/')+')。',
    '其他题按科学问题规划视图，LP样例不加入这些时刻，也不伪造迭代曲线。正文审阅、选图确认与失效规则归B+，真实生成/视觉审查归C+；本次只核对现有图清单元数据和文件哈希，不声称重新审图。',
    '## 复核与限制','geometry maximum length error = '+str(geometry['maximum_length_error_m'])+' m；width error = '+str(geometry['maximum_width_error_m'])+' m。检查单位、尺寸、采样行、共享范围、候选覆盖及来源，图中最终字体/遮挡仍以C+视觉检查为准。新目录拒绝覆盖；来源和当前规范已归档。']
    (output/'README.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    write(output/'manifest.json',{'created_at':datetime.now(timezone.utc).isoformat(),'artifacts':{p.name:sha(p) for p in output.iterdir() if p.is_file()},'sources':source_records,'historical_records_modified':False})
    print(json.dumps({'status':'passed','output':str(output),'time_views':6,'candidate_contracts':len(figures),'geometry_error_m':geometry['maximum_length_error_m']},ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bundle',type=Path,default=ROOT/'output/md/modeling-q1-candidates-v3');args=parser.parse_args();build(args.output.resolve(),args.bundle.resolve())
