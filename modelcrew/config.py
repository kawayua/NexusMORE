"""Configuration for stage B, never print connection strings or secrets."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
def database_url():
    value=os.environ.get('MODELCREW_DATABASE_URL')
    if value:return value
    p=ROOT/'stage-b/.env'
    if p.exists():
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            if line.startswith('MODELCREW_DATABASE_URL='):return line.split('=',1)[1].strip()
    raise RuntimeError('Stage B database URL missing; see stage-b/README.md')
