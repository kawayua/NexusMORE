"""Start the local database while preserving the existing Compose project/volume."""
import argparse
from pathlib import Path
from secrets import token_hex
import subprocess
from modelcrew.config import ROOT, database_env_file


def compose_command(root, env_file, *, check=False):
    return ['docker','compose','-p','stage-b','--env-file',str(env_file),
            '-f',str(Path(root)/'configs/services/postgres.yaml'),
            *(['config','--quiet'] if check else ['up','-d','--wait','--wait-timeout','60'])]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-config',action='store_true',help='Validate configuration without starting containers')
    args=parser.parse_args()
    path=database_env_file()
    if not path.exists():
        if args.check_config:
            raise RuntimeError('Configure the local database environment file first')
        path.parent.mkdir(parents=True,exist_ok=True)
        password=token_hex(24)
        with path.open('x',encoding='utf-8') as stream:
            stream.write(f'MODELCREW_DB_PASSWORD={password}\nMODELCREW_DATABASE_URL=postgresql://modelcrew:{password}@127.0.0.1:55432/modelcrew\n')
    subprocess.run(compose_command(ROOT,path,check=args.check_config),check=True,timeout=120)
    print('Database configuration verified.' if args.check_config else 'Local database started; credentials are not displayed.')


if __name__ == '__main__':
    main()
