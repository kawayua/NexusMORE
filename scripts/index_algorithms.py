"""Explicit legacy vector-index maintenance; installed algorithm lookup needs no index build."""
import argparse,json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.retrieval_paths import algorithm_config_path,algorithm_catalog_path
from modelcrew.algorithm_retrieval import build_index,verify_sources
from modelcrew.retrieval import LocalBge
from qdrant_client import QdrantClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',type=Path,required=True)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output or algorithm_config_path(ROOT)
    if output.exists():
        raise FileExistsError('Index configuration already exists; choose a new output version')
    catalog_path=algorithm_catalog_path(ROOT,args.catalog)
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'));verify_sources(catalog)
    settings=json.loads(algorithm_config_path(ROOT,args.settings).read_text(encoding='utf-8'))
    model=LocalBge(settings['model_path']);client=QdrantClient(url=settings['qdrant_url'],timeout=30)
    try:
        collection=build_index(catalog,model,client)
    finally:
        client.close()
    config={'model_path':settings['model_path'],'qdrant_url':settings['qdrant_url'],
            'embedding_signature':model.signature,'collection':collection,
            'catalog_path':catalog_path.relative_to(ROOT).as_posix(),'catalog_sha256':catalog['catalog_sha256']}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(config,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'collection':collection,'cards':len(catalog['cards']),'output':str(output)}))


if __name__=='__main__':
    main()
