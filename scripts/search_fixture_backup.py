"""Read-only search of likely local backups for an exact historical workbook hash."""
from modelcrew.project_assets import asset_path
import os,json,time
from pathlib import Path
from datetime import datetime
from modelcrew.config import ROOT
from modelcrew.inputs import file_hash
TARGET='d86a15905d3dc16658508adb5082bfc8d4688da64b7bda744165c94cf79168a4'
profile=Path(os.environ['USERPROFILE'])
roots=[profile/'Downloads',profile/'Documents',profile/'OneDrive',Path('D:/big-scend-up'),Path('D:/big-third-up/pythoncalculate'),Path('D:/big-third-up/CUMC')]
counts={};matches=[];errors=[];start=time.monotonic()
for root in roots:
    count=0
    if not root.exists():continue
    for base,dirs,names in os.walk(root,followlinks=False,onerror=lambda e:errors.append(str(e))):
        dirs[:]=[d for d in dirs if d not in ['node_modules','.git','.venv','venv','__pycache__']]
        for name in names:
            if not name.lower().endswith(('.xlsx','.xlsm','.bak')):continue
            path=Path(base)/name
            try:
                if path.stat().st_size>20*1024*1024:continue
                count+=1
                if file_hash(path)==TARGET:matches.append(str(path))
            except OSError as exc:errors.append(str(exc))
    counts[str(root)]=count
result={'date':datetime.now().astimezone().isoformat(),'target_sha256':TARGET,'roots_examined':counts,'exact_matches':matches,'read_errors':errors,'elapsed_seconds':time.monotonic()-start,'source_files_changed':False}
folder=asset_path(ROOT,'stage-b/runs')/('fixture-recovery-'+datetime.now().strftime('%Y%m%dT%H%M%S'));folder.mkdir(parents=True)
(folder/'extended-backup-search.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'report':str(folder/'extended-backup-search.json'),'roots_examined':counts,'exact_matches':matches,'read_error_count':len(errors),'elapsed_seconds':result['elapsed_seconds']},ensure_ascii=False,indent=2))
