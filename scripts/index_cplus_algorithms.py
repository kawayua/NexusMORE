"""Build/reuse an isolated algorithm collection with the existing local BGE settings."""
import argparse,json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.algorithm_retrieval import build_index,verify_sources
from modelcrew.retrieval import LocalBge
from qdrant_client import QdrantClient

def main():
    p=argparse.ArgumentParser();p.add_argument('--settings',type=Path,default=ROOT/'stage-c/runs/retrieval-index.json');p.add_argument('--output',type=Path,default=ROOT/'stage-c-plus/runs/algorithm-index.json');args=p.parse_args()
    catalog=json.loads((ROOT/'stage-c-plus/algorithm-catalog.json').read_text(encoding='utf-8'));verify_sources(catalog)
    settings=json.loads(args.settings.read_text(encoding='utf-8'));model=LocalBge(settings['model_path']);client=QdrantClient(url=settings['qdrant_url'],timeout=30)
    try:collection=build_index(catalog,model,client)
    finally:client.close()
    config={'model_path':settings['model_path'],'qdrant_url':settings['qdrant_url'],'embedding_signature':model.signature,'collection':collection,'catalog_path':'stage-c-plus/algorithm-catalog.json','catalog_sha256':catalog['catalog_sha256']}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'collection':collection,'cards':len(catalog['cards']),'output':str(args.output)}))

if __name__=='__main__':main()
