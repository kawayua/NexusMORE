"""Compare an isolated MiMo run's exported data with independent reference."""
from modelcrew.project_assets import asset_path
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1];CASE=asset_path(ROOT,'stage-a/2024-A-problem-1')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('run_dir',type=Path);a=ap.parse_args();run=a.run_dir.resolve();out=run/'output'
 refs=sorted(p for p in (CASE/'runs').glob('reference-*') if (p/'trajectories.npz').exists())
 ref=refs[-1];checks={}
 def record(name,passed,**details):checks[name]={'passed':bool(passed),**details}
 with np.load(ref/'trajectories.npz',allow_pickle=False) as r,np.load(out/'trajectories.npz',allow_pickle=False) as m:
  required={'time_s':(301,),'position_m':(301,224,2),'velocity_m_s':(301,224,2),'speed_m_s':(301,224)}
  for name,shape in required.items():
   x=m[name];record(name+'_shape',x.shape==shape,actual_shape=list(x.shape));record(name+'_finite',np.all(np.isfinite(x)))
   if x.shape!=shape:raise ValueError(name+' shape mismatch')
   error=float(np.max(np.abs(x-r[name])))
   tol=0 if name=='time_s' else 1e-6
   record(name+'_reference_error',error<=tol,max_abs_error=error,tolerance=tol)
  pos=m['position_m'];vel=m['velocity_m_s'];speed=m['speed_m_s']
  distances=np.full(223,1.65);distances[0]=2.86
  e=float(np.max(np.abs(np.linalg.norm(np.diff(pos,axis=1),axis=2)-distances)))
  record('rod_distances',e<=1e-8,max_abs_error=e,tolerance=1e-8)
  e=float(np.max(np.abs(np.linalg.norm(vel,axis=2)-speed)))
  record('velocity_speed_consistency',e<=1e-8,max_abs_error=e,tolerance=1e-8)
  expected={'位置':pos.transpose(1,2,0).reshape(448,301),'速度':speed.T}
  wb=load_workbook(out/'result1.xlsx',read_only=True,data_only=True)
  for title,values in expected.items():
   sheet=wb[title];record(title+'_dimensions',(sheet.max_row,sheet.max_column)==(values.shape[0]+1,302))
   data=np.array(list(sheet.iter_rows(min_row=2,min_col=2,max_row=values.shape[0]+1,max_col=302,values_only=True)),dtype=float)
   record(title+'_numeric_complete',np.all(np.isfinite(data)))
   error=float(np.max(np.abs(data-values)));record(title+'_rounding',error<=5.00001e-7,max_abs_error=error,tolerance=5.00001e-7)
   # Every data cell should display six decimal places, not only contain rounded values.
   formats=all(cell.number_format=='0.000000' for row in sheet.iter_rows(min_row=2,min_col=2,max_row=values.shape[0]+1,max_col=302) for cell in row)
   record(title+'_six_decimal_format',formats)
  wb.close()
 passed=all(c['passed'] for c in checks.values())
 report={'run_id':run.name,'reference_run':ref.name,'passed':passed,'checks':checks,'limitation':'Reference agreement is within this fixed case; not a general success-rate estimate.'}
 (run/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
