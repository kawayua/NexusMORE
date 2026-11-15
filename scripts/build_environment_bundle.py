"""Build a private Windows preparation bundle; never publish or include local credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from scripts.build_distribution import build,ROOT


def prepare_bundle(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    report=build(output/'distribution')
    bundle=output/'bundle';bundle.mkdir()
    wheel=Path(report['wheel']['path']);shutil.copyfile(wheel,bundle/wheel.name)
    resources=ROOT/'src/modelcrew/resources/environment'
    for name in ['bootstrap.ps1','native-tools.json']:shutil.copyfile(resources/name,bundle/name)
    lock={'schema_version':'1.0.0','private_distribution':True,'wheel':{'filename':wheel.name,'sha256':report['wheel']['sha256']},
        'native_catalog_sha256':hashlib.sha256((bundle/'native-tools.json').read_bytes()).hexdigest(),
        'bootstrap_sha256':hashlib.sha256((bundle/'bootstrap.ps1').read_bytes()).hexdigest()}
    (bundle/'distribution-lock.json').write_text(json.dumps(lock,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(ROOT/'docs/environment-preparation.md',bundle/'environment-preparation.md')
    for name in ['LICENSE','THIRD_PARTY_NOTICES.md','docs/combined-distribution-license.md','docs/licenses/Apache-2.0.txt']:
        target=bundle/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    archive=output/'nexusmore-0.1.0.dev0-windows-x86_64-private.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as package:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():package.write(path,path.relative_to(bundle).as_posix())
    result={'status':'passed','package_build':report,'bundle':{'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size},
        'lock':lock,'native_binaries_or_model_weights_shipped':False,'public_upload_authorized':False}
    (output/'bundle-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=prepare_bundle(args.output);print(json.dumps({'status':result['status'],'bundle':result['bundle']}))
