"""Register explicit D4 result-review and all-nine-figure approvals, separately."""
from modelcrew.project_assets import asset_path
import json, shutil
from datetime import datetime, timezone
from modelcrew.config import ROOT
from modelcrew.collaboration import sha_file
from modelcrew.full_result import verify_frozen_files
from modelcrew.mathematics import snapshot
from scripts.run_d4_full import workflow

STATEMENT='审阅稿通过 然后9张候选图通过'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def main():
    base=asset_path(ROOT,'stage-d/d4');current=read(base/'current-solve.json');run=ROOT/current['run_dir']
    verify_frozen_files(run)
    prior=read(base/'evidence.json')
    for name in ['stage-d/d4/result-review.md','stage-d/d4/candidate-figures.md']:
        item=next(x for x in prior['files'] if x['path']==name)
        assert sha_file(ROOT/name)==item['sha256'],'Displayed document changed'
    manifest=read(run/'figure-manifest.json');assert len(manifest['figures'])==9
    for fig in manifest['figures']:
        for fmt,path in fig['files'].items():assert sha_file(ROOT/path)==fig['file_hashes'][fmt]
    identifier='user-d4-review-and-nine-figures-'+sha_file(base/'result-review.md')[:16]
    dest=base/'confirmations'/identifier;dest.mkdir(parents=True,exist_ok=True)
    configs=['resources/paper/workflow.json','resources/paper/writer-instructions.md','resources/paper/chinese-modeling-policy.json','docs/scientific-figure-contract.md']
    context=[]
    for name in configs:
        p=ROOT/name;target=dest/('source-'+p.name)
        if not target.exists():shutil.copyfile(p,target)
        assert sha_file(target)==sha_file(p)
        context.append({'path':name,'sha256':sha_file(p),'snapshot':target.relative_to(ROOT).as_posix()})
    binding={k:current[k] for k in ['task_id','version','execution_id','result_revision','P2_receipt_sha256']}
    shared={'actor':'user','user_statement':STATEMENT,'binding':binding,'configuration_sources':context,'decision':'approve'}
    payloads={
        'review-approval.json':{**shared,'scope':'D4_full_result_review','review_path':'stage-d/d4/result-review.md','review_sha256':sha_file(base/'result-review.md'),'arrays_sha256':sha_file(run/'output/trajectories.npz'),'workbook_sha256':sha_file(run/'output/result1.xlsx'),'D5_manuscript_approved':False,'note':'批准本次D4全量结果审阅稿及其全量结果；尚不存在D5论文正文。'},
        'figure-selection-approval.json':{**shared,'scope':'D4_all_nine_candidate_figures','candidate_list_path':'stage-d/d4/candidate-figures.md','candidate_list_sha256':sha_file(base/'candidate-figures.md'),'figure_manifest_path':(run/'figure-manifest.json').relative_to(ROOT).as_posix(),'figure_manifest_sha256':sha_file(run/'figure-manifest.json'),'selected_figure_ids':[f['figure_id'] for f in manifest['figures']],'selected_figures':[{'figure_id':f['figure_id'],'files':f['files'],'file_hashes':f['file_hashes']} for f in manifest['figures']],'selected_count':9,'note':'用户已批准全部9图，覆盖原先8图推荐；以后正文嵌图、编号、题注及W1/W2仍按阶段执行。'}
    }
    for name,payload in payloads.items():
        target=dest/name
        if not target.exists():write(target,{**payload,'recorded_at':datetime.now(timezone.utc).isoformat()})
        old=read(target)
        assert all(old[k]==v for k,v in payload.items())
    with workflow() as w,w.lock(current['task_id']):
        t=w.task(current['task_id'])
        assert t['current_version']==current['version'] and t['result_revision']==current['result_revision'] and str(t['execution_id'])==current['execution_id']
        entries={}
        for name in payloads:
            p=dest/name;scope=payloads[name]['scope']
            entries[scope]=w.record_entry(t['id'],version=current['version'],kind='feedback',actor='user',request_id=identifier+'-'+scope,text=STATEMENT+'；确认范围：'+scope,artifacts=[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha_file(p),'role':scope}],metadata={'scope':scope,'decision':'approve','binding':binding})
        state=w.action(t['id'],actor='user',request_id=identifier+'-full-result',version=current['version'],kind='result',decision='approve',result_revision=current['result_revision'],math_semantic_sha256=snapshot(w,t['id'],current['version'])['semantic_sha256'],reason=STATEMENT+'；对应本次D4全量结果审阅稿，独立P2已通过。')
        after=state['task'];assert after['result_approved'] and after['phase']=='COMPLETED'
        registration={'binding':binding,'entries':entries,'result_approved':True,'phase':after['phase'],'phase_scope':'confirmed modeling/solving workflow only, not D5 or all Stage D','selected_figure_count':9,'approval_files':{n:sha_file(dest/n) for n in payloads}}
        if not (dest/'registration.json').exists():write(dest/'registration.json',registration)
        else:assert read(dest/'registration.json')==registration
    current.update({'phase':after['phase'],'result_approved':True,'result_review_approval':(dest/'review-approval.json').relative_to(ROOT).as_posix(),'figure_selection':'user_approved_all_nine','selected_figures':9,'figure_selection_approval':(dest/'figure-selection-approval.json').relative_to(ROOT).as_posix(),'confirmation_registration':(dest/'registration.json').relative_to(ROOT).as_posix()})
    write(base/'current-solve.json',current)
    progress=read(asset_path(ROOT,'stage-d/progress.json'));progress['current_milestone']='D4_case_full_result_and_nine_figures_user_confirmed'
    d4=progress['milestones']['D4'];d4.update({'result_confirmation':'user_approved','figure_selection':'user_approved_all_nine','selected_figures':9,'result_review_approval':current['result_review_approval'],'figure_selection_approval':current['figure_selection_approval']})
    progress['next']='D5 Writer/W1 and Chinese modeling Markdown; D4 full result and all nine figures confirmed; future D5 manuscript needs its own review'
    write(asset_path(ROOT,'stage-d/progress.json'),progress)
    note=base/'user-confirmation.md'
    text='# D4 用户确认\n\n用户明确：“'+STATEMENT+'”。已分别记录本次D4全量结果审阅稿通过，以及全部9张候选图通过；图集以本次9张文件哈希为准，原推荐8张不再限制用户选择。\n\n业务结果批准已登记，当前建模求解工作流为COMPLETED；这不表示整个阶段D完成。审阅稿、候选清单与图文件保持原字节，其中“待确认”描述是交付当时的历史状态；本记录及current-solve.json为最新确认状态。\n\nD5论文正文尚未生成，本次批准不冒充后续论文正文审阅或W1/W2。\n\n[审阅确认]('+current['result_review_approval'].split('stage-d/d4/')[1]+') · [九图确认]('+current['figure_selection_approval'].split('stage-d/d4/')[1]+') · [数据库登记]('+current['confirmation_registration'].split('stage-d/d4/')[1]+')\n'
    if not note.exists():note.write_text(text,encoding='utf-8')
    else:assert note.read_text(encoding='utf-8')==text
    verify_frozen_files(run)
    write(dest/'verification.json',{'frozen_files_unchanged':True,'review_unchanged':sha_file(base/'result-review.md')==payloads['review-approval.json']['review_sha256'],'candidate_list_unchanged':sha_file(base/'candidate-figures.md')==payloads['figure-selection-approval.json']['candidate_list_sha256'],'all_nine_figures_hash_verified':True,'result_approved':True,'D5_not_started':progress['milestones']['D5']['status']=='not_started'})
    print(json.dumps({'result_approved':True,'nine_figures_approved':True,'phase':after['phase'],'record':note.relative_to(ROOT).as_posix()},ensure_ascii=False))
if __name__=='__main__':main()
