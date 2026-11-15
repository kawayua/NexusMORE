"""NexusMORE Python LaTeX workspace tools; raw projects are engineering probes.

Formal exports enter through the registered assembly workflow. An arbitrary TeX
project, compiler exit code or reason string never grants paper approval.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from .config import configured, ROOT
import re
import shutil
import subprocess

from .package_resources import resource
from .pdf_checks import sha, inspect_pdf, verify_pdf_report

MANIFEST = 'latex-project.json'
ENGINES = {'tectonic', 'xelatex', 'lualatex', 'pdflatex'}


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def contained(root, path):
    """Actual configured workspace containment, including Windows junctions."""
    root = Path(root).absolute()
    raw = Path(path)
    raw = raw.absolute() if raw.is_absolute() else root/raw
    resolved = raw.resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved == root.resolve():
        raise ValueError('Path must be a child of the explicitly selected workspace')
    current = raw
    while True:
        if current.is_symlink() or current.is_junction():
            raise ValueError('Linked workspace path is not allowed')
        if current == current.parent:
            break
        current = current.parent
    return resolved


def inventory(folder):
    folder = Path(folder)
    result = {}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or path.is_junction():
            raise ValueError('Linked project resource is not allowed')
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = sha(path)
    if not result:
        raise ValueError('Empty project')
    return result


def project_at(root, project):
    folder = contained(root, project)
    value = json.loads((folder/MANIFEST).read_text(encoding='utf-8'))
    if value.get('schema_version') != '1.0.0' or value.get('purpose') != 'engineering_probe':
        raise ValueError('Unknown LaTeX project protocol')
    from .hand_guidance import frozen_bundle
    frozen_bundle(folder,value['guidance_sha256'])
    if value.get('engine') not in ENGINES:
        raise ValueError('Unsupported project compiler')
    main = contained(folder, value['main'])
    if not main.is_file() or main.suffix.lower() != '.tex':
        raise ValueError('Project main TeX is missing')
    return folder, value, main


def initialize(root, output, *, profile='zh', template=None, main='main.tex',
               template_source=None, template_version=None, engine='tectonic', cjk_font=None):
    """Create an editable, UNAPPROVED skeleton in a new workspace directory."""
    if profile not in {'zh', 'en'} or engine not in ENGINES:
        raise ValueError('Unknown language profile or engine')
    target = contained(root, output)
    if template is not None:
        if not template_source or not template_version:
            raise ValueError('Custom template requires source and version metadata')
        source = contained(root, template)
        if not source.is_dir() or target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError('Custom template must be a separate directory')
        originals = inventory(source)
        if any(name in originals for name in [MANIFEST,'collaboration-guidance.json']) or any(name.startswith('bindings/') for name in originals):
            raise ValueError('Template already contains project metadata')
        selected = contained(source, main)
        if not selected.is_file() or selected.suffix.lower() != '.tex':
            raise ValueError('Specify an existing template main TeX')
        metadata = {'source':template_source, 'version':template_version,
                    'files':originals, 'official_compliance_verified':False}
    else:
        if main != 'main.tex':
            raise ValueError('Bundled skeleton main is main.tex')
        files = {'main.tex':resource('latex/'+profile+'-main.tex').read_bytes(),
                 'references.bib':resource('latex/references.bib').read_bytes()}
        if profile=='zh':
            font = Path(cjk_font or configured('MODELCREW_CJK_FONT') or
                        Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/simsun.ttc')
            if not font.is_absolute(): font=ROOT/font
            if font.is_file():
                if font.suffix.lower() not in {'.ttc','.ttf','.otf'}:
                    raise ValueError('Unsupported CJK font file')
                name='fonts/cjk-font'+font.suffix.lower()
                files[name]=font.read_bytes()
                font_identity={'path':str(font.resolve()),'sha256':__import__('hashlib').sha256(files[name]).hexdigest(),
                               'scope':'Local template snapshot only; font redistribution permission is not asserted'}
                files['main.tex']=files['main.tex'].replace(b'NEXUSMORE_CJK_FONT',Path(name).name.encode('ascii'))
            elif cjk_font is not None:
                raise ValueError('Explicit CJK font file is missing')
        metadata = {'source':'NexusMORE project-authored research skeleton', 'version':'1.0.0',
                    'files':{name:__import__('hashlib').sha256(raw).hexdigest() for name,raw in files.items()},
                    'official_compliance_verified':False}
        if profile=='zh' and 'font_identity' in locals():metadata['local_font']=font_identity
    target.mkdir(parents=True, exist_ok=False)
    if template is not None:
        for name in originals:
            dest=contained(target,name);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source/name,dest)
        if inventory(source) != originals or inventory(target) != originals:
            raise ValueError('Template changed during copy')
    else:
        for name,raw in files.items():
            (target/name).parent.mkdir(parents=True,exist_ok=True)
            with (target/name).open('xb') as stream:stream.write(raw)
    from .hand_guidance import freeze_guidance
    guidance_sha256=freeze_guidance(target)
    value = {'schema_version':'1.0.0', 'guidance_sha256':guidance_sha256, 'purpose':'engineering_probe', 'profile':profile,
             'engine':engine, 'main':main, 'template':metadata,
             'formal_export_route':'registered assembly export only', 'user_approval':False}
    write_new(target/MANIFEST,value)
    return {'status':'initialized', 'project':str(target), 'purpose':'engineering_probe',
            'user_approval':False,'template':metadata}


def bind(root, project, source, destination):
    """Copy one authoritative resource and append a write-once binding record."""
    folder, _, _ = project_at(root, project)
    original = contained(root, source)
    target = contained(folder, destination)
    if original.is_relative_to(folder) or not original.is_file():
        raise ValueError('Authoritative input must be a file outside the TeX project')
    if target in {folder/MANIFEST,folder/'collaboration-guidance.json'} or target.suffix.lower() in {'.tex','.sty','.cls','.bib','.bst'}:
        raise ValueError('Use template/source editing for TeX authoring resources')
    if target.is_relative_to(folder/'bindings'):
        raise ValueError('Binding metadata directory is reserved')
    expected = sha(original)
    if target.exists():
        if not target.is_file() or sha(target) != expected:
            raise ValueError('Existing resource copy differs; use a new version')
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as output, original.open('rb') as input_stream:
            shutil.copyfileobj(input_stream,output)
    if sha(original) != expected or sha(target) != expected:
        raise ValueError('Resource changed during binding')
    records = folder/'bindings';records.mkdir(exist_ok=True)
    identifier = __import__('uuid').uuid4().hex
    record = {'source':str(original), 'destination':target.relative_to(folder).as_posix(),
              'sha256':expected, 'scope':'source identity; not execution or user approval'}
    write_new(records/(identifier+'.json'),record)
    return record


def run_logged(command, folder, name, *, cwd=None, timeout=180, env=None, input_data=None, raw_output=False):
    """Persist command/stdout/stderr even on timeout, spawn error or nonzero exit."""
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError('Timeout must be an integer from 1 to 600 seconds')
    folder=Path(folder)
    write_new(folder/(name+'-command.json'),{'command':list(map(str,command)),
              'cwd':str(cwd) if cwd else None,'timeout_seconds':timeout,
              'input_sha256':__import__('hashlib').sha256(input_data).hexdigest() if input_data is not None else None})
    status='failed';code=None;error=None;stdout=b'';stderr=b''
    try:
        result=subprocess.run(list(map(str,command)),cwd=cwd,env=env,capture_output=True,
                              timeout=timeout,input=input_data,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        stdout,stderr=result.stdout,result.stderr;code=result.returncode
        status='passed' if code==0 else 'failed'
    except subprocess.TimeoutExpired as exc:
        status='timeout';stdout=exc.stdout or b'';stderr=exc.stderr or b'';error='Command timed out'
    except OSError as exc:
        error=str(exc)
    (folder/(name+'-stdout.log')).write_bytes(stdout)
    (folder/(name+'-stderr.log')).write_bytes(stderr)
    record={'status':status,'returncode':code,'error':error,
            'stdout_sha256':sha(folder/(name+'-stdout.log')),
            'stderr_sha256':sha(folder/(name+'-stderr.log'))}
    write_new(folder/(name+'-result.json'),record)
    if status!='passed':raise RuntimeError(name+' '+status+': '+str(code if error is None else error))
    return stdout if raw_output else stdout.decode('utf-8',errors='replace')


def executable(name, explicit=None):
    if name not in ENGINES | {'pandoc','latexmk','biber','bibtex'}:
        raise ValueError('Unsupported tool')
    if name in {'tectonic','pandoc'}:
        from .tool_discovery import discover_tool
        return discover_tool(name,explicit)
    configured=explicit or os.environ.get('MODELCREW_'+name.upper()) or shutil.which(name)
    if configured is None or not Path(configured).is_file():
        raise RuntimeError('Missing executable: '+name)
    return Path(configured).resolve()


def doctor(output, *, engine='tectonic', bibliography='none', need_word=False, compiler=None):
    """Diagnose selected features only. No installing or downloading anything."""
    if engine not in ENGINES or bibliography not in {'none','bibtex','biber'}:
        raise ValueError('Unknown compiler or bibliography selection')
    folder=Path(output).resolve();folder.mkdir(parents=True,exist_ok=False)
    issues=[];tools=[]
    names=[engine]+(['latexmk',bibliography] if bibliography!='none' else [])+(['pandoc'] if need_word else [])
    if engine=='tectonic' and bibliography!='none':
        issues.append('External bibliography with Tectonic is not verified; select the current numbered Markdown route or an explicitly configured classic engine')
    for name in names:
        try:
            path=executable(name,compiler if name==engine else None)
            version=run_logged([path,'--version'],folder,name,timeout=15).splitlines()
            if not version:raise RuntimeError('Empty version response')
            tools.append({'name':name,'path':str(path),'sha256':sha(path),'version':version[0]})
        except (RuntimeError,OSError,ValueError) as exc:issues.append(str(exc))
    dependencies=[]
    from importlib.metadata import version, PackageNotFoundError
    for name in ['fitz','pypdf']+(['docx'] if need_word else []):
        available=importlib.util.find_spec(name) is not None
        package={'fitz':'PyMuPDF','pypdf':'pypdf','docx':'python-docx'}[name]
        try:installed=version(package) if available else None
        except PackageNotFoundError:installed=None
        dependencies.append({'name':package,'available':available,'version':installed})
        if not available or installed is None:issues.append('Missing Python dependency/version: '+name)
    report={'status':'passed' if not issues else 'blocked','engine':engine,'bibliography':bibliography,
            'tools':tools,'dependencies':dependencies,'issues':issues,'downloaded':False,'native_word_render_verified':False,
            'scope':'Requested tools/dependencies only; not template compatibility or a successful paper export'}
    write_new(folder/'doctor.json',report)
    return report


def _clean(text):
    # Limited static checks, deliberately not described as a TeX parser/sandbox.
    text=re.sub(r'\\begin\{(verbatim\*?|lstlisting|comment)\}.*?\\end\{\1\}', '',text,flags=re.S)
    text=re.sub(r'(?<!\\)%[^\n]*','',text)
    return text


def preflight(root, project):
    folder, metadata, main=project_at(root,project)
    files=inventory(folder);issues=[]
    bound={}
    for path in sorted((folder/'bindings').glob('*.json')):
        record=json.loads(path.read_text(encoding='utf-8'))
        original=contained(root,record['source']);dest=contained(folder,record['destination'])
        if not original.is_file() or not dest.is_file() or sha(original)!=record['sha256'] or sha(dest)!=record['sha256']:
            issues.append('Changed or missing resource: '+record['destination'])
        if record['destination'] in bound and bound[record['destination']]!=record['sha256']:
            issues.append('Conflicting resource bindings: '+record['destination'])
        bound[record['destination']]=record['sha256']
    text='\n'.join(_clean((folder/name).read_text(encoding='utf-8-sig')) for name in files if Path(name).suffix.lower() in {'.tex','.cls','.sty'})
    if re.search(r'NEXUSMORE_[A-Z_]+|\bTODO\b|PLACEHOLDER|待补充',text,re.I):issues.append('Unresolved template placeholder')
    if re.search(r'\\(?:write18|openin|openout|read|write)(?![A-Za-z@])|\\(?:usepackage|RequirePackage)(?:\[[^]]*\])?\{[^}]*(?:minted|shellesc)',text):
        issues.append('Prohibited TeX execution/file command')
    if not all(token in _clean(main.read_text(encoding='utf-8-sig')) for token in ['\\begin{document}','\\end{document}']):
        issues.append('Main TeX requires a document environment')
    labels=re.findall(r'\\label\s*\{([^}]+)\}',text)
    if len(labels)!=len(set(labels)):issues.append('Duplicate TeX labels')
    refs=[part.strip() for group in re.findall(r'\\(?:ref|eqref|pageref|autoref|cref)\s*\{([^}]+)\}',text) for part in group.split(',')]
    if set(refs)-set(labels):issues.append('Unresolved source label reference')
    for name in files:
        suffix=Path(name).suffix.lower()
        metadata_file = name in {MANIFEST,'collaboration-guidance.json'} or name.startswith('bindings/') and suffix == '.json'
        if suffix not in {'.tex','.cls','.sty','.bib','.bst','.md'} and not metadata_file and name not in bound:
            original=metadata['template']['files'].get(name)
            if original!=files[name]:issues.append('Unbound data/code/figure resource: '+name)
    for raw in re.findall(r'\\(?:input|include)\s*\{([^}]+)\}',text):
        if '\\' in raw or '#' in raw:issues.append('Dynamic include requires explicit adapter verification');continue
        target=contained(folder,raw if Path(raw).suffix else raw+'.tex')
        if not target.is_file():issues.append('Missing TeX include: '+raw)
    if re.search(r'\\(?:bibliography|addbibresource)\b',text):
        issues.append('External bibliography requires a verified bibliography adapter; current probe supports inline verified references')
    for raw in re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',text):
        image=contained(folder,raw)
        choices=[image] if image.suffix else [image.with_suffix(ext) for ext in ['.pdf','.png','.jpg','.jpeg']]
        if image.suffix.lower() in {'.svg','.eps'}:
            issues.append('Compile-time SVG/EPS conversion is not enabled')
        elif not any(item.is_file() for item in choices):
            issues.append('Missing figure resource: '+raw)
    active=set();visited=set()
    def visit(path):
        if path in active:
            issues.append('Cyclic TeX includes');return
        if path in visited or not path.is_file():return
        active.add(path)
        content=_clean(path.read_text(encoding='utf-8-sig'))
        for raw in re.findall(r'\\(?:input|include)\s*\{([^}]+)\}',content):
            if '\\' not in raw and '#' not in raw:
                visit(contained(folder,raw if Path(raw).suffix else raw+'.tex'))
        active.remove(path);visited.add(path)
    visit(main)
    keys=set(re.findall(r'\\bibitem(?:\[[^]]*\])?\{([^}]+)\}',text))
    citations={key.strip() for group in re.findall(r'\\cite(?:p|t)?(?:\[[^]]*\])?\{([^}]+)\}',text) for key in group.split(',')}
    if citations-keys:issues.append('Citation key has no inline bibliography item')
    return {'status':'passed' if not issues else 'failed','issues':sorted(set(issues)),
            'project_files':files,'main':metadata['main'],'purpose':'engineering_probe',
            'formal_approval':False,'scope':'Limited source and binding checks, not TeX macro semantics or scientific validation'}


def build(root, project, output, *, compiler=None, timeout=180):
    """Compile a source snapshot, never overwrite or publish a formal paper."""
    folder,metadata,_=project_at(root,project);attempt=contained(root,output)
    if attempt.is_relative_to(folder) or folder.is_relative_to(attempt):
        raise ValueError('Build attempt must be separate from source project')
    attempt.mkdir(parents=True,exist_ok=False)
    report={'status':'failed','purpose':'engineering_probe','formal_approval':False,
            'visual_review':'PENDING','W2':'NOT_RUN'}
    try:
        checked=preflight(root,folder);write_new(attempt/'source-check.json',checked)
        if checked['status']!='passed':raise ValueError('Source checks failed: '+'; '.join(checked['issues']))
        snapshot=attempt/'source';shutil.copytree(folder,snapshot)
        if inventory(snapshot)!=checked['project_files']:raise ValueError('Source changed during snapshot')
        path=executable(metadata['engine'],compiler)
        version=run_logged([path,'--version'],attempt,'compiler-version',timeout=15).splitlines()
        if not version:raise RuntimeError('Compiler version response empty')
        identity={'path':str(path),'sha256':sha(path),'version':version[0]}
        artifacts=attempt/'artifacts';artifacts.mkdir()
        engine=metadata['engine'];main=metadata['main']
        env={**os.environ,'openin_any':'p','openout_any':'p'}
        if engine=='tectonic':
            if (snapshot/'fonts').is_dir():
                config=attempt/'engine-fontconfig.xml'
                config.write_text('<?xml version="1.0"?><fontconfig></fontconfig>\n',encoding='utf-8')
                env['FONTCONFIG_FILE']=str(config)
            from .tool_discovery import tex_cache_directory
            env['TECTONIC_CACHE_DIR']=str(tex_cache_directory())
            commands=[[path,'--untrusted','--only-cached','--keep-logs','--keep-intermediates','--outdir',artifacts,main]]
        else:
            command=[path,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-file-line-error','-output-directory='+str(artifacts),main]
            if 'miktex' in version[0].lower():command.insert(1,'--disable-installer')
            commands=[command,command]
        stdout=''
        for index,command in enumerate(commands,1):
            stdout += run_logged(command,attempt,'compile-'+str(index),cwd=snapshot,timeout=timeout,env=env)
        logs=list(artifacts.glob('*.log'))
        if not logs:raise RuntimeError('Compiler did not retain a TeX log')
        log='\n'.join(path.read_text(encoding='utf-8',errors='replace') for path in logs)+'\n'+stdout
        problems=[line for line in log.splitlines() if re.search(r'undefined|Undefined control|Missing character|(?:Over|Under)full|(?:LaTeX|Package .*|Class .*|Font) Warning:|! (?:LaTeX|Package)',line,re.I)]
        write_new(attempt/'compiler-check.json',{'status':'failed' if problems else 'passed','findings':problems,'warning_exceptions':[]})
        if problems:raise ValueError('Unresolved compiler warnings or errors; see compiler-check.json')
        pdf=artifacts/(Path(main).stem+'.pdf')
        complete=inspect_pdf(pdf,attempt/'pdf-check');verify_pdf_report(pdf,attempt/'pdf-check',complete)
        if any(page['warnings'] for page in complete['pages']):
            raise ValueError('Unresolved PDF audit warnings; inspect every page')
        if inventory(folder)!=checked['project_files'] or inventory(snapshot)!=checked['project_files']:
            raise ValueError('Original or snapshot source changed during compile')
        if preflight(root,folder)['status']!='passed':
            raise ValueError('Authoritative resource binding changed during compile')
        if sha(path)!=identity['sha256']:raise ValueError('Compiler changed during compile')
        report.update(status='passed',compiler=identity,source_files=checked['project_files'],
                      pdf={'path':pdf.relative_to(attempt).as_posix(),'sha256':sha(pdf)},
                      pdf_check_sha256=sha(attempt/'pdf-check/pdf-check.json'),
                      page_count=complete['page_count'],scope='Real compilation and all-page mechanical checks; NOT a formal paper or independent W2')
    except Exception as exc:
        report.update(error=str(exc),error_type=type(exc).__name__)
    report['attempt_files']=inventory(attempt) if any(attempt.iterdir()) else {}
    write_new(attempt/'build-check.json',report)
    return report


def validate(root, project, attempt):
    """Recheck immutable build evidence and every current physical PDF page."""
    folder,_,_=project_at(root,project);attempt=contained(root,attempt)
    report=json.loads((attempt/'build-check.json').read_text(encoding='utf-8'))
    if report.get('status')!='passed' or report.get('purpose')!='engineering_probe':raise ValueError('No successful probe build to validate')
    actual=inventory(attempt);actual.pop('build-check.json')
    if actual!=report['attempt_files']:raise ValueError('Build artifacts or logs changed')
    if inventory(folder)!=report['source_files'] or inventory(attempt/'source')!=report['source_files']:
        raise ValueError('Current project differs from built source')
    checked=preflight(root,folder)
    if checked['status']!='passed':raise ValueError('Current resource binding failed')
    pdf=contained(attempt,report['pdf']['path'])
    if sha(pdf)!=report['pdf']['sha256'] or sha(attempt/'pdf-check/pdf-check.json')!=report['pdf_check_sha256']:
        raise ValueError('PDF identity changed')
    verify_pdf_report(pdf,attempt/'pdf-check',json.loads((attempt/'pdf-check/pdf-check.json').read_text(encoding='utf-8')))
    return {'status':'passed','page_count':report['page_count'],'formal_approval':False,
            'visual_review':'PENDING','W2':'NOT_RUN','scope':'Probe source/artifact/all-page identity check only'}


def export_registered(project_id, build_id, request_id, actor):
    """The single formal entry: existing DB approvals, lineage and assembly gates."""
    from .workflow import Workflow
    with Workflow() as workflow:
        result=workflow.export_assembly(project_id,build_id,request_id=request_id,actor=actor)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    init=sub.add_parser('init');init.add_argument('--root',required=True);init.add_argument('--output',required=True)
    init.add_argument('--profile',choices=['zh','en'],default='zh');init.add_argument('--template');init.add_argument('--main',default='main.tex')
    init.add_argument('--cjk-font');init.add_argument('--template-source');init.add_argument('--template-version');init.add_argument('--engine',choices=sorted(ENGINES),default='tectonic')
    check=sub.add_parser('doctor');check.add_argument('--output',required=True);check.add_argument('--engine',choices=sorted(ENGINES),default='tectonic')
    check.add_argument('--bibliography',choices=['none','bibtex','biber'],default='none');check.add_argument('--need-word',action='store_true');check.add_argument('--compiler')
    binding=sub.add_parser('bind');binding.add_argument('--root',required=True);binding.add_argument('--project',required=True);binding.add_argument('--source',required=True);binding.add_argument('--destination',required=True)
    compile_cmd=sub.add_parser('build');compile_cmd.add_argument('--root',required=True);compile_cmd.add_argument('--project',required=True);compile_cmd.add_argument('--output',required=True);compile_cmd.add_argument('--compiler');compile_cmd.add_argument('--timeout',type=int,default=180)
    inspect=sub.add_parser('validate');inspect.add_argument('--root',required=True);inspect.add_argument('--project',required=True);inspect.add_argument('--attempt',required=True)
    formal=sub.add_parser('export');formal.add_argument('--project-id',required=True);formal.add_argument('--build-id',required=True);formal.add_argument('--request-id',required=True);formal.add_argument('--actor',required=True)
    options=vars(parser.parse_args());action=options.pop('action')
    try:result={'init':initialize,'doctor':doctor,'bind':bind,'build':build,'validate':validate,'export':export_registered}[action](**options)
    except Exception as exc:result={'status':'failed','error':str(exc),'error_type':type(exc).__name__}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get('status') in {'passed','initialized'} or result.get('phase') in {'WAITING_RENDER','WAITING_W2','W2_PASSED'} else 1


if __name__=='__main__':raise SystemExit(main())
