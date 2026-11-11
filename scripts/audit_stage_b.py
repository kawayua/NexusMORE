"""Read-only audit of the stage-B production demonstration and current files."""
import json
from datetime import datetime
from pathlib import Path
import numpy as np
from openpyxl import load_workbook
from modelcrew.config import ROOT
from modelcrew.workflow import Workflow
from modelcrew.contracts import digest,validate,SCHEMAS
from modelcrew.inputs import file_hash
from modelcrew.reviews import artifact_status
from jsonschema import Draft202012Validator

def main():
    for schema in SCHEMAS.values():Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(json.loads((ROOT/'contracts/interpretation-claims-1.0.0.schema.json').read_text(encoding='utf-8')))
    with Workflow() as w,w.lock('dragon-q1'),w.db.transaction():
        w.db.execute('SET TRANSACTION READ ONLY')
        state=w.inspect('dragon-q1');contracts=w.db.execute('SELECT * FROM mc_contracts WHERE task_id=%s ORDER BY version',('dragon-q1',)).fetchall()
        executions=w.db.execute('SELECT * FROM mc_executions WHERE task_id=%s ORDER BY created_at',('dragon-q1',)).fetchall()
        results=w.db.execute('SELECT * FROM mc_results WHERE task_id=%s ORDER BY version,revision',('dragon-q1',)).fetchall()
        entries=w.db.execute('SELECT version,kind,actor,created_at FROM mc_version_entries WHERE task_id=%s ORDER BY created_at',('dragon-q1',)).fetchall()
        summaries=w.db.execute('SELECT * FROM mc_summaries WHERE task_id=%s ORDER BY version,revision',('dragon-q1',)).fetchall()
        confirmations=[e for e in state['events'] if e['kind'] in ['model_approve','result_approve']]
        migrations=[x['version'] for x in w.db.execute('SELECT version FROM mc_migrations ORDER BY version').fetchall()]
    contract_checks=[];inputs=[];artifact_checks=[]
    for c in contracts:
        validate(c['content'])
        contract_checks.append({'version':c['version'],'sha256':c['sha256'],'structure_valid':True,'hash_valid':digest(c['content'])==c['sha256'],'parent_version':c['parent_version'],'legacy_executor_config_unspecified':c['executor_key'] is None})
        for item in c['content']['inputs']:inputs.append({'version':c['version'],'input_id':item['id'],'path':item['path'],'status':artifact_status(item)})
    by_version={c['version']:c for c in contracts}
    for execution in executions:
        for a in execution['artifacts']:artifact_checks.append({'version':execution['version'],'execution_id':str(execution['id']),'mode':execution['mode'],'path':a['path'],'registered_sha256':a['sha256'],'current_sha256':file_hash(ROOT/a['path']) if (ROOT/a['path']).is_file() else None,'status':artifact_status(a)})
    with np.load(ROOT/'stage-a/2024-A-problem-1/runs/reference-20261101T124835482890Z/trajectories.npz',allow_pickle=False) as known:
        reference={'位置':known['position_m'].transpose(1,2,0).reshape(448,301),'速度':known['speed_m_s'].T}
    numeric=[]
    for relative in ['stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z','stage-b/runs/solver-v2-20261104T131332959555Z']:
        folder=ROOT/relative;book=folder/'output/result1.xlsx';wb=load_workbook(book,read_only=True,data_only=True)
        with np.load(folder/'output/trajectories.npz',allow_pickle=False) as data:own={'位置':data['position_m'].transpose(1,2,0).reshape(448,301),'速度':data['speed_m_s'].T}
        checks=[]
        for title,expected in own.items():
            rows=list(wb[title].iter_rows(min_row=2,min_col=2));values=np.asarray([[x.value for x in row] for row in rows],dtype=float)
            rounding=float(np.max(np.abs(values-expected)));vs_reference=float(np.max(np.abs(values-reference[title])))
            checks.append({'sheet':title,'shape':list(values.shape),'max_roundtrip_error':rounding,'roundtrip_limit':5.00001e-7,'max_reference_error':vs_reference,'reference_limit':1e-6,'format_six_decimals':all(cell.number_format=='0.000000' for row in rows for cell in row),'passed':bool(np.all(np.isfinite(values)) and rounding<=5.00001e-7 and vs_reference<=1e-6)})
        wb.close();numeric.append({'path':str(book.relative_to(ROOT)),'current_sha256':file_hash(book),'checks':checks})
    binding=all(e['contract_sha256']==by_version[e['version']]['sha256'] for e in executions)
    task={k:state['task'][k] for k in ['id','current_version','result_revision','phase','model_approved','result_approved','execution_id','thread_id']}
    report={'date':datetime.now().astimezone().isoformat(),'audit_mode':'read_only_production_task_and_files','task':task,'checkpoint_next':state['checkpoint_next'],'migrations':migrations,'contracts':contract_checks,'inputs':inputs,'execution_count':len(executions),'result_count':len(results),'summary_count':len(summaries),'confirmation_count':len(confirmations),'confirmations':confirmations,'execution_contract_bindings_valid':binding,'artifacts':artifact_checks,'artifact_issues':[a for a in artifact_checks if a['status']!='verified'],'current_numeric_recheck':numeric,'current_numeric_passed':all(c['passed'] and c['format_six_decimals'] for b in numeric for c in b['checks']),'historical_version_entries':entries,'historical_missing_archive_sections':{str(v):[k for k in ['proposal','feedback','next_step','code','experiment'] if not any(e['version']==v and e['kind']==k for e in entries)] for v in [1,2]},'new_model_calls':0,'new_solver_runs':0,'new_real_user_confirmations':0}
    out=ROOT/'stage-b/stage-b-production-audit-20261106.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({'task':task,'execution_count':len(executions),'artifact_issue_references':len(report['artifact_issues']),'distinct_changed_files':len({a['path'] for a in report['artifact_issues']}),'numeric_recheck_passed':report['current_numeric_passed'],'historical_entry_count':len(entries),'report':str(out)},ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()

