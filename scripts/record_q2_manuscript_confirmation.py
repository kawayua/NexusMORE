"""Record the user's approval of the exact delivered Q2 prose; preserve prior figure consent."""
from modelcrew.project_assets import asset_path
import json,os,shutil
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from modelcrew.modeling_paper import writing_context,require_review_for_export
from scripts.run_d4_full import workflow
STATEMENT='正文审阅通过'

def mutable(path,value):
    temporary=path.with_name(path.name+'.next');wh.new(temporary,value);os.replace(temporary,path)

def main():
    base=asset_path(ROOT,'stage-d/q2-full');pointer=base/'current-writing.json';current=wh.read(pointer);folder=ROOT/current['run_dir']
    md=folder/'单题论文-中文审阅稿.md';catalog=folder/'figure-catalog.json'
    if wh.sha(md)!=current['manuscript_sha256']:raise ValueError('Delivered manuscript changed')
    figure_hash=wh.sha(folder/'figure-selection-review.json');catalog_hash=wh.sha(catalog)
    figures=wh.read(catalog)['figures'];selected=[f['id'] for f in figures if f['formal']]
    if len(selected)!=7 or {'raw-01','raw-02'}&set(selected):raise ValueError('User selected seven figures differ')
    identifier='user-q2-manuscript-'+wh.sha(md)[:16];dest=base/'confirmations'/identifier;dest.mkdir(parents=True,exist_ok=True)
    if not (dest/'writer-context.json').exists():wh.new(dest/'writer-context.json',writing_context())
    with workflow() as w:
        wh.status(folder,w)
        if not (folder/'manuscript-review.json').exists():
            wh.record_manuscript_decision(folder,decision='approve',actor='user',statement=STATEMENT,reason='用户明确通过已交付的第二题中文正文；绑定当前稿件、7幅入文图及既定去重政策，不批准任何后续改稿。',w=w)
        record=wh.read(folder/'manuscript-review.json')
        if record['user_statement']!=STATEMENT or record['decision']!='approve':raise ValueError('Another decision already exists')
        if not (dest/'manuscript-approval.json').exists():shutil.copyfile(folder/'manuscript-review.json',dest/'manuscript-approval.json')
        if wh.sha(dest/'manuscript-approval.json')!=wh.sha(folder/'manuscript-review.json'):raise ValueError('Approval copy differs')
        bundle=wh.read(folder/'reviews.json');check=require_review_for_export(md,catalog,bundle);after=wh.status(folder,w)
        if after['state']['phase']!='READY_FOR_E_EXPORT' or not check['separate_reviews']['can_export']:raise ValueError('Current separate approvals required')
        approval=dest/'manuscript-approval.json'
        entry=w.record_entry(current['binding']['task_id'],version=current['binding']['contract_version'],kind='feedback',actor='user',request_id=identifier,text=STATEMENT+'；范围为当前第二题正文，既有七图选择保持原确认。',artifacts=[{'path':wh.rel(approval),'sha256':wh.sha(approval),'role':'Q2_current_manuscript_approval'}],metadata={'binding':current['binding'],'decision':'approve','scope':'Q2_current_manuscript','manuscript_sha256':wh.sha(md),'figure_catalog_sha256':catalog_hash})
        registration={'binding':current['binding'],'database_entry':entry,'phase':after['state']['phase'],'manuscript':'approved','figure_selection':'approved','selected_figures':7,'selected_figure_ids':selected,'can_export':True,'formal_export_performed':False,'W2_performed':False,'manuscript_approval_sha256':wh.sha(approval),'figure_approval_origin':{'path':wh.rel(folder/'figure-selection-review.json'),'sha256':figure_hash,'statement':wh.read(folder/'figure-selection-review.json')['user_statement']}}
        if not (dest/'registration.json').exists():wh.new(dest/'registration.json',registration)
        elif wh.read(dest/'registration.json')!=registration:raise ValueError('Registration changed')
    if wh.sha(md)!=current['manuscript_sha256'] or wh.sha(catalog)!=catalog_hash or wh.sha(folder/'figure-selection-review.json')!=figure_hash:raise ValueError('Approved artifacts changed')
    current.update(state=after['state'],manuscript_approval=wh.rel(dest/'manuscript-approval.json'),confirmation_registration=wh.rel(dest/'registration.json'))
    mutable(pointer,current)
    note=base/'manuscript-confirmation.md'
    text=f'''# 第二题正文用户确认

用户明确：“{STATEMENT}”。已将通过记录绑定到已交付的第二题中文稿，稿件SHA256为`{wh.sha(md)}`。

第二题正文approved、既有7幅入文图选择approved，状态为READY_FOR_E_EXPORT。raw-01、raw-02继续不入文，仅引用第一题对应图；原图、正文、第一题通过记录及本题去重政策保持原样。

此记录不表示已生成正式LaTeX/PDF/Word或完成W2。先前交付文件中的待审描述保留为历史状态；当前状态以current-writing.json与本次记录为准。

[已通过正文]({md.as_posix()}) · [正文确认]({(dest/'manuscript-approval.json').as_posix()}) · [登记回执]({(dest/'registration.json').as_posix()})
'''
    if not note.exists():note.write_text(text,encoding='utf-8')
    elif note.read_text(encoding='utf-8')!=text:raise ValueError('Confirmation note changed')
    files=[md,catalog,folder/'manuscript-review.json',folder/'figure-selection-review.json',folder/'reviews.json',folder/'state.json',pointer,note,*dest.glob('*.json')]
    files += [folder/asset['path'] for f in figures for asset in f['files'].values()]
    evidence={'user_statement':STATEMENT,'binding':current['binding'],'checks':{'manuscript_unchanged':True,'selected_seven_figure_hashes_unchanged':True,'separate_approval_gate':'passed','formal_exports':0,'W2':'not_started'},'files':wh.frozen_manifest(files)}
    if not (dest/'verification.json').exists():wh.new(dest/'verification.json',evidence)
    else:wh.verify_files(wh.read(dest/'verification.json')['files'])
    print(json.dumps({'manuscript':'approved','figures':7,'figure_selection':'approved','phase':after['state']['phase'],'can_export':True,'note':wh.rel(note)},ensure_ascii=False))
if __name__=='__main__':main()
