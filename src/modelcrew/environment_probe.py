"""Synthetic environment probes; no model calls, user approval, or formal paper export."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from . import config
from .package_resources import resource
from .repository_migration import relative_path
from .service_environment import _root,_state,_database,_write,_sha,status,EnvironmentError


def _output(root,output):
    path=Path(output)
    if not path.is_absolute():path=root/path
    try:name=path.relative_to(root).as_posix()
    except ValueError:raise ValueError('Probe output must stay in the selected workspace') from None
    path=relative_path(root,name)
    path.mkdir(parents=True,exist_ok=False)
    return path


def _binding(state):
    if state['task']['phase']!='WAITING_MODEL_APPROVAL' or state['task']['model_approved'] or state['execution']:
        raise EnvironmentError('Environment sample unexpectedly advanced past the model approval gate')


def smoke(output,root=None):
    root=_root(root)
    if root!=config.ROOT:raise ValueError('Select workspace before importing workflow modules')
    state=_state(root)
    if status(root)['status']!='passed':raise EnvironmentError('Managed services must be healthy before the probe')
    folder=_output(root,output)
    raw=json.dumps({'a':1,'b':1,'scope':'synthetic_environment_probe'},sort_keys=True).encode()
    _write(folder/'environment-input.json',raw.decode())
    contract=json.loads(resource('environment/example-contract.json').read_text(encoding='utf-8'))
    input_path=(folder/'environment-input.json').relative_to(root).as_posix();fingerprint=hashlib.sha256(raw).hexdigest()
    contract['sources'][0].update(locator=input_path,sha256=fingerprint)
    contract['inputs'][0].update(path=input_path,sha256=fingerprint)
    _write(folder/'contract.json',contract)
    task='environment-'+uuid.uuid4().hex
    from .workflow import Workflow
    with Workflow(url=_database(root,state)) as workflow:
        current=workflow.create(task,contract,project='environment-probes',executor_key='pending-code')
        _binding(current)
        contract_hash=workflow.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s',(task,)).fetchone()['sha256']
    from qdrant_client import QdrantClient,models
    collection='mc_environment_'+uuid.uuid4().hex
    payload={'kind':'synthetic_environment_probe','task':task,'contract_sha256':contract_hash}
    with closing(QdrantClient(url=f'http://127.0.0.1:{state["qdrant_port"]}',timeout=15)) as client:
        client.create_collection(collection,vectors_config=models.VectorParams(size=3,distance=models.Distance.COSINE))
        client.upsert(collection,points=[models.PointStruct(id=1,vector=[1.,0.,0.],payload=payload)],wait=True)
        assert client.retrieve(collection,[1])[0].payload==payload
    from .docker_executor import DockerExecutor,register_job
    from .execution_paths import execution_directory
    code=folder/'executor-probe.py'
    _write(code,"import json,os,sys,platform\nfrom pathlib import Path\nimport numpy as np\nassert sys.version_info[:2]==(3,13) and os.getuid()!=0\na=np.array([1.,2.]);assert float(a.sum())==3\ntry:\n Path('/root-write-probe').write_text('forbidden')\nexcept OSError:pass\nelse:raise AssertionError('Root was writable')\nPath('environment-result.json').write_text(json.dumps({'python':platform.python_version(),'uid':os.getuid(),'sum':float(a.sum()),'root_write_denied':True}))\n")
    job_id='environment-'+uuid.uuid4().hex
    execution_root=execution_directory(root)
    register_job(execution_root,job_id,code,[],{'mode':'verification','actor':'environment-engineering-probe','not_independent_modeling':True}, {'timeout_s':30,'memory_mb':512})
    receipt=DockerExecutor(execution_root,allow_test_jobs=True).execute(job_id)
    if receipt['status']!='succeeded':raise EnvironmentError('Executor probe failed; inspect its preserved receipt')
    recovered=DockerExecutor(execution_root,allow_test_jobs=True).status(job_id)
    if recovered!=receipt:raise EnvironmentError('Executor receipt recovery changed')
    report={'schema_version':'1.0.0','status':'passed','project':state['project'],'task_id':task,'contract_sha256':contract_hash,
        'phase':'WAITING_MODEL_APPROVAL','model_approved':False,'qdrant_collection':collection,'payload':payload,
        'executor_job_id':job_id,'executor_receipt_sha256':hashlib.sha256(json.dumps(receipt,sort_keys=True,default=str).encode()).hexdigest(),
        'executor_image_id':receipt.get('image_id'),'services_restarted':False,'recovery_verified':False,'model_calls':0,
        'scientific_review':'not_run','user_approval':False,'scope':'Synthetic infrastructure/persistence probe only; not formal workflow acceptance'}
    _write(folder/'probe.json',report)
    return report


def recover(report_path,root=None):
    root=_root(root);path=Path(report_path)
    if not path.is_absolute():path=root/path
    path=relative_path(root,path.relative_to(root).as_posix())
    report=json.loads(path.read_text(encoding='utf-8'));state=_state(root)
    if report['project']!=state['project']:raise EnvironmentError('Recovery report belongs to another workspace')
    from .workflow import Workflow
    with Workflow(url=_database(root,state)) as workflow:
        current=workflow.resume(report['task_id']);_binding(current)
        actual=workflow.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s',(report['task_id'],)).fetchone()['sha256']
        if actual!=report['contract_sha256']:raise EnvironmentError('Recovered contract changed')
    from qdrant_client import QdrantClient
    with closing(QdrantClient(url=f'http://127.0.0.1:{state["qdrant_port"]}',timeout=15)) as client:
        points=client.retrieve(report['qdrant_collection'],[1],with_vectors=True)
        if len(points)!=1 or points[0].payload!=report['payload'] or points[0].vector!=[1.,0.,0.]:raise EnvironmentError('Qdrant persisted probe changed')
    from .docker_executor import DockerExecutor
    from .execution_paths import execution_directory
    receipt=DockerExecutor(execution_directory(root),allow_test_jobs=True).status(report['executor_job_id'])
    if hashlib.sha256(json.dumps(receipt,sort_keys=True,default=str).encode()).hexdigest()!=report['executor_receipt_sha256']:
        raise EnvironmentError('Recovered execution receipt changed; do not redispatch')
    return {'status':'passed','task_id':report['task_id'],'phase':'WAITING_MODEL_APPROVAL','model_approved':False,
        'contract_unchanged':True,'qdrant_persistence_verified':True,'execution_receipt_unchanged':True,
        'new_execution_dispatched':False,'scope':'Persistence recovery only; run after an explicit service restart to test restart recovery'}


def documents(output,root=None,*,offline=False):
    root=_root(root);folder=_output(root,output)
    from .tool_discovery import discover_tool,tex_cache_directory
    from .environment_tools import _version
    pandoc=discover_tool('pandoc',root=root);tectonic=discover_tool('tectonic',root=root)
    _version(pandoc,'pandoc','3.6.4');_version(tectonic,'tectonic','0.17.0')
    font=Path(config.configured('MODELCREW_CJK_FONT',Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/simsun.ttc',root=root))
    if not font.is_absolute():font=root/font
    if not font.is_file():raise EnvironmentError('Chinese font missing; configure a licensed local font')
    (folder/'fonts').mkdir();(folder/'fonts/cjk.ttc').write_bytes(font.read_bytes())
    tex=r"""\documentclass[12pt]{article}
\usepackage[a4paper,margin=30mm]{geometry}
\usepackage{fontspec,xeCJK}
\setmainfont[Path=fonts/]{cjk.ttc}
\setCJKmainfont[Path=fonts/]{cjk.ttc}
\pagestyle{empty}
\begin{document}
\section*{环境准备工程探针}
本页检查中文字体、公式与真实编译。这不是正式论文，也不记录用户批准。
\[1+1=2\]
\newpage
\section*{全页检查工程探针}
第二页用于核对物理页数、全部页面预览及文本边界。独立审查尚未执行。
\[\int_0^1 x\,dx=\frac{1}{2}\]
\end{document}
"""
    _write(folder/'probe.tex',tex)
    _write(folder/'probe.md','# 环境准备工程探针\n\n本文件检查中文与 Word 原生公式，不是正式论文。\n\n$$1+1=2$$\n\n# 全页检查工程探针\n\n核对全部物理页面与预览。\n')
    cache=tex_cache_directory(root);cache.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'TECTONIC_CACHE_DIR':str(cache),'TEMP':str(cache),'TMP':str(cache),'PYTHONIOENCODING':'utf-8'}
    commands=[('tectonic',[str(tectonic),'--untrusted','--keep-logs',*(['--only-cached'] if offline else []),'probe.tex']),
              ('pandoc',[str(pandoc),'probe.md','-o','probe.docx'])]
    for name,args in commands:
        try:response=subprocess.run(args,cwd=folder,env=env,capture_output=True,timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.SubprocessError):raise EnvironmentError(name+' probe unavailable or timed out; keep the new output directory') from None
        (folder/(name+'.stdout.log')).write_bytes(response.stdout);(folder/(name+'.stderr.log')).write_bytes(response.stderr)
        if response.returncode:raise EnvironmentError(name+' real probe failed; inspect retained logs and prepare downloads/cache explicitly')
    # Force two Word pages so all-page inspection exercises more than page one.
    from docx import Document
    from docx.oxml import OxmlElement
    document=Document(folder/'probe.docx')
    headers=[p for p in document.paragraphs if p.style.name.startswith('Heading')]
    if len(headers)>=2:headers[1].paragraph_format.page_break_before=True
    document.save(folder/'probe.docx')
    import zipfile
    with zipfile.ZipFile(folder/'probe.docx') as package:
        if b'<m:oMath' not in package.read('word/document.xml'):raise EnvironmentError('Pandoc did not produce native Word equations')
    word_pdf=folder/'word-render.pdf'
    command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(resource('rendering/render-word.ps1'))),'-Docx',str(folder/'probe.docx'),'-Pdf',str(word_pdf)]
    response=subprocess.run(command,capture_output=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (folder/'word.stdout.log').write_bytes(response.stdout);(folder/'word.stderr.log').write_bytes(response.stderr)
    checks={}
    from .pdf_checks import inspect_pdf,verify_pdf_report
    for label,pdf in [('latex',folder/'probe.pdf'),('word',word_pdf)]:
        if not pdf.is_file():checks[label]={'status':'blocked','reason':'native_render_unavailable'};continue
        checked=inspect_pdf(pdf,folder/(label+'-pages'));verify_pdf_report(pdf,folder/(label+'-pages'),checked)
        checks[label]=checked
    log=(folder/'probe.log').read_text(encoding='utf-8',errors='replace')
    warnings=[line for line in log.splitlines() if any(term in line for term in ['Missing character','Overfull','Underfull','undefined','LaTeX Warning','Package fontspec Warning'])]
    passed=not warnings and all(v.get('status')=='passed' for v in checks.values()) and all(v.get('page_count')==2 for v in checks.values())
    report={'schema_version':'1.0.0','status':'passed' if passed else 'blocked','scope':'Two-page engineering probes, not formal paper approval','checks':checks,
        'latex_warnings':warnings,'word_exit_code':response.returncode,'font_sha256':_sha(font),'visual_review':'pending','independent_W2':'not_run',
        'source_files':{name:_sha(folder/name) for name in ['probe.tex','probe.md','probe.docx','probe.pdf']},'cache_network_allowed':not offline}
    _write(folder/'documents.json',report)
    return report
