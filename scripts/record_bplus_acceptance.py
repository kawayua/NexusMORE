"""Freeze B+ evidence after real tests and read-only production comparisons."""
from modelcrew.project_assets import asset_path
import json,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.inputs import file_hash
from modelcrew.mathematics import validate_package
from modelcrew.contracts import validate,digest

def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def main():
    base=asset_path(ROOT,'stage-b-plus')
    def junit(path):
        suites=list(ET.parse(base/path).getroot().iter('testsuite'))
        return {**{k:sum(int(s.get(k,'0')) for s in suites) for k in ['tests','errors','failures','skipped']},'seconds':sum(float(s.get('time','0')) for s in suites),'path':'stage-b-plus/'+path,'sha256':file_hash(base/path)}
    local=junit('runs/bplus-tests-diff-final.xml');full=junit('runs/full-regression-complete.xml')
    for test in [local,full]:assert test['errors']==test['failures']==test['skipped']==0
    assert local['tests']==46 and full['tests']==227
    summary=read('stage-b-plus/verification-summary.json');assert file_hash(ROOT/summary['report_path'])==summary['report_sha256']
    demo=read(summary['report_path']);assert len(demo['checks'])==22 and all(c['passed'] for c in demo['checks'])
    assert demo['production_before']==demo['production_after']
    assert demo['production_after']['task']['current_version']==2 and demo['production_after']['task']['result_revision']==2 and demo['production_after']['math_packages']==0
    for name in ['bench-dragon','resource']:
        c=read('stage-b-plus/examples/'+('contract-v2-snapshot.json' if name=='bench-dragon' else 'resource-contract.json'));validate(c)
        validate_package(read(f'stage-b-plus/examples/valid-{name}.json'),c)
    # Original A+ baseline and all its frozen artifacts remain valid.
    aplus=read('stage-a-plus/acceptance.json')
    for group in ['artifact_sha256','code_sha256']:
        for path,sha in aplus[group].items():assert file_hash(ROOT/path)==sha,path
    progress={'stage':'B+','date':'2026-11-06','status':'implemented_and_verified','engineering_acceptance':'passed_in_declared_scope','user_acceptance':'not_recorded','schema_versions':{'MethodSelection':'1.0.0','MathematicalDossier':'1.0.0','MathematicalPackage':'1.0.0'},'migration':7,'specialized_tests_passed':46,'full_regression_passed':227,'durable_demo_checks_passed':22,'formal_task_changed':False,'new_model_calls':0,'new_contest_solver_runs':0,'real_latex_compile_render':'deferred_to_C+','figures_generated':False,'report':'stage-b-plus/acceptance-report.md','next':'C+ algorithm retrieval supplement, figures and real mathematical export; not implemented in this task'}
    (base/'progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    criteria=[{'id':'B+1','requirement':'Versioned method/dossier/package schemas and stable semantic IDs','status':'passed','evidence':['contracts/method-selection-1.0.0.schema.json','contracts/mathematical-dossier-1.0.0.schema.json','contracts/mathematical-package-1.0.0.schema.json']},{'id':'B+2','requirement':'Readable proposal from canonical math, with contract cross-references','status':'passed','evidence':['stage-b-plus/proposals/bench-dragon.md','stage-b-plus/proposals/resource.md','tests/test_mathematics.py']},{'id':'B+3','requirement':'Contract/math/user-confirmation/result snapshot binding','status':'passed','evidence':['migrations/007_mathematical_packages.sql','modelcrew/mathematics.py','tests/test_mathematics_workflow.py',summary['report_path']]},{'id':'B+4','requirement':'Math invalidation, restricted presentation edits, visible version math differences','status':'passed','evidence':['modelcrew/workflow.py','modelcrew/versions.py','tests/test_mathematics_workflow.py']},{'id':'B+5','requirement':'Old schemas/hashes and historical confirmations remain valid','status':'passed','evidence':['stage-b-plus/examples/contract-v2-snapshot.json',summary['report_path']]},{'id':'B+6','requirement':'Transactions, rollback, idempotency, immutable audit and process recovery','status':'passed','evidence':['tests/test_mathematics_workflow.py',local['path'],full['path'],summary['report_path']]}]
    report={'stage':'B+','created_at':datetime.now(timezone.utc).isoformat(),'status':'implemented_and_verified','engineering_acceptance':'passed_in_declared_scope','user_acceptance':'not_recorded','criteria':criteria,'specialized_tests':local,'full_regression':full,'durable_demo':summary,'formal_task_read_only_recheck':demo['production_after'],'A+_frozen_artifacts_rechecked':True,'new_model_calls':0,'new_contest_solver_runs':0,'simulated_test_actors':True,'latex_compiled':False,'figures_generated':False,'historical_schema_sha256':{f'contracts/model-contract-{v}.schema.json':file_hash(asset_path(ROOT,f'contracts/model-contract-{v}.schema.json')) for v in ['1.0.0','1.1.0']},'known_limits':['No general proof/LaTeX semantic equivalence engine; schema-valid 1=2 counterexample is explicitly retained.','Only explicit equation_spacing presentation setting is exempt; symbol renames and formula edits are conservatively semantic.','Math revisions conservatively rerun confirmation/execution; finer proof-only impact analysis is not implemented.','Local trusted API retains audit-label actors rather than authentication.','No new real-model draft generation, independent second math reviewer, graphical frontend, C+ compilation/rendering or figures.','Existing fixed-fixture Excel exception is preserved.'],'earlier_attempts':[{'path':'stage-b-plus/runs/bplus-tests.xml','result':'25 passed, 16 setup errors: missing runs parent directory'},{'path':'stage-b-plus/runs/bplus-tests-retry.xml','result':'25 passed, 16 setup errors: actual JSONB canonical rendering defect; fixed with sorted semantic JSON'},{'path':'stage-b-plus/runs/bplus-tests-canonical.xml','result':'41 passed'},{'path':'stage-b-plus/runs/full-regression.xml','result':'222 passed before five additional boundary tests'},{'path':'stage-b-plus/runs/full-regression-final.xml','result':'227 passed before adding explicit math-diff display assertion'}]}
    files=[p for p in base.rglob('*') if p.is_file() and 'runs' not in p.relative_to(base).parts and p.name!='acceptance.json']
    report['artifact_sha256']={str(p.relative_to(ROOT)):file_hash(p) for p in files}
    names=['modelcrew/mathematics.py','modelcrew/workflow.py','modelcrew/versions.py','modelcrew/api.py','modelcrew/__main__.py','tests/test_mathematics.py','tests/test_mathematics_workflow.py','tests/conftest.py','scripts/prepare_bplus_examples.py','scripts/verify_bplus_handoff.py','scripts/record_bplus_acceptance.py','migrations/007_mathematical_packages.sql','contracts/method-selection-1.0.0.schema.json','contracts/mathematical-dossier-1.0.0.schema.json','contracts/mathematical-package-1.0.0.schema.json','docs/mathematical-handoff.md']
    report['implementation_sha256']={p:file_hash(ROOT/p) for p in names}
    (base/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stage':'B+','status':report['status'],'specialized_tests':local['tests'],'full_tests':full['tests'],'demo_checks':22,'A+_unchanged':True,'formal_task_unchanged':True},ensure_ascii=False))
if __name__=='__main__':main()
