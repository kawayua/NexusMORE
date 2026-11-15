"""Q2 writing hand: explicit consent, frozen W1 outline and configured supplier calls."""
from modelcrew.project_assets import asset_path
import argparse,json,uuid,shutil
from pathlib import Path
import httpx
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from modelcrew.collaboration import Binding,Call,Artifact,Snapshot,CollaborationStore,Receipt,sha_file,REQUIRED_CHECKS
from modelcrew.modeling_paper import writing_context
from modelcrew.writing_reviews import selection_record
from modelcrew.mathematics import snapshot as math_snapshot
from modelcrew.q2_full_result import verify_q2_frozen_files
from modelcrew.modeling_hand import M1Answer,pointer
from modelcrew.model_client import JsonModel
from scripts.run_d4_full import workflow
from scripts.run_q2_full import active,TASK
from scripts.recheck_q2_p2 import JsonClient

STATEMENT='结果正确 然后对于配图 raw-01：板凳尺寸与孔位（示意） raw-02：初始实体外包络 这两张图 第一题已经出现了其他图通过 请进入写作'
FOLDER=asset_path(ROOT,'stage-d/runs/writing/d6-q2-20261109-v1')
MODEL=asset_path(ROOT,'stage-d/runs/modeling/q2-collision-20261109-v2')

def prepare():
    f=active();verify_q2_frozen_files(f);base=asset_path(ROOT,'stage-d/q2-full');current=wh.read(base/'current-run.json')
    binding={k:current[k] for k in ['task_id','contract_version','contract_sha256','execution_id','result_revision']}
    selected=[x['figure_id'] for x in wh.read(f/'figures.json')['figures'] if x['figure_id'] not in ['raw-01','raw-02']]
    consent=base/'confirmations/user-q2-result-and-seven-figures-20261109';consent.mkdir(parents=True,exist_ok=True)
    if not (consent/'result-approval.json').exists():wh.new(consent/'result-approval.json',{'actor':'user','user_statement':STATEMENT,'decision':'approve','binding':binding,'P2_receipt_sha256':current['P2_receipt_sha256'],'result_report_sha256':sha_file(base/'acceptance-report.md'),'workbook_sha256':sha_file(f/'results/result2.xlsx'),'manuscript_approved':False})
    if not (consent/'figure-approval.json').exists():wh.new(consent/'figure-approval.json',{'actor':'user','user_statement':STATEMENT,'decision':'approve','binding':binding,'selected_figure_ids':selected,'omitted_duplicate_ids':['raw-01','raw-02'],'reason':'用户指出两图已在第一题出现，本题不重复插图，其他7图通过；正文可引用第一题对应图。','source_manifest_sha256':sha_file(f/'figures.json'),'selected_figures':[x for x in wh.read(f/'figures.json')['figures'] if x['figure_id'] in selected]})
    with workflow() as w:
        for name in ['result-approval.json','figure-approval.json']:
            p=consent/name
            w.record_entry(TASK,version=2,kind='feedback',actor='user',request_id='q2-confirm-20261109-'+name,text=STATEMENT,artifacts=[{'path':wh.rel(p),'sha256':sha_file(p),'role':name}],metadata={'binding':binding,'scope':name})
        t=w.task(TASK)
        if not t['result_approved']:
            w.action(TASK,actor='user',request_id='q2-result-confirm-20261109',version=2,kind='result',decision='approve',result_revision=1,math_semantic_sha256=math_snapshot(w,TASK,2)['semantic_sha256'],reason=STATEMENT)
        wh.assert_upstream(w,binding)
    current.update(result_user_approval='approved',phase='COMPLETED',figure_selection_user_approval='approved_seven_excluding_two_duplicates',selected_figure_ids=selected,result_confirmation=wh.rel(consent/'result-approval.json'),figure_confirmation=wh.rel(consent/'figure-approval.json'))
    (base/'current-run.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    FOLDER.mkdir(parents=True,exist_ok=False);(FOLDER/'figures').mkdir();context=writing_context();wh.new(FOLDER/'writer-context.json',context)
    policy={'actor':'user','user_statement':STATEMENT,'reason':'第二题仅7幅新图入文；raw-01和raw-02与已通过第一题重复，改为跨题引用。不新增凑数图，不全局降低默认8图要求。','base_policy_sha256':sha_file(asset_path(ROOT,'resources/paper/chinese-modeling-policy.json')),'binding':binding,'question_ids':['q2'],'selected_figure_ids':sorted(selected),'minimum_formal':7,'scope':'only_this_q2_result_and_catalog','origin':wh.rel(consent/'figure-approval.json'),'origin_sha256':sha_file(consent/'figure-approval.json')}
    wh.new(FOLDER/'user-figure-policy.json',policy)
    catalog=[];number=0
    for item in wh.read(f/'figures.json')['figures']:
        fid=item['figure_id'];formal=fid in selected
        if formal:number+=1
        files={}
        for asset in item['files']:
            src=f/asset['path'];fmt=src.suffix[1:];target=FOLDER/'figures'/f'{fid}.{fmt}';shutil.copyfile(src,target)
            if sha_file(target)!=asset['sha256']:raise ValueError('Figure changed')
            files[fmt]={'path':target.relative_to(FOLDER).as_posix(),'sha256':sha_file(target)}
        catalog.append({'id':fid,'category':item['category'],'question_ids':['q2'],'title':item['title'],'purpose':item['claim'],'statistics':item['statistics'],'source_kind':'confirmed_Q2_'+item['category'],'formal':formal,'number':number if formal else None,'files':files,'limitation':item['risk'],'selection_note':'本题通过入文' if formal else '用户指出第一题已出现，本题不重复入文'})
    wh.new(FOLDER/'figure-catalog.json',{'question_ids':['q2'],'evidence':binding,'figures':catalog,'policy_override':{'path':'user-figure-policy.json','sha256':sha_file(FOLDER/'user-figure-policy.json')}})
    approval=selection_record(FOLDER/'figure-catalog.json',selected,decision='approve',actor='user',statement=STATEMENT,reason=policy['reason']);approval['origin']={'path':wh.rel(consent/'figure-approval.json'),'sha256':sha_file(consent/'figure-approval.json')};wh.new(FOLDER/'figure-selection-review.json',approval)
    q1=ROOT/wh.read(asset_path(ROOT,'stage-d/d5/current-writing.json'))['run_dir']
    wh.new(FOLDER/'previous-question-reference.json',{'manuscript_path':wh.rel(q1/'单题论文-中文审阅稿.md'),'manuscript_sha256':sha_file(q1/'单题论文-中文审阅稿.md'),'approval_path':wh.rel(q1/'manuscript-review.json'),'approval_sha256':sha_file(q1/'manuscript-review.json'),'figures':[{**item,'body_reference':'第一题图1' if item['id']=='raw-1' else '第一题图3'} for item in wh.read(q1/'figure-catalog.json')['figures'] if item['id'] in ['raw-1','raw-3']],'not_reembedded_in_Q2':True})
    # Actual reading excerpts are archived and pinned; references never cite internal math as external literature.
    sources=[asset_path(ROOT,'stage-d/d5/sources/cumcm2024a-statement.txt'),asset_path(ROOT,'stage-d/runs/references/d6-q1-to-q2-20261109-v2/问题二题面.txt'),asset_path(ROOT,'stage-d/d5/sources/scipy-brentq-1.15.3.txt')]
    wh.new(FOLDER/'citations.json',{'references':[{'number':1,'title':'2024年高教社杯全国大学生数学建模竞赛A题“板凳龙”题面，问题一、问题二','sources':[{'path':wh.rel(p),'sha256':sha_file(p),'text':p.read_text(encoding='utf-8')} for p in sources[:2]],'limitation':'题面本地原始字节与来源核对，未核验当届提交规范。'},{'number':2,'title':'SciPy 1.15.3，scipy.optimize.brentq官方文档','url':'https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.brentq.html','sources':[{'path':wh.rel(sources[2]),'sha256':sha_file(sources[2]),'text':sources[2].read_text(encoding='utf-8')}],'limitation':'读取已保存版本化官方文档，不冒称本轮联网核验。'}]})
    claims=[('C1','完整矩形外包络、相邻整对豁免与非相邻首次接触停止均为经确认模型假设；只回答问题二。',MODEL/'attempt-0/model-design.json','/new_assumptions'),('C2','复用第一题螺线、弧长反解与隐式速度；完整板长用于碰撞，孔距用于运动学。',MODEL/'attempt-0/model-design.json','/physical_dimensions'),('C3','全部24531非相邻板对的整段固定轴投影包围，15773个连续安全段与最终有限特征认证首碰。',f/'validation.json','/safe_segments'),('C4','首次接触区间[412.4738376736641,412.4738377034664]秒，龙头与第8节龙身接触。',f/'collision-event.json','/time_interval_s'),('C5','224个把手终态输出与指定7把手真实结果，速度为首碰左极限。',f/'results/selected-handles.json','/handles'),('C6','位置误差2.1174e-8米，速率误差6.7568e-8米每秒；10坐标、24速率跨六位舍入格并显式报告区间。',f/'precision-supplement.json','/rounding_disclosure'),('C7','17对独立Docker重跑输出相同，数值认证不等同真实构件无误差或碰撞后动力学。',f/'reproduction.json','/partitions')]
    sections=['问题重述','问题分析','模型假设','符号说明','模型建立','模型求解','结果分析','误差分析与模型检验','模型评价与推广','结论','参考文献']
    plan={'title':'完整矩形外包络约束下板凳龙盘入终止时刻与终态求解','scope':'问题二；与已通过第一题衔接的单题中文研究稿','sections':[{'title':s,'claims':['C1','C2'] if i<4 else ['C3','C4','C5','C6','C7']} for i,s in enumerate(sections)],'claims':[{'id':cid,'statement':statement,'evidence':[{'path':wh.rel(path),'selector':selector,'sha256':sha_file(path)}]} for cid,statement,path,selector in claims],'figure_selection':selected,'no_duplicate_figures':['raw-01','raw-02'],'previous_question_cross_references':['第一题图1：板凳实体与孔位','第一题图3：初态与盘入方向'],'required_precision_disclosure':'全部10位置坐标及24速率歧义在附录逐项列上下界；主文明确不得声称六位唯一。','method_limits':'固定轴证明整段投影分离；最早未决不得跳过；本次局部为横穿，孤立切触若未证必须返回未决，不声称异号覆盖任意相切。','writing_order':'摘要与关键词最后撰写；正文不泄漏哈希/数据库/审核流程。'}
    if FOLDER.name.endswith('-v2'):
        plan['revision_of']='stage-d/runs/writing/d6-q2-20261109-v1'
        plan['figure_placements']=[{'figure_id':fid,'number':i,'section':'模型建立' if fid=='raw-03' else '模型求解' if fid.startswith('process') else '结果分析','body_reference':'图'+str(i)} for i,fid in enumerate(selected,1)]
        plan['claims'][5]['statement']+='；六位小数舍入不唯一，跨格末位可能相差一单位，附录逐项给出上下界。'
    wh.new(FOLDER/'outline.json',plan)
    with workflow() as w:
        task=w.task(TASK)
        wh.new(FOLDER/'confirmed-source-status.json',{'binding':binding,'result_user_approved':task['result_approved'],'P2_admission':wh.read(f/'P2-admission.json'),'P2_admission_path':wh.rel(f/'P2-admission.json'),'P2_admission_sha256':sha_file(f/'P2-admission.json'),'historical_event_unknown_fields':'generated before later independent review; immutable execution-stage fields are not final current admission','figure_consent_path':wh.rel(consent/'figure-approval.json'),'figure_consent_sha256':sha_file(consent/'figure-approval.json')})
    chain=[]
    for claim in plan['claims']:
        for proof in claim['evidence']:
            value=pointer(wh.read(ROOT/proof['path']),proof['selector'])
            if sha_file(ROOT/proof['path'])!=proof['sha256']:raise ValueError('Claim source changed')
            chain.append({'claim_id':claim['id'],**proof,'path_exists':True,'hash_matches':True,'selector_resolves':True,'value':value})
    wh.new(FOLDER/'evidence-chain.json',{'verified_claims':chain,'citations_valid_JSON':True,'figure_ids_and_placements':plan.get('figure_placements',[])})
    # Rebinding is an explicit coding-to-writing handoff, not a new numerical authorship claim.
    store=CollaborationStore(FOLDER/'records');modeler=Call.model_validate(wh.read(MODEL/'run.json')['author']);store.register_call(modeler)
    original=wh.read(f/'run.json')['author'];coder=Call(call_id='q2-coding-handoff-'+uuid.uuid4().hex,context_id=original['context_id']+'-durable-handoff',role='coding',binding=Binding.model_validate(binding));store.register_call(coder)
    writer=Call(call_id='q2-writing-'+uuid.uuid4().hex,context_id='codex-q2-writing-'+uuid.uuid4().hex,role='writing',binding=Binding.model_validate(binding));store.register_call(writer)
    def artifact(a,k,p,owner):return Artifact(artifact_id=a,kind=k,path=wh.rel(p),sha256=sha_file(p),author_call_ids=[owner.call_id])
    upstream=[artifact('execution','execution',f/'part-10g-final-bound/execution.json',coder),artifact('contract','contract',f/'contract.json',modeler),artifact('model','mathematics',MODEL/'attempt-0/mathematics.json',modeler),artifact('design','input',MODEL/'attempt-0/model-design.json',modeler),artifact('event','result',f/'collision-event.json',coder),artifact('validation','result',f/'validation.json',coder),artifact('precision','result',f/'precision-supplement.json',coder),artifact('positions_precision','result',f/'review-recheck/precision-note.json',coder),artifact('selected_handles','result',f/'results/selected-handles.json',coder),artifact('reproduction','reproduction',f/'reproduction.json',coder),artifact('figure_sources','figure',f/'figures.json',coder)]
    lineage=[modeler.call_id,coder.call_id];key=store.freeze(Snapshot(binding=writer.binding,hand='coding',artifacts=upstream,lineage_call_ids=lineage));handoff=store.handoff(key,'writing',[a.artifact_id for a in upstream]);wh.new(FOLDER/'handoff.json',{**store.context(handoff,writer.call_id),'original_coding_author':original,'rebind_reason':'source numerical P2 binds logical folder execution; confirmed workflow and writing bind durable execution UUID; original P2 unchanged'})
    art=upstream+[artifact(a,k,FOLDER/p,writer) for a,k,p in [('outline','outline','outline.json'),('citations','source','citations.json'),('writer_context','input','writer-context.json'),('figure_catalog','figure_selection','figure-catalog.json'),('figure_consent','input','figure-selection-review.json'),('figure_policy','input','user-figure-policy.json'),('q1_reference','input','previous-question-reference.json'),('confirmed_source','input','confirmed-source-status.json'),('evidence_chain','input','evidence-chain.json')]]
    key=store.freeze(Snapshot(binding=writer.binding,hand='writing',artifacts=art,lineage_call_ids=lineage+[writer.call_id]))
    files=[ROOT/a.path for a in art]+[consent/'result-approval.json',consent/'figure-approval.json',f/'frozen-artifacts.json',f/'P2-admission.json',q1/'单题论文-中文审阅稿.md',q1/'manuscript-review.json']+sources+[ROOT/d['path'] for d in context['documents']]+[asset_path(ROOT,'resources/paper/workflow.json'),asset_path(ROOT,'resources/paper/chinese-modeling-policy.json')]
    files += [FOLDER/x['path'] for fig in catalog for x in fig['files'].values()]
    wh.new(FOLDER/'run.json',{'binding':binding,'author':writer.model_dump(mode='json'),'source_run':wh.rel(f),'workflow_sha256':context['workflow_sha256'],'W1_snapshot_sha256':key,'inputs':wh.frozen_manifest(sorted(set(files))),'implementation':'Q2 supplied outline/consent adapter; configured supplier API W1 and prose requested separately, no autonomous Writer framework claim'})
    wh.new(FOLDER/'W1-context.json',{'snapshot_sha256':key,'binding':binding,'required_checks':REQUIRED_CHECKS['W1'],'evidence':{a.artifact_id:a.path for a in art},'response_schema':M1Answer.model_json_schema(),'read_only':True,'gate_scope':'claims/evidence/citations/outline before prose'})
    wh.state_write(FOLDER,{'phase':'WAITING_W1','manuscript_review':'pending','figure_selection':'approved_seven','paper_exported':False})
    (asset_path(ROOT,'stage-d/q2-full/current-writing.json')).write_text(json.dumps({'run_dir':wh.rel(FOLDER),'binding':binding,'phase':'WAITING_W1'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Q2_CONFIRM_AND_PREPARE_PASS',flush=True)

def resume_prepare():
    # Resume only the retained failed handoff; existing authoring artifacts are not rewritten.
    f=active();verify_q2_frozen_files(f);base=asset_path(ROOT,'stage-d/q2-full')
    binding=wh.read(FOLDER/'figure-catalog.json')['evidence'];catalog=wh.read(FOLDER/'figure-catalog.json')['figures'];context=wh.read(FOLDER/'writer-context.json')
    consent=base/'confirmations/user-q2-result-and-seven-figures-20261109';q1=ROOT/wh.read(asset_path(ROOT,'stage-d/d5/current-writing.json'))['run_dir']
    sources=[asset_path(ROOT,'stage-d/d5/sources/cumcm2024a-statement.txt'),asset_path(ROOT,'stage-d/runs/references/d6-q1-to-q2-20261109-v2/问题二题面.txt'),asset_path(ROOT,'stage-d/d5/sources/scipy-brentq-1.15.3.txt')]
    store=CollaborationStore(FOLDER/'records');calls=[Call.model_validate(wh.read(p)) for p in (FOLDER/'records/Call').glob('*.json')]
    modeler=next(c for c in calls if c.role=='modeling');coder=next(c for c in calls if c.role=='coding');writer=next(c for c in calls if c.role=='writing');original=wh.read(f/'run.json')['author']
    with workflow() as w:wh.assert_upstream(w,binding)
    if (FOLDER/'run.json').exists():raise ValueError('Already completed; no blind repeated preparation')
    wh.new(FOLDER/'prepare-recovery.json',{'prior_error':'Required handoff inputs missing','cause':'execution artifact missing in first supplied coding handoff; no supplier call or prose had run','fix':'include real successful final primary execution receipt','model_result_figures_unchanged':True})
    def artifact(a,k,p,owner):return Artifact(artifact_id=a,kind=k,path=wh.rel(p),sha256=sha_file(p),author_call_ids=[owner.call_id])
    upstream=[artifact('execution','execution',f/'part-10g-final-bound/execution.json',coder),artifact('contract','contract',f/'contract.json',modeler),artifact('model','mathematics',MODEL/'attempt-0/mathematics.json',modeler),artifact('design','input',MODEL/'attempt-0/model-design.json',modeler),artifact('event','result',f/'collision-event.json',coder),artifact('validation','result',f/'validation.json',coder),artifact('precision','result',f/'precision-supplement.json',coder),artifact('positions_precision','result',f/'review-recheck/precision-note.json',coder),artifact('selected_handles','result',f/'results/selected-handles.json',coder),artifact('reproduction','reproduction',f/'reproduction.json',coder),artifact('figure_sources','figure',f/'figures.json',coder)]
    lineage=[modeler.call_id,coder.call_id];key=store.freeze(Snapshot(binding=writer.binding,hand='coding',artifacts=upstream,lineage_call_ids=lineage));handoff=store.handoff(key,'writing',[a.artifact_id for a in upstream]);wh.new(FOLDER/'handoff.json',{**store.context(handoff,writer.call_id),'original_coding_author':original,'rebind_reason':'source numerical P2 binds logical folder execution; confirmed workflow and writing bind durable execution UUID; original P2 unchanged'})
    art=upstream+[artifact(a,k,FOLDER/p,writer) for a,k,p in [('outline','outline','outline.json'),('citations','source','citations.json'),('writer_context','input','writer-context.json'),('figure_catalog','figure_selection','figure-catalog.json'),('figure_consent','input','figure-selection-review.json'),('figure_policy','input','user-figure-policy.json'),('q1_reference','input','previous-question-reference.json'),('confirmed_source','input','confirmed-source-status.json'),('evidence_chain','input','evidence-chain.json')]]
    key=store.freeze(Snapshot(binding=writer.binding,hand='writing',artifacts=art,lineage_call_ids=lineage+[writer.call_id]))
    files=[ROOT/a.path for a in art]+[consent/'result-approval.json',consent/'figure-approval.json',f/'frozen-artifacts.json',f/'P2-admission.json',q1/'单题论文-中文审阅稿.md',q1/'manuscript-review.json']+sources+[ROOT/d['path'] for d in context['documents']]+[asset_path(ROOT,'resources/paper/workflow.json'),asset_path(ROOT,'resources/paper/chinese-modeling-policy.json')]
    files += [FOLDER/x['path'] for fig in catalog for x in fig['files'].values()]
    wh.new(FOLDER/'run.json',{'binding':binding,'author':writer.model_dump(mode='json'),'source_run':wh.rel(f),'workflow_sha256':context['workflow_sha256'],'W1_snapshot_sha256':key,'inputs':wh.frozen_manifest(sorted(set(files))),'implementation':'Q2 supplied outline/consent adapter; configured supplier API W1 and prose requested separately, no autonomous Writer framework claim'})
    wh.new(FOLDER/'W1-context.json',{'snapshot_sha256':key,'binding':binding,'required_checks':REQUIRED_CHECKS['W1'],'evidence':{a.artifact_id:a.path for a in art},'response_schema':M1Answer.model_json_schema(),'read_only':True,'gate_scope':'claims/evidence/citations/outline before prose'})
    wh.state_write(FOLDER,{'phase':'WAITING_W1','manuscript_review':'pending','figure_selection':'approved_seven','paper_exported':False})
    (asset_path(ROOT,'stage-d/q2-full/current-writing.json')).write_text(json.dumps({'run_dir':wh.rel(FOLDER),'binding':binding,'phase':'WAITING_W1'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Q2_CONFIRM_AND_PREPARE_PASS',flush=True)

def w1():
    with workflow() as w:
        wh.dispatch(FOLDER,'configured-provider-q2-'+uuid.uuid4().hex,w)
    ctx=wh.read(FOLDER/'W1-context.json');evidence={a:wh.read(ROOT/p) for a,p in ctx['evidence'].items()}
    # Use only enumerated, actual pointers for structured evidence references.
    allowed={'outline':['/claims','/sections','/method_limits','/required_precision_disclosure'],'citations':['/references'],'figure_catalog':['/figures','/policy_override'],'event':['/time_interval_s','/active_board_pairs'],'validation':['/checks','/safe_segments'],'precision':['/rounding_disclosure'],'positions_precision':['/ambiguous_coordinates'],'design':['/new_assumptions','/continuous_search'],'selected_handles':['/handles'],'reproduction':['/partitions'],'q1_reference':['/not_reembedded_in_Q2'],'figure_policy':['/user_statement','/minimum_formal']}
    schema=M1Answer.model_json_schema()
    schema['$defs']['Evidence']['properties']['artifact_id']['enum']=list(allowed)
    prompt='你是全新独立只读W1 Reviewer，不是作者。审查长篇正文前的claims/evidence/citations/outline。只返回严格schema JSON，checks恰claims,evidence,citations,outline，每项PASS需引用allowed_evidence_paths中真实成对artifact_id/selector；不要发明路径，不添加issue:null。每段explanation和issue<=300字。独立检验论断仅来自已确认模型和真结果、全程区间认证与本次有限特征横穿、速度左极限和10坐标/24速率六位舍入歧义、引用确实读取。用户明确删去已在第一题出现的两图，保留七幅入文，figure_policy是仅本题有效的明确用户例外，不强迫补图凑数，不将第一题被引用两图重复嵌入。正文需含模型/算法/结果/检验/评价，不能写成工程验收或定理清单。本次W1不宣称已审尚未编写的正文或最终版式；发现实质证据缺口须FAIL/BLOCKED按implementation->coding/model->modeling/writing->writing/explanation->writing/infrastructure->recovery返工，不因作者说明便通过。'
    answer,meta=JsonModel(client=JsonClient()).call(FOLDER,'W1-provider',prompt,{'schema':schema,'allowed_evidence_paths':allowed,'evidence':evidence},max_tokens=4500)
    wh.new(FOLDER/'W1-provider-call.json',meta);wh.new(FOLDER/'W1-response.json',answer)
    with workflow() as w:print(json.dumps(wh.admit(FOLDER,w),ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('step',choices=['prepare','resume','w1']);a=p.parse_args();{'prepare':prepare,'resume':resume_prepare,'w1':w1}[a.step]()
