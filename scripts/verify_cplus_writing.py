"""Replay C+ Chinese-paper checks without regenerating selected figures or approvals."""
from modelcrew.project_assets import asset_path
import argparse,json,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
import fitz
import numpy as np
from modelcrew.config import ROOT
from modelcrew.modeling_paper import writing_context,validate_draft,require_review_for_export,sha,inside
from modelcrew.writing_reviews import review_status


def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


def verify(source,output,qa_tools):
    context=writing_context();source=source.resolve();output=output.resolve()
    if output==source or output.is_relative_to(source):raise ValueError('Output must be separate from historical draft')
    output.mkdir(parents=True,exist_ok=False)
    before={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()}
    md_name='单题论文-中文审阅稿.md';catalog=json.loads((source/'figure-catalog.json').read_text(encoding='utf-8'))
    for name in (md_name,'figure-catalog.json','user-review.json','selected-results.csv','constraint-diagnostics.csv'):
        shutil.copyfile(source/name,output/name)
    for fig in catalog['figures']:
        for asset in fig['files'].values():
            src=inside(source,asset['path']);target=inside(output,asset['path']);target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copyfile(src,target)
    write(output/'writer-context.json',context)
    # Read the selected numerical section, not all seven algorithm documents.
    selected=asset_path(ROOT,'resources/algorithms/numerical-geometry.md')
    write(output/'selected-source-context.json',{'index_read_first':True,'path':str(selected.relative_to(ROOT)),'sha256':sha(selected),'text':selected.read_text(encoding='utf-8'),'purpose':'Review current geometry/root-method premises, not propose a new model.'})
    evidence=catalog['evidence'];data_path=inside(ROOT,evidence['path'])
    if sha(data_path)!=evidence['sha256']:raise ValueError('Historical trajectory hash changed')
    contract_path=asset_path(ROOT,'stage-b-plus/examples/contract-v2-snapshot.json');contract=json.loads(contract_path.read_text(encoding='utf-8'));pars={p['id']:p['value'] for p in contract['parameters']}
    with np.load(data_path,allow_pickle=False) as arrays:
        times=arrays['time_s'];positions=arrays['position_m'];velocity=arrays['velocity_m_s']
        if times.shape!=(301,) or positions.shape!=(301,224,2) or velocity.shape!=positions.shape:raise ValueError('Unexpected data shape')
        if not all(np.isfinite(a).all() for a in (times,positions,velocity)):raise ValueError('Nonfinite historical data')
        rods=np.diff(positions,axis=1);lengths=np.full(223,float(pars['body_gap']));lengths[0]=float(pars['head_gap'])
        rod=float(np.max(np.abs(np.linalg.norm(rods,axis=2)-lengths)))
        derivative=float(np.max(np.abs(np.einsum('tij,tij->ti',rods,np.diff(velocity,axis=1)))))
    tolerance=float(next(c['tolerance'] for c in contract['checks'] if c['id']=='rod_distance'))
    if rod>tolerance:raise ValueError('Historical rod tolerance failed')
    report=validate_draft(output/md_name,output/'figure-catalog.json');write(output/'paper-check.json',report)
    if report['status']!='passed':raise ValueError(str(report['findings']))
    review=json.loads((output/'user-review.json').read_text(encoding='utf-8'))
    if review.get('review_version')!='2.0.0':raise ValueError('Separate review bundle required')
    state=review_status(output/md_name,output/'figure-catalog.json',review.get('manuscript_review'),review.get('figure_selection_review'));write(output/'review-status.json',state)
    # The gate is actually called; no formatter/exporter is invoked in this replay.
    try:
        require_review_for_export(output/md_name,output/'figure-catalog.json',review)
        gate={'status':'eligible','export_executed':False}
    except ValueError as error:
        if state['can_export']:raise
        gate={'status':'blocked_as_required','reason':str(error),'export_executed':False}
    write(output/'export-gate-check.json',gate)
    audits=output/'qa';audits.mkdir();qa_summary=[]
    for fig in catalog['figures']:
        pdf=inside(output,fig['files']['pdf']['path']);paths={}
        for tool in ('audit_pdf_text.py','audit_figure_collisions.py'):
            args=[sys.executable,str(qa_tools/tool),str(pdf)]+(['--min-pt','5'] if tool=='audit_pdf_text.py' else [])+['--json']
            result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',timeout=60)
            target=audits/(fig['id']+'.'+tool.replace('.py','.json'));target.write_text(result.stdout,encoding='utf-8')
            (audits/(target.stem+'.stderr.log')).write_text(result.stderr,encoding='utf-8')
            if result.returncode:raise RuntimeError('Actual figure audit failed: '+fig['id']+'/'+tool)
            paths[tool]={'report':target.relative_to(output).as_posix(),'sha256':sha(target)}
        with fitz.open(pdf) as doc:
            if len(doc)!=1:raise ValueError('Expected one figure page')
            doc[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(audits/(fig['id']+'.png'))
        qa_summary.append({'figure_id':fig['id'],'checks':paths,'alignment':'Historical render-time evidence retained; no figure layout regenerated','visual_review':'pending'})
    write(output/'figure-qa.json',{'status':'automated_checks_passed','figures':qa_summary,'tool_hashes':{name:sha(qa_tools/name) for name in ('audit_pdf_text.py','audit_figure_collisions.py')}})
    lines=['# 当前配图清单与审阅状态','15 张图沿用用户已批准的选图及原字节；本次未重新批准。全部入文后的新版正文仍待审阅，正式导出被阻断。']
    by_category={'raw':'题目与模型输入','process':'求解与约束诊断','result':'结果分析'}
    for fig in catalog['figures']:
        n=fig['number'];lines += [f'## 图{n} {fig["title"]}',f'类别：{fig["category"]}；拟放章节：{by_category[fig["category"]]}。',fig['purpose'],f'![图{n} {fig["title"]}]({fig["files"]["png"]["path"]})']
    (output/'配图清单与审阅状态.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    after={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()}
    if before!=after:raise ValueError('Historical bundle changed')
    write(output/'verification-summary.json',{'verified_at':datetime.now(timezone.utc).isoformat(),'status':'automated_checks_passed_visual_review_pending','source_bundle':source.relative_to(ROOT).as_posix(),'source_file_hashes':before,'source_unchanged':True,'manuscript_byte_identical':sha(source/md_name)==sha(output/md_name),'catalog_byte_identical':sha(source/'figure-catalog.json')==sha(output/'figure-catalog.json'),'review_record_byte_identical':sha(source/'user-review.json')==sha(output/'user-review.json'),'review_state':state,'export_gate':gate,'paper_checks':report,'data':{'path':evidence['path'],'sha256':sha(data_path),'all_times':301,'all_rods':223,'max_rod_residual_m':rod,'rod_tolerance_m':tolerance,'max_derivative_residual_m2_per_s':derivative,'derivative_threshold':'not_defined_report_only'},'context_sha256':sha(output/'writer-context.json'),'script_sha256':sha(Path(__file__)),'new_llm_calls':0,'new_solver_runs':0,'new_user_approvals':0,'new_figures_generated':0,'paper_exported':False})
    print(json.dumps({'output':str(output),'checks':report['status'],'figures':len(catalog['figures']),'manuscript_review':state['manuscript'],'figure_selection':state['figure_selection'],'export_gate':gate['status']},ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--qa-tools',type=Path,required=True);args=p.parse_args();verify(args.source,args.output,args.qa_tools)
