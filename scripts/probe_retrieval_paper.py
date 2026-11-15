"""Installed retrieval/paper-group probes; synthetic inputs, no business approval."""
import argparse
import copy
import importlib
import importlib.metadata as md
import importlib.util
import json
import os
from pathlib import Path
import re
import site
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def write(path,data):
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)

def retrieval(out):
    os.environ['HF_HOME']=str(out/'hf-cache');os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
    import numpy as np
    import torch
    torch.set_num_threads(2);torch.manual_seed(17)
    from transformers import BertConfig,BertModel,PreTrainedTokenizerFast
    from tokenizers import BertWordPieceTokenizer
    from sentence_transformers import SentenceTransformer,models as sm
    from qdrant_client import QdrantClient
    from modelcrew.retrieval import LocalBge,ingest,Retriever,RetrievalUnavailable
    from modelcrew.contracts import digest
    from modelcrew.paper_search_mcp import SearchTool
    from modelcrew.paper_discovery import discover
    base=out/'tiny-transformer';base.mkdir()
    vocab=['[PAD]','[UNK]','[CLS]','[SEP]','[MASK]','alpha','beta','network','flow']
    (base/'vocab.txt').write_text(chr(10).join(vocab)+chr(10),encoding='utf-8')
    tokens=BertWordPieceTokenizer(str(base/'vocab.txt'),lowercase=True);tokens.save(str(base/'tokenizer.json'))
    tokenizer=PreTrainedTokenizerFast(tokenizer_file=str(base/'tokenizer.json'),unk_token='[UNK]',pad_token='[PAD]',cls_token='[CLS]',sep_token='[SEP]',mask_token='[MASK]');tokenizer.save_pretrained(base)
    config=BertConfig(vocab_size=len(vocab),hidden_size=16,num_hidden_layers=1,num_attention_heads=2,intermediate_size=32,max_position_embeddings=512)
    BertModel(config).save_pretrained(base,safe_serialization=True)
    encoder=sm.Transformer(str(base),model_args={'local_files_only':True},tokenizer_args={'local_files_only':True})
    model=SentenceTransformer(modules=[encoder,sm.Pooling(16)],device='cpu');model.save(str(out/'synthetic-weights'))
    embedder=LocalBge(out/'synthetic-weights',device='cpu')
    vectors=np.asarray(embedder.encode(['alpha network','beta flow']));assert vectors.shape==(2,16) and np.isfinite(vectors).all() and np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5)
    chunks=[]
    for i in range(3):chunks.append({'record_type':'chunk','doc_id':'synthetic-'+str(i),'chunk_id':'chunk-'+str(i),'text':'alpha network' if i!=1 else 'beta flow','title':'Synthetic engineering record '+str(i),'kind':'paper','year':2026,'case_id':'synthetic','same_problem_reference':i==2,'source_url':'https://example.invalid/fixture-'+str(i),'source_note':'Generated engineering fixture, not a real paper','usage':'installation probe','source_sha256':'a'*64,'parser':'synthetic','locator':{'page':1}})
    corpus={'documents':[{'id':'synthetic'}],'chunks':chunks};corpus['corpus_sha256']=digest({'documents':corpus['documents'],'chunks':chunks})
    client=QdrantClient(path=str(out/'qdrant-local'));collection=ingest(client,embedder,corpus);assert ingest(client,embedder,corpus)==collection
    service=Retriever(client,embedder,collection,corpus['corpus_sha256']);result=service.search('alpha',limit=5,include_same_problem=False);assert result['hits'] and all(h['same_problem_reference'] is False for h in result['hits'])
    filtered=service.search('alpha',filters={'doc_id':'synthetic-0'},include_same_problem=False);assert filtered['hits'] and all(h['doc_id']=='synthetic-0' for h in filtered['hits'])
    tool=SearchTool(factory=lambda:service,log_path=out/'search-audit.jsonl',references=out/'references')
    packet=tool.invoke('paper_search',{'query':'alpha','limit':2,'include_same_problem':False}).structuredContent;assert packet['status']=='ok',packet
    found=discover('alpha',out/'discovery',sources=['paper_search'],adapter=tool);assert found['status'] in ['ok','partial','passed'],found
    changed=copy.copy(embedder);changed.signature='changed'
    try:Retriever(client,changed,collection,corpus['corpus_sha256']).search('alpha')
    except RetrievalUnavailable:rejected=True
    else:raise AssertionError('Mismatched embedding identity accepted')
    client.close();client=QdrantClient(path=str(out/'qdrant-local'));restored=Retriever(client,embedder,collection,corpus['corpus_sha256']).search('alpha',include_same_problem=False);assert restored['hits'];client.close()
    return {'torch':torch.__version__,'embedding_shape':list(vectors.shape),'normalization':'passed','model':'locally generated random tiny BERT; product LocalBge adapter exercised, NOT production BGE weights or semantic-quality acceptance','model_downloaded':False,'qdrant':'real persistent local client, NOT Docker/server deployment','ingest_idempotency':True,'search_hits':len(result['hits']),'filtered_hits':len(filtered['hits']),'same_problem_exclusion':True,'mismatched_embedding_rejected':True,'persisted_index_reopened':True,'mcp_core_search_envelope':packet,'discovery':found,'live_public_search':'NOT_RUN'}

def paper(out,pandoc,tectonic,cache):
    import sentence_transformers,fitz
    from docx import Document
    from modelcrew import paper_export,latex_tools,paper_render
    from modelcrew.modeling_paper import writing_context
    from modelcrew.pdf_checks import audit_pdf_tree
    from modelcrew.package_resources import resource
    tools=latex_tools.doctor(out/'doctor',need_word=True,compiler=tectonic);assert tools['status']=='passed',tools
    template=out/'template';template.mkdir()
    # Custom project is a declared engineering probe, never registered formal export.
    tex=chr(10).join([r'\documentclass[12pt]{article}',r'\begin{document}','Synthetic installation probe; not a paper.',r'\[x^2+1=2\]',r'\newpage','Second physical page: complete PDF checks required.',r'\end{document}'])
    (template/'main.tex').write_text(tex,encoding='utf-8')
    latex_tools.initialize(out,'project',template='template',template_source='NexusMORE independently authored installation fixture',template_version='1')
    compiled=latex_tools.build(out,'project','compiled',compiler=tectonic);assert compiled['status']=='passed',compiled
    assert latex_tools.validate(out,'project','compiled')['status']=='passed'
    markdown=out/'synthetic.md';markdown.write_text('# Synthetic installation probe'+chr(10)*2+'Not a paper; no user result or approval.'+chr(10)*2+'Equation: $x^2+1=2$.'+chr(10),encoding='utf-8')
    reference=out/'reference.docx';paper_export.reference_docx(reference)
    command=[str(pandoc),str(markdown),'--from=markdown+tex_math_dollars','--to=docx','--reference-doc='+str(reference),'--output='+str(out/'synthetic.docx')]
    latex_tools.run_logged(command,out,'pandoc-docx',timeout=90)
    latex_tools.run_logged([str(pandoc),str(markdown),'--from=markdown+tex_math_dollars','--to=json','--output='+str(out/'source-ast.json')],out,'pandoc-ast',timeout=90)
    with zipfile.ZipFile(out/'synthetic.docx') as z:
        xml=z.read('word/document.xml');assert b'<m:oMath' in xml and b'x' in xml
    native_command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(resource('rendering/render-word.ps1'))),'-Docx',str(out/'synthetic.docx'),'-Pdf',str(out/'word-render.pdf')]
    native=subprocess.run(native_command,capture_output=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));(out/'word-render.stdout.log').write_bytes(native.stdout);(out/'word-render.stderr.log').write_bytes(native.stderr)
    native_status={'status':'passed' if native.returncode==0 and (out/'word-render.pdf').is_file() else 'blocked','returncode':native.returncode,'scope':'this host engineering fixture only; not formal paper acceptance','stderr_log':'word-render.stderr.log'}
    from modelcrew.paper_layout import contract
    context=writing_context();layout=contract(context)
    assert len(layout['read_log'])==5 and layout['source']=='nexusmore_authored_chinese_research_baseline_1.0.0'
    writing={'status':'passed','workflow_version':context['workflow']['workflow_version'],'documents':len(context['documents']),'layout':layout,'formal_approval':False}
    tree=audit_pdf_tree(out,out.parent/'paper-pdf-audit');assert tree['status']=='passed',tree
    return {'imports':'passed including sentence_transformers and paper render/export','tool_diagnostics':tools,'real_tectonic_build':compiled,'pandoc_docx_native_omml':True,'pandoc_ast':True,'native_word_render':native_status,'all_generated_pdfs':tree,'writing_context':writing,'formal_export_complete':False,'formal_approval':False,'independent_W2':'NOT_RUN'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--group',choices=['retrieval','paper'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--wheel',type=Path,required=True);p.add_argument('--pandoc',type=Path);p.add_argument('--tectonic',type=Path);p.add_argument('--cache',type=Path);a=p.parse_args()
    import modelcrew
    from modelcrew.package_resources import verify_resources
    assert sys.prefix!=sys.base_prefix and site.ENABLE_USER_SITE is False and importlib.util.find_spec('pytest') is None
    assert str(ROOT/'src') not in sys.path and str(ROOT) not in sys.path and not Path.cwd().is_relative_to(ROOT)
    package=Path(modelcrew.__file__).parent;assert package.is_relative_to(Path(sys.prefix))
    with zipfile.ZipFile(a.wheel) as z:
        for name in z.namelist():
            if name.startswith('modelcrew/'):assert z.read(name)==(package/name.removeprefix('modelcrew/')).read_bytes(),name
    a.output.mkdir(parents=True,exist_ok=False)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HF_HOME']=str(a.output/'hf-cache')
    if a.group=='paper':
        os.environ['MODELCREW_PANDOC']=str(a.pandoc);os.environ['MODELCREW_TECTONIC']=str(a.tectonic);os.environ['TECTONIC_CACHE_DIR']=str(a.cache)
    result=retrieval(a.output) if a.group=='retrieval' else paper(a.output,a.pandoc,a.tectonic,a.cache)
    pip=subprocess.run([sys.executable,'-I','-m','pip','check'],capture_output=True,text=True,check=True)
    status='partial' if a.group=='paper' and result['native_word_render']['status']!='passed' else 'passed'
    report={'status':status,'dependency_validation_status':'passed','group':a.group,'python':sys.version,'cwd':str(Path.cwd()),'package':str(package),'system_site_packages':False,'user_site_enabled':False,'resources':verify_resources(),'checks':result,'pip_check':pip.stdout.strip(),'distributions':sorted([{'name':d.metadata['Name'],'version':d.version} for d in md.distributions()],key=lambda d:d['name'].lower()),'formal_approval':False,'independent_review':'NOT_RUN'}
    write(a.output/'probe.json',report);print(json.dumps({'status':status,'dependency_validation_status':'passed','group':a.group,'report':str(a.output/'probe.json')}))

if __name__=='__main__':main()
