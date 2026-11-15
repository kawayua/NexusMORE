from modelcrew.project_assets import asset_path
import json,xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.inputs import file_hash
from modelcrew.artifacts import snapshot_artifacts
from modelcrew.workflow import Workflow

stamp='20261106';stage=asset_path(ROOT,'stage-b')
production=json.loads((stage/f'stage-b-production-audit-{stamp}.json').read_text(encoding='utf-8'))
search=json.loads((stage/f'historical-artifact-copy-search-{stamp}.json').read_text(encoding='utf-8'))
recovered=[]
for expected in search['matched_hashes']:
    match=next(m for m in search['matching_copies'] if m['registered_sha256']==expected)
    frozen=snapshot_artifacts([{'path':match['path'],'sha256':expected,'role':'recovered_original_confirmed_workbook'}])[0]
    assert file_hash(ROOT/frozen['path'])==expected
    recovered.append({**match,'archive_path':frozen['path'],'archive_sha256':expected,'original_registered_path_changed':True,'database_history_rewritten':False})
(stage/f'historical-evidence-recovery-{stamp}.json').write_text(json.dumps({'date':datetime.now().astimezone().isoformat(),'recovered':recovered,'unmatched_hashes':search['missing_hashes'],'original_paths_overwritten':False,'new_user_confirmations':0},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
xml_path=stage/'runs/stage-b-final-acceptance-20261106.xml';xml=ET.parse(xml_path).getroot();suites=list(xml.iter('testsuite'))
counts={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ['tests','failures','errors','skipped']}
assert counts=={'tests':76,'failures':0,'errors':0,'skipped':0},counts
version=json.loads((stage/'version-recovery-verification.json').read_text(encoding='utf-8'))
executor=json.loads((stage/'executor-review-verification.json').read_text(encoding='utf-8'))
assert version['passed'] and executor['passed'] and version['database_restarts']==3 and executor['database_restarts']==2
with Workflow() as w:
    t=w.task('dragon-q1')
    assert t['current_version']==2 and t['result_revision']==2 and t['phase']=='COMPLETED'
    assert len(w.versions('dragon-q1'))==2
    assert w.db.execute("SELECT count(*) AS n FROM mc_events WHERE task_id=%s AND kind IN ('model_approve','result_approve')",('dragon-q1',)).fetchone()['n']==4
criteria=[
 {'id':'B1','requirement':'契约、字段说明、输入输出结构与合法/非法样例；结构与数学审核分离','status':'passed','evidence':['contracts/model-contract-1.0.0.schema.json','contracts/model-contract-1.1.0.schema.json','contracts/input-templates-1.0.0.json','contracts/README.md','tests/test_contracts.py','tests/test_inputs.py'],'scope':'Schema可验证结构，数学状态不自动转passed；输入歧义阻止新格式方案确认。'},
 {'id':'B2','requirement':'PostgreSQL业务记录、版本、指导、确认、执行与产物关系','status':'passed_with_historical_exception','evidence':['migrations/001_stage_b.sql','migrations/003_version_dossiers.sql','migrations/004_execution_receipts.sql','migrations/005_version_executor_settings.sql',f'stage-b/stage-b-production-audit-{stamp}.json'],'scope':'关联与不可变机制通过；旧固定样例Excel原字节仍有H1例外，历史档案补录列H2。'},
 {'id':'B3','requirement':'LangGraph双人工关卡与可替换执行接口','status':'passed','evidence':['modelcrew/workflow.py','modelcrew/executors.py','modelcrew/dispatch.py','docs/execution-and-interpretation-review.md'],'scope':'三类内置后端、CLI配置、按版本绑定回执；未确认不派发；结果不明先恢复查询。固定样例与真实solver明确区分。'},
 {'id':'B4','requirement':'CLI查看、确认、指导修改、拒绝、幂等与过期版本检查','status':'passed','evidence':['modelcrew/__main__.py','tests/test_workflow.py'],'scope':'重复/并发/过期请求、拒绝不推进、事务失败回滚及原始graph resume绕过拦截通过；actor仍是本地审计标签。'},
 {'id':'B5','requirement':'修改影响范围、解释复用计算并重审、等待点及跨事务恢复','status':'passed','evidence':['modelcrew/reviews.py','contracts/interpretation-claims-1.0.0.schema.json','stage-b/version-recovery-verification.json','stage-b/executor-review-verification.json'],'scope':'新模型或执行配置创建新待确认版本；解释修改复用execution_id，审核失败阻止确认，unknown需明确人工审阅；规范结构断言可通过。'},
 {'id':'B6','requirement':'初稿→用户补充→新契约→确认→求解/联调→结果确认的完整演练','status':'passed','evidence':['stage-b/method-comparison.md','stage-b/v2-confirmation.md','stage-b/v2-result-confirmation.json',f'stage-b/stage-b-production-audit-{stamp}.json','stage-b/executor-review-verification.json'],'scope':'实际v1/v2交互历史和v2既有受控求解保留；本次新演练是模拟用户+固定证据，不是新LLM或新求解。'}]
source_paths=sorted({*ROOT.glob('modelcrew/*.py'),*ROOT.glob('migrations/*.sql'),*ROOT.glob('tests/*.py'),asset_path(ROOT,'contracts/model-contract-1.0.0.schema.json'),asset_path(ROOT,'contracts/model-contract-1.1.0.schema.json'),asset_path(ROOT,'contracts/input-templates-1.0.0.json'),asset_path(ROOT,'contracts/interpretation-claims-1.0.0.schema.json')})
report={'date':datetime.now().astimezone().isoformat(),'stage':'B','conclusion':'conditional_pass','functional_conclusion':'passed_with_documented_scope','unconditional_closeout':False,
 'basis':'modelcrew-agent-plan.md / 阶段B：契约与人工关卡，及用户确认的输入结构、版本档案与回退补充要求',
 'tests':counts,'pytest_duration_seconds':sum(float(s.attrib.get('time',0)) for s in suites),'pytest_command':'python -m pytest tests --integration -q --junitxml=stage-b/runs/stage-b-final-acceptance-20261106.xml',
 'restart_drills':{'total_restarts':5,'version_recovery':version,'executor_review':executor},'criteria':criteria,
 'production_snapshot':production,'evidence_recovery':recovered,
 'findings':[
 {'id':'H1','status':'open','category':'historical_evidence_integrity','blocks_unconditional_closeout':True,'description':'历史固定样例的result1.xlsx原字节副本在本次本地搜索范围内仍未找到；两个fixture执行引用受影响。当前数值检查通过不替代原字节身份。','required_followup':'优先从备份找回匹配原哈希的文件；若无法找回，保留原登记与异常，以显式例外归档或新版本新产物及独立用户确认完成替代，不能覆盖原哈希或沿用旧确认伪装修复。'},
 {'id':'H1R','status':'matching_original_archived','category':'recovered_v2_evidence','blocks_unconditional_closeout':False,'description':'v2真实solver的原确认Excel在旧validator-test目录找到8份同哈希副本，已保存一份内容寻址副本；数据库原登记路径未改，恢复映射在报告中留痕。'},
 {'id':'H2','status':'pending_historical_backfill','category':'historical_version_dossiers','blocks_unconditional_closeout':False,'description':'正式dragon-q1的mc_version_entries为0；旧方案/代码/反馈部分在原始文件和事件中可追溯，尚未统一回填新档案。不能把可记录能力通过描述成历史资料已全部补录。','required_followup':'从实际原文和产物追加带来源的历史档案；没有原文的项标缺失，不伪造Agent原始思路或下一步。'},
 {'id':'N1','status':'not_live_validated','category':'new_draft_generation_extension','blocks_unconditional_closeout':False,'description':'自动完整契约草稿接口仅通过模拟API测试，本轮未真实调用模型；原计划B的人机修订已有实际v2历史证据，不能把新增草稿真实调用另设为原计划强制项。'},
 {'id':'N2','status':'scope_limit','category':'semantic_review','blocks_unconditional_closeout':False,'description':'自动审核验证结构化数值断言及证据，任意自由文字保持unknown并要求人工审阅；非通用自然语言数学证明。'},
 {'id':'N3','status':'not_clean_deployment_tested','category':'reproducibility','blocks_unconditional_closeout':False,'description':'本次为现有Windows+Docker+本地数据库环境验收；运行缓存被Git忽略，未验证Gitee干净检出部署、Web/API、MCP或真实论文生成。'}],
 'new_real_model_calls':0,'new_real_solver_runs':0,'new_real_user_confirmations':0,
 'evidence_files':{str(p.relative_to(ROOT)):file_hash(p) for p in [xml_path,stage/f'stage-b-production-audit-{stamp}.json',stage/'version-recovery-verification.json',stage/'executor-review-verification.json',stage/f'historical-artifact-copy-search-{stamp}.json',stage/f'historical-evidence-recovery-{stamp}.json']},
 'source_hashes':{str(p.relative_to(ROOT)):file_hash(p) for p in source_paths}}
(stage/f'stage-b-acceptance-{stamp}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
print(json.dumps({'conclusion':report['conclusion'],'tests':counts,'database_restarts':5,'v2_original_workbook_archived':len(recovered)==1,'open_unconditional_closeout_findings':['H1'],'json_report':f'stage-b/stage-b-acceptance-{stamp}.json'},ensure_ascii=False,indent=2))
