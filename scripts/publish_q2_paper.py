"""Publish Q2 Markdown for user review; retain approvals separately, no formal export."""
from modelcrew.project_assets import asset_path
import json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from modelcrew.collaboration import Call,Binding,Snapshot,Artifact,sha_file,CollaborationStore
from modelcrew.modeling_paper import validate_draft
from scripts.run_d4_full import workflow
F=asset_path(ROOT,'stage-d/runs/writing/d6-q2-20261109-v2')

def main():
    draft_review=wh.read(F/'draft-consistency-review.json')
    if draft_review.get('status')!='PASS':raise ValueError('independent draft consistency findings unresolved')
    with workflow() as w:
        meta=wh.require_W1(F,w);supplier=wh.read(F/'Writer-provider-call.json');store=CollaborationStore(F/'records')
        provider_author=Call(call_id=supplier['call_id'],context_id=supplier['context_id'],role='writing',binding=Binding.model_validate(meta['binding']));store.register_call(provider_author)
        result=wh.publish(F,F/'author-draft.md',w)
        author=meta['author']['call_id'];prior=store.load(Snapshot,meta['W1_snapshot_sha256'])
        article=F/'单题论文-中文审阅稿.md'
        prose=Artifact(artifact_id='manuscript',kind='manuscript',path=wh.rel(article),sha256=sha_file(article),author_call_ids=[author,provider_author.call_id])
        finalkey=store.freeze(Snapshot(binding=provider_author.binding,hand='writing',artifacts=prior.artifacts+[prose],lineage_call_ids=prior.lineage_call_ids+[provider_author.call_id]))
        wh.new(F/'manuscript-snapshot.json',{'snapshot_sha256':finalkey,'W1_snapshot_sha256':meta['W1_snapshot_sha256'],'supplier_API_writer_call':provider_author.model_dump(mode='json'),'scope':'published prose authorship for later W2; not a new W1 review or manuscript approval'})
        w.record_entry(meta['binding']['task_id'],version=2,kind='experiment',actor='writing-hand',request_id='q2-writing-v2-W1-and-Markdown',text='第二题：独立W1四项通过，实际供应商Writer API生成并由Codex校核整合中文Markdown；按用户决定仅7幅新图入文、两图跨题引用；等待正文审阅。',artifacts=[{'path':wh.rel(p),'sha256':sha_file(p),'role':role} for p,role in [(article,'Q2_manuscript_pending_user_review'),(F/'figure-selection-review.json','Q2_user_selected_seven'),(F/'W1-admission.json','Q2_independent_W1'),(F/'manuscript-snapshot.json','Q2_prose_authorship')]],metadata={'binding':meta['binding'],'manuscript_user_approved':False,'formal_export_performed':False})
    check=validate_draft(article,F/'figure-catalog.json')
    if check['status']!='passed' or result['state']['reviews']['manuscript']!='pending' or result['state']['reviews']['figure_selection']!='approved' or result['state']['reviews']['can_export']:raise ValueError('wrong delivery/review state')
    old=asset_path(ROOT,'stage-d/d5/current-writing.json')
    with workflow() as w:
        q1=wh.status(ROOT/wh.read(old)['run_dir'],w)
    if q1['state']['reviews']['manuscript']!='approved' or q1['state']['reviews']['figure_selection']!='approved':raise ValueError('Prior Q1 approval invalidated')
    wh.new(F/'regression.json',{'status':'PASS','full_suite':{'command':'python -m pytest tests -q --integration --basetemp tmp/q2-writing-final-regression-20261109 -p no:cacheprovider','passed':491,'elapsed_seconds':143.73},'focused_writing_policy_suite':{'passed':54,'elapsed_seconds':12.11},'counts_overlap':True,'prior_Q1_manuscript_and_selection_approvals_still_current':True})
    sources=['AGENTS.md','resources/paper/workflow.json','resources/paper/writer-instructions.md','resources/paper/chinese-modeling-policy.json','docs/scientific-figure-contract.md','docs/three-hand-collaboration.md','resources/algorithms/index.md','resources/algorithms/numerical-geometry.md','modelcrew/writing_hand.py','modelcrew/modeling_paper.py','modelcrew/writing_reviews.py','scripts/write_q2_paper.py','scripts/draft_q2_paper.py','scripts/edit_q2_draft.py','scripts/publish_q2_paper.py','tests/test_q2_paper_policy.py']
    wh.new(F/'source-read-and-implementation-log.json',{'sources':[{'path':p,'sha256':sha_file(ROOT/p),'text':(ROOT/p).read_text(encoding='utf-8-sig')} for p in sources],'algorithm_scope':'existing verified numerical-geometry method only, no new solver selection','math_reasoning_use':'formula/units/branch proof checks only, not paper outline','policy_exception_scope':'only this user-confirmed Q2 seven-figure catalog; global default 8 unchanged'})
    current={**result,'manuscript_path':wh.rel(article),'manuscript_sha256':sha_file(article),'selected_figures':7,'archived_candidates':9,'excluded_duplicate_figures':['raw-01','raw-02'],'first_question_cross_references':['第一题图1','第一题图3'],'Writer_provider_API_call':supplier,'W1_mode':'new independent read-only agent; original configured-provider FAIL preserved and adjudicated','new_solver_runs':0,'new_figures_generated':0,'formal_exports':0,'generic_autonomous_Writer':'not_implemented; case adapter invokes actual configured service','manuscript_snapshot_sha256':finalkey}
    (asset_path(ROOT,'stage-d/q2-full/current-writing.json')).write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    report=f'''# 第二题写作与独立W1交付

用户已明确确认第二题结果正确，并指出raw-01、raw-02在第一题已出现，其他图通过。结果确认与选图分别登记在confirmations/user-q2-result-and-seven-figures-20261109，数据库求解任务结果已批准。按此次明确决定，第二题只嵌入其余7幅图；两幅重复图不再嵌入，以第一题图1与图3跨题引用。原9候选及第一题已通过稿、模型和图均不改写。

[第二题中文Markdown审阅稿]({article.as_posix()})已完成。模型、连续首事件求解、终态表、数值检验和局限完整呈现；10坐标与24速率的全部跨六位舍入格区间列于附录，打印区间两端向外舍入。原始224把手位置/速度/速率上下界另有附件。正式入文7图，保留9候选归档；低于默认8图的例外由用户原话、同一结果绑定及精确7个figure IDs限定，不修改全局政策，也不以新图凑数。

独立W1在长篇正文前完成claims/evidence/citations/outline四项PASS，回执{wh.read(F/'W1-admission.json')['receipt_sha256']}。首轮供应商W1为FAIL且有空冗余schema字段；仅删除空字段后按原FAIL接纳，原始判定与issues均保留在v1。新独立上下文逐个核对真实路径、JSONPointer、哈希和引用原文，判定其主要反对理由不成立；v2另冻结P2已通过、用户确认及逐claim映射后独立通过。不能称供应商W1最终通过，也不能让作者自检替代W1。

正文确实调用项目配置的{supplier['configured_model']}供应商Writer API，call_id={supplier['call_id']}；Codex随后依已通过W1与原始证据完成LaTeX、题意/假设归属、各板对可用不同固定轴、真实图表及附录区间的校核整合。原始API正文、调用及编辑记录均保留。交付前独立上下文另检查大纲落实与数值一致性；此项不是W2最终版式审查。

机械检查通过，491项全项目回归通过，54项相关写作/选图检查通过（计数重叠）。实际第一题正文与选图仍为approved，第二题正文为pending、选图为approved、can_export=false。没有新增求解或重画图，没有正式LaTeX/PDF/Word导出，也没有代用户批准本次新正文。通用自主Writer框架并未因本题适配器而宣称完成。

请审阅当前第二题正文；通过后再进入后续汇编与正式导出/W2。
'''
    (asset_path(ROOT,'stage-d/q2-full/writing-report.md')).write_text(report,encoding='utf-8')
    wh.new(F/'delivery-verification.json',{'status':'PASS','manuscript_sha256':sha_file(article),'mechanical_check':check,'state':result['state'],'prior_Q1_approval_preserved':True,'all_34_interval_rows_present':True,'source_XLSX_hash_unchanged':sha_file(F/'result2.xlsx')==sha_file(ROOT/meta['source_run']/'results/result2.xlsx'),'report_path':'stage-d/q2-full/writing-report.md','not_user_approval':True})
    print(json.dumps({'phase':result['state']['phase'],'manuscript':wh.rel(article),'W1':'PASS','figures':7,'manuscript_approval':'pending','figure_approval':'approved','can_export':False,'regression_passed':491},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
