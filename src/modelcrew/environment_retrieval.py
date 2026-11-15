"""Prepare local embedding weights and a tiny real retrieval index, not algorithm routing."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
from . import config
from .package_resources import resource
from .service_environment import _root,_path,_write,_lock,_sha,_state,EnvironmentError


def embedding(root=None,*,source=None,offline=False):
    root=_root(root);spec=json.loads(resource('environment/native-tools.json').read_text(encoding='utf-8'))['embedding']
    with _lock(root):
        destination=_path(root,'models/bge-base-zh-v1.5');receipt=_path(root,'embedding-model.json')
        if receipt.exists():
            previous=json.loads(receipt.read_text(encoding='utf-8'))
            if not all(_sha(destination/name)==identity for name,identity in previous['files'].items()):raise EnvironmentError('Prepared embedding weights changed')
            return {'status':'prepared','model_directory':str(destination),'retained':True,'signature':previous['signature']}
        if config.configured('MODELCREW_EMBEDDING_MODEL',root=root):raise EnvironmentError('Explicit embedding model already configured; do not replace it automatically')
        destination.mkdir(parents=True,exist_ok=True)
        if source is not None:
            source=Path(source).resolve(strict=True)
            for name in spec['files']:
                original=source/name;target=_path(root,'models/bge-base-zh-v1.5/'+name)
                if not original.is_file():raise EnvironmentError('Supplied embedding directory lacks required model files')
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():
                    if _sha(target)!=_sha(original):raise EnvironmentError('Partial embedding copy differs; refusing overwrite')
                else:
                    with original.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
                if _sha(target)!=_sha(original):raise EnvironmentError('Embedding copy verification failed')
            source_kind='explicit_local_directory_not_upstream_attestation'
        else:
            if offline:raise EnvironmentError('No prepared embedding weights offline; supply --model or prepare once online')
            from huggingface_hub import snapshot_download
            try:snapshot_download(spec['repo_id'],revision=spec['revision'],allow_patterns=spec['files'],local_dir=destination,
                cache_dir=_path(root,'huggingface-cache'))
            except Exception:raise EnvironmentError('Embedding download incomplete; retry the same pinned revision explicitly or supply verified local files') from None
            source_kind='huggingface_pinned_revision'
        from .retrieval import LocalBge
        model=LocalBge(destination)
        files={name:_sha(destination/name) for name in spec['files']}
        current=config.load_settings(root);current['retrieval']['model_path']=destination.relative_to(root).as_posix()
        settings=config.settings_path(root)
        if settings!=root/'configs/local/settings.json':raise EnvironmentError('Embedding binding requires workspace-local settings')
        _write(_path(root,'settings.before-embedding.json'),settings.read_text(encoding='utf-8'))
        temporary=_path(root,'settings.embedding.tmp');_write(temporary,current);os.replace(temporary,settings)
        _write(receipt,{'schema_version':'1.0.0','repo_id':spec['repo_id'],'revision':spec['revision'],'source_kind':source_kind,
            'files':files,'signature':model.signature,'dimension':model.dimension,'semantic_quality_verified':False})
    return {'status':'prepared','model_directory':str(destination),'signature':model.signature,'dimension':model.dimension,
        'retained':False,'source_kind':source_kind,'semantic_quality_verified':False}


def initialize(output,root=None):
    root=_root(root);state=_state(root)
    from .environment_probe import _output
    folder=_output(root,output)
    model_path=config.configured('MODELCREW_EMBEDDING_MODEL',root=root)
    if not model_path:raise EnvironmentError('Prepare local embedding weights first')
    from .retrieval import LocalBge,ingest,Retriever
    from .contracts import digest
    from qdrant_client import QdrantClient
    model=LocalBge(root/Path(model_path))
    texts=['线性规划以线性目标与线性等式或不等式约束建立模型，求解前必须检查可行性。',
           '河流流量监测使用时间序列描述水位和流速变化。',
           '论文导出需要中文字体与完整的 PDF 页面检查。']
    documents=[];chunks=[]
    for i,text in enumerate(texts):
        identifier='environment-reference-'+str(i);sha=hashlib.sha256(text.encode()).hexdigest()
        documents.append({'id':identifier,'source_sha256':sha,'source_kind':'project_authored_synthetic_reference','text':text})
        chunks.append({'record_type':'chunk','doc_id':identifier,'chunk_id':digest({'id':identifier,'text':text}),
            'text':text,'title':'Synthetic environment reference '+str(i),'kind':'algorithm','year':2026,'case_id':None,
            'same_problem_reference':False,'source_url':None,'source_sha256':sha,'parser':'environment-text-1.0.0',
            'locator':{'label':'Project-authored synthetic text','paragraph':1}})
    corpus={'schema_version':'1.0.0','documents':documents,'chunks':chunks};corpus['corpus_sha256']=digest({'documents':documents,'chunks':chunks})
    _write(folder/'corpus.json',corpus)
    endpoint=f'http://127.0.0.1:{state["qdrant_port"]}'
    with closing(QdrantClient(url=endpoint,timeout=30)) as client:
        collection=ingest(client,model,corpus)
        answer=Retriever(client,model,collection,corpus['corpus_sha256']).search('线性规划的目标和约束需要满足哪些条件？',limit=1)
        if not answer['hits'] or answer['hits'][0]['doc_id']!='environment-reference-0':raise EnvironmentError('Tiny retrieval smoke failed; do not mark the index usable')
    index={'collection':collection,'qdrant_url':endpoint,'model_path':str(model.path),'embedding_signature':model.signature,
        'embedding_identity':model.identity,'corpus_sha256':corpus['corpus_sha256'],'chunk_count':len(chunks)}
    _write(folder/'index.json',index);_write(folder/'query.json',answer)
    settings=config.load_settings(root)
    bound=False
    if not config.configured('MODELCREW_RETRIEVAL_CONFIG',root=root):
        path=config.settings_path(root)
        if path!=root/'configs/local/settings.json':raise EnvironmentError('Index binding requires workspace-local settings')
        _write(_path(root,'settings.before-retrieval-probe.json'),path.read_text(encoding='utf-8'))
        settings['retrieval']['paper_config']=(folder/'index.json').relative_to(root).as_posix()
        temporary=_path(root,'settings.retrieval.tmp');_write(temporary,settings);os.replace(temporary,path);bound=True
    result={'status':'passed','collection':collection,'dimension':model.dimension,'chunks':len(chunks),'index':str(folder/'index.json'),
        'bound_as_paper_index':bound,'query_expected_first_hit':True,'scope':'Three synthetic references and real local BGE/Qdrant; not production semantic quality, 113-algorithm indexing or automatic routing'}
    _write(folder/'retrieval.json',result);return result
