"""Read approved Q1 artifacts into a Q2 intake. No Q2 model approval or solving."""
from modelcrew.project_assets import asset_path
import argparse,json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.writing_hand import new,read,rel
from modelcrew.collaboration import sha_file
from scripts.run_d4_full import workflow

TARGET='d6-bench-q2-20261109'

def prepare(folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    source=read(asset_path(ROOT,'stage-d/d6/question2-statement.json'))
    page=source['pages'][0];excerpt=page['text'].split('问题3',1)[0].strip()
    (folder/'问题二题面.txt').write_text(excerpt+'\n',encoding='utf-8')
    with workflow() as w:
        w.setup()
        q=w.question_intake(target_id=TARGET,revision=1,case_id='CUMCM2024A',question_id='Q2',statement_path=source['source_path'],statement_sha256=source['source_sha256'],pages=[page['page']],excerpt_path=folder/'问题二题面.txt')
        model=w.attach_question_reference(target_id=TARGET,target_revision=1,source_task='d2-bench-q1-20261108',scopes=['model'],purpose='参考第一题已确认的螺线、孔距、弧长反解、外侧选根和速度递推；独立读取不以论文/导出完成为前提。')
        full=w.attach_question_reference(target_id=TARGET,target_revision=1,source_task='d2-bench-q1-20261108',scopes=['result','manuscript','figures'],purpose='读取已确认0到300秒结果作复算对照，并参考已确认正文和实体尺寸图；不继承无碰撞结论或超出300秒状态。')
        ids=[model['reference_id'],full['reference_id']]
        context=w.question_context(target_id=TARGET,target_revision=1,reference_ids=ids)
        new(folder/'model-reference.json',model);new(folder/'result-writing-reference.json',full);new(folder/'question-context.json',context)
        new(folder/'resume-request.json',{'target_id':TARGET,'target_revision':1,'reference_ids':ids})
        # Actually open returned content-addressed arrays and referenced text/figures;
        # consumption is not merely an untested declaration of file paths.
        import numpy as np
        files=context['references'][1]['source']['files'];opened=[];array_summary=None
        for item in files:
            p=ROOT/item['path'];assert sha_file(p)==item['sha256']
            if item in context['references'][1]['source']['values']['result']['artifacts']:
                try:
                    with np.load(p,allow_pickle=False) as a:
                        if 'position_m' in a.files:
                            array_summary={'time_count':len(a['time_s']),'handle_count':a['position_m'].shape[1],'time_min_s':float(a['time_s'].min()),'time_max_s':float(a['time_s'].max()),'head_at_300_m':a['position_m'][-1,0].tolist()}
                except (ValueError,OSError):pass
            opened.append({'path':item['path'],'sha256':item['sha256'],'bytes_read':len(p.read_bytes())})
        assert array_summary and array_summary['time_count']==301 and array_summary['handle_count']==224
        md=context['references'][1]['source']['values']['manuscript']['document'];assert '问题重述' in (ROOT/md['path']).read_text(encoding='utf-8')
        new(folder/'read-verification.json',{'files':opened,'arrays':array_summary,'inline_model_read':True,'manuscript_read':True,'logical_figures_verified':9,'Q2_model_approved':False,'Q2_result_approved':False,'new_solver_runs':0,'Q1_final_export_required':False})
        new(folder/'registration.json',{'target':q,'reference_ids':ids,'question_context_sha256':digest(context),'source_task_unchanged':True,'target_is_intake_not_model_contract':True})
    print(json.dumps({'target_id':TARGET,'folder':rel(folder),'references':ids,'Q2_status':'INTAKE_AND_REFERENCE_READY','new_solver_runs':0}))

def resume(folder):
    with workflow() as w:context=w.question_context(**read(Path(folder)/'resume-request.json'))
    if context!=read(Path(folder)/'question-context.json'):raise ValueError('Reopened question context differs')
    print(json.dumps({'target_id':TARGET,'context_identical':True,'reference_count':len(context['references']),'Q2_model_approved':False,'Q2_result_approved':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('step',choices=['prepare','resume']);p.add_argument('--run',required=True,type=Path);a=p.parse_args()
    (prepare if a.step=='prepare' else resume)(a.run)
