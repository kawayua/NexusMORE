"""Prepare/start the dedicated Compose database without exposing credentials."""
from pathlib import Path
from secrets import token_hex
import subprocess
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'stage-b/.env'
if not p.exists():
    password=token_hex(24)
    p.write_text(f'MODELCREW_DB_PASSWORD={password}\nMODELCREW_DATABASE_URL=postgresql://modelcrew:{password}@127.0.0.1:55432/modelcrew\n',encoding='utf-8')
subprocess.run(['docker','version','--format','{{.Server.Version}}'],check=True,timeout=15)
subprocess.run(['docker','compose','--env-file',str(p),'-f',str(ROOT/'stage-b/compose.yaml'),'up','-d','--wait','--wait-timeout','60'],check=True,timeout=120)
print('Dedicated stage B database started; credential values are not displayed.')
