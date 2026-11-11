"""Human-authored fault probes, executed only inside restricted solver container."""
import json,runpy,hashlib
from pathlib import Path
ns=runpy.run_path('/work/solver.py',run_name='probe_only')
g=ns['main'].__globals__
report={'probe_type':'fault_injection_not_physical_case','checks':{}}
original=g['DENOM_TOL'];g['DENOM_TOL']=1e100
try:
    g['main']()
except SystemExit as e:
    data=json.loads(Path('/work/output/checks.json').read_text())
    report['checks']['near_zero_guard_fail_closed']={'passed':e.code==2 and 'singular velocity recurrence' in data.get('error','') and all(c['status']=='unknown' for c in data['checks'].values()),'exit_code':e.code,'error':data.get('error'),'reported_statuses':{k:v['status'] for k,v in data['checks'].items()}}
else:report['checks']['near_zero_guard_fail_closed']={'passed':False}
g['DENOM_TOL']=original
original_gap=g['GAP'][1];g['GAP'][1]=1e6
try:
    g['main']()
except SystemExit as e:
    data=json.loads(Path('/work/output/checks.json').read_text())
    report['checks']['impossible_bracket_fail_closed']={'passed':e.code==2 and 'chord bracket infeasible' in data.get('error','') and all(c['status']=='unknown' for c in data['checks'].values()),'exit_code':e.code,'error':data.get('error'),'reported_statuses':{k:v['status'] for k,v in data['checks'].items()}}
else:report['checks']['impossible_bracket_fail_closed']={'passed':False}
g['GAP'][1]=original_gap
report['passed']=all(x['passed'] for x in report['checks'].values())
report['code_sha256']=hashlib.sha256(Path('/work/solver.py').read_bytes()).hexdigest()
Path('/work/output/fault-probes.json').write_text(json.dumps(report,indent=2))
if not report['passed']:raise SystemExit(1)
