"""Persist explicit user approval of the current D5 manuscript and all nine figures."""
from modelcrew.project_assets import asset_path
import json,os,shutil
from datetime import datetime,timezone
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from modelcrew.modeling_paper import writing_context,require_review_for_export
from modelcrew.writing_reviews import selection_record,review_status
from scripts.run_d4_full import workflow

STATEMENT='论文通过 9张图也通过了'

def mutable(path,value):
    temporary=path.with_name(path.name+'.next');wh.new(temporary,value);os.replace(temporary,path)

def main():
    base=asset_path(ROOT,'stage-d/d5');current=wh.read(base/'current-writing.json');folder=ROOT/current['run_dir'];md=folder/'单题论文-中文审阅稿.md';catalog=folder/'figure-catalog.json'
    assert wh.sha(md)==current['manuscript_sha256'],'Presented manuscript changed'
    identifier='user-d5-manuscript-and-nine-figures-'+wh.sha(md)[:16]
    dest=base/'confirmations'/identifier;dest.mkdir(parents=True,exist_ok=True)
    ctx=writing_context()
    if not (dest/'writer-context.json').exists():wh.new(dest/'writer-context.json',ctx)
    else:assert wh.read(dest/'writer-context.json')==ctx
    figures=wh.read(catalog)['figures'];selected=[f['id'] for f in figures if f['formal']];assert len(figures)==len(selected)==9
    figure_record=selection_record(catalog,selected,decision='approve',actor='user',statement=STATEMENT,reason='用户明确通过本次论文中全部9张图，绑定当前图目录、内容、题注用途及政策。')
    figure_record['binding']=current['binding'];figure_record['catalog_path']=wh.rel(catalog)
    if not (dest/'figure-selection-approval.json').exists():wh.new(dest/'figure-selection-approval.json',figure_record)
    else:assert wh.read(dest/'figure-selection-approval.json')==figure_record
    with workflow() as w:
        before=wh.status(folder,w)
        if not (folder/'manuscript-review.json').exists():
            wh.record_manuscript_decision(folder,decision='approve',actor='user',statement=STATEMENT,reason='用户明确通过当前D5中文论文正文及其9幅入文图，对应已交付稿件，不沿用D4结果页批准。',w=w)
        manuscript=wh.read(folder/'manuscript-review.json')
        assert manuscript['user_statement']==STATEMENT and manuscript['decision']=='approve'
        if not (dest/'manuscript-approval.json').exists():shutil.copyfile(folder/'manuscript-review.json',dest/'manuscript-approval.json')
        else:assert wh.sha(dest/'manuscript-approval.json')==wh.sha(folder/'manuscript-review.json')
        bundle={'review_version':'2.0.0','manuscript_review':manuscript,'figure_selection_review':figure_record}
        mutable(folder/'reviews.json',bundle)
        report=require_review_for_export(md,catalog,bundle)
        assert report['separate_reviews']['can_export']
        entries={}
        for name,scope in [('manuscript-approval.json','D5_current_manuscript'),('figure-selection-approval.json','D5_current_nine_figures')]:
            path=dest/name
            entries[scope]=w.record_entry(current['binding']['task_id'],version=current['binding']['contract_version'],kind='feedback',actor='user',request_id=identifier+'-'+scope,text=STATEMENT+'；分别确认范围：'+scope,artifacts=[{'path':wh.rel(path),'sha256':wh.sha(path),'role':scope}],metadata={'decision':'approve','scope':scope,'binding':current['binding'],'manuscript_sha256':wh.sha(md),'figure_catalog_sha256':wh.sha(catalog)})
        after=wh.status(folder,w)
        assert after['state']['phase']=='READY_FOR_E_EXPORT'
        assert after['state']['reviews']['manuscript']=='approved' and after['state']['reviews']['figure_selection']=='approved'
        assert after['state']['reviews']==report['separate_reviews']
        registration={'binding':current['binding'],'database_entries':entries,'phase':after['state']['phase'],'manuscript':'approved','figure_selection':'approved','selected_figures':9,'can_export':True,'formal_export_performed':False,'W2_performed':False,'approval_files':{name:wh.sha(dest/name) for name in ['manuscript-approval.json','figure-selection-approval.json']}}
        if not (dest/'registration.json').exists():wh.new(dest/'registration.json',registration)
        else:assert wh.read(dest/'registration.json')==registration
    current['state']=after['state'];current['manuscript_approval']=wh.rel(dest/'manuscript-approval.json');current['figure_selection_approval']=wh.rel(dest/'figure-selection-approval.json');current['confirmation_registration']=wh.rel(dest/'registration.json')
    mutable(base/'current-writing.json',current)
    progress=wh.read(asset_path(ROOT,'stage-d/progress.json'));progress['current_milestone']='D5_case_manuscript_and_nine_figures_user_confirmed'
    progress['milestones']['D5'].update({'status':'single_case_manuscript_and_figures_confirmed','manuscript_review':'user_approved','figure_selection':'user_approved_all_nine_current_D5','manuscript_approval':current['manuscript_approval'],'figure_selection_approval':current['figure_selection_approval'],'writing_phase':'READY_FOR_E_EXPORT'})
    progress['next']='D5 current-case manuscript and all nine figures confirmed; D6 remains pending; formal export/assembly and independent W2 belong to E'
    mutable(asset_path(ROOT,'stage-d/progress.json'),progress)
    note='# D5 用户确认\n\n用户明确：“'+STATEMENT+'”。当前D5中文论文正文和全部9张入文图已分别记录通过，均绑定当前文件与政策哈希。\n\n稿件SHA256：`'+wh.sha(md)+'`。状态为READY_FOR_E_EXPORT，正文approved、选图approved、can_export=true。这表示用户确认条件已满足，不代表已正式导出或通过W2。\n\n[已通过正文](../runs/writing/d5-q1-20261108-v4/单题论文-中文审阅稿.md) · [正文批准]('+wh.rel(dest/'manuscript-approval.json').split('stage-d/d5/')[1]+') · [九图批准]('+wh.rel(dest/'figure-selection-approval.json').split('stage-d/d5/')[1]+') · [登记回执]('+wh.rel(dest/'registration.json').split('stage-d/d5/')[1]+')\n\n先前交付报告中的“待审阅”为历史状态，保持原证据；本记录和current-writing.json反映最新确认。全文与图文件均未修改。D6及E/W2尚未完成，当前确认不等同于整个阶段D或通用Writer/API验收。\n'
    if not (base/'user-confirmation.md').exists():(base/'user-confirmation.md').write_text(note,encoding='utf-8')
    else:assert (base/'user-confirmation.md').read_text(encoding='utf-8')==note
    r=asset_path(ROOT,'stage-d/README.md');text=r.read_text(encoding='utf-8')
    text=text.replace('当前开发题论文手与独立W1也已完成并等待新正文审阅','当前开发题论文手与独立W1也已完成，新正文及全部9图已获用户确认')
    text=text.replace('中文稿待用户审阅，九图确认保留，见 [D5报告](d5/acceptance-report.md)','中文稿与全部9图已获用户确认，见 [确认记录](d5/user-confirmation.md) / [D5报告](d5/acceptance-report.md)')
    r.write_text(text,encoding='utf-8')
    paths=[md,catalog,folder/'publication.json',folder/'manuscript-review.json',folder/'reviews.json',folder/'state.json',base/'current-writing.json',base/'user-confirmation.md',asset_path(ROOT,'stage-d/progress.json'),r,Path(__file__).resolve(),*dest.glob('*.json')]
    paths += [folder/asset['path'] for fig in figures for asset in fig['files'].values()]
    index={'recorded_at':datetime.now(timezone.utc).isoformat(),'binding':current['binding'],'user_statement':STATEMENT,'verification':{'unchanged_manuscript':wh.sha(md)==current['manuscript_sha256'],'all_nine_selected':len(selected)==9,'export_review_gate':'passed','formal_exports':0,'W2':'not_started'},'files':wh.frozen_manifest(paths)}
    if not (base/'confirmation-evidence.json').exists():wh.new(base/'confirmation-evidence.json',index)
    else:wh.verify_files(wh.read(base/'confirmation-evidence.json')['files'])
    print(json.dumps({'manuscript':'approved','nine_figures':'approved','phase':after['state']['phase'],'can_export':True,'record':wh.rel(base/'user-confirmation.md')},ensure_ascii=False))

if __name__=='__main__':main()
