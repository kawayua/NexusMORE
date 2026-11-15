"""Render registered PDF/Word output for mechanical QA; visual W2 stays pending."""
import json
import re
import hashlib
import zipfile
from pathlib import Path
import subprocess
import fitz
from modelcrew.config import ROOT
from modelcrew.package_resources import resource
from modelcrew.paper_layout import rendered_frontmatter
from modelcrew.collaboration import sha_file
from modelcrew.pdf_checks import inspect_pdf, verify_pdf_report


def render(output, qa):
    output=Path(output).resolve();qa=Path(qa).resolve()
    command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
             str(Path(resource('rendering/render-word.ps1'))),'-Docx',str(output/'paper.docx'),
             '-Pdf',str(qa/'word-render.pdf')]
    response=subprocess.run(command,capture_output=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (qa/'word-render.stdout.log').write_bytes(response.stdout)
    (qa/'word-render.stderr.log').write_bytes(response.stderr)
    if response.returncode:raise RuntimeError('Native Word render failed; inspect render logs')
    return inspect(output,qa,qa/'word-render.pdf')


def inspect(output,qa,word_pdf):
    """Read/render existing PDFs; this does not create or approve a paper."""
    output=Path(output).resolve();qa=Path(qa).resolve();qa.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((output/'figure-catalog.json').read_text(encoding='utf-8'))
    expected=[f['number'] for f in catalog['figures'] if f['formal']]
    ast=json.loads((output/'build/source-ast.json').read_text(encoding='utf-8'))
    def plain(value):
        if isinstance(value,dict):
            if value.get('t')=='Str':return value['c']
            if value.get('t') in ['Image','Math']:return ''
            return ''.join(plain(v) for v in value.values())
        return ''.join(map(plain,value)) if isinstance(value,list) else ''
    def chinese(value):return ''.join(re.findall('[\u4e00-\u9fff]',value))
    paragraphs=[chinese(plain(b)) for b in ast['blocks'] if b['t'] in ['Para','Header'] and len(chinese(plain(b)))>3]
    image_hashes={f['files']['png']['sha256'] for f in catalog['figures'] if f['formal']}
    with zipfile.ZipFile(output/'paper.docx') as zipped:
        embedded={hashlib.sha256(zipped.read(n)).hexdigest() for n in zipped.namelist() if n.startswith('word/media/')}
    report={'word_original_images_match':embedded==image_hashes,'source_docx_sha256':sha_file(output/'paper.docx'),
            'source_pdf_sha256':sha_file(output/'paper.pdf'),'formats':{},
            'visual_review':'PENDING','W2':'NOT_RUN'}
    for kind,pdf in [('latex',output/'paper.pdf'),('word',Path(word_pdf))]:
        complete = inspect_pdf(pdf,qa/(kind+'-pdf-check'))
        verify_pdf_report(pdf,qa/(kind+'-pdf-check'),complete)
        with fitz.open(pdf) as document:
            pages=[];body=''
            for n,page in enumerate(document,1):
                page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(qa/f'{kind}-{n:03}.png')
                body+=page.get_text(clip=fitz.Rect(0,50,page.rect.width,page.rect.height-45))
                spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans'] if s['text'].strip()]
                outside=[s['text'] for s in spans if s['bbox'][0]<-1 or s['bbox'][1]<-1 or s['bbox'][2]>page.rect.width+1 or s['bbox'][3]>page.rect.height+1]
                pages.append({'page':n,'outside':outside,'minimum_font_pt':min((s['size'] for s in spans),default=0)})
            compact=''.join(body.split())
            report['formats'][kind]={'pages':pages,'missing_chinese_paragraphs':[p for p in paragraphs if p not in chinese(body)],'all_figures_referenced':all('图'+str(n) in compact for n in expected), 'pdf_check':complete}
    manifest=json.loads((output/'build-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format_requirements',{}).get('frontmatter_max_pages')==1:
        for kind,pdf in [('latex',output/'paper.pdf'),('word',Path(word_pdf))]:
            report['formats'][kind]['abstract_pagination']=rendered_frontmatter(pdf,(output/'单题论文-中文审阅稿.md').read_text(encoding='utf-8'))
    from docx import Document
    doc=Document(output/'paper.docx')
    expected_equations=re.findall(r'\\tag\{(\d+)\}',(output/'单题论文-中文审阅稿.md').read_text(encoding='utf-8'))
    native_equations=[p.text.strip().strip('()') for p in doc.paragraphs if re.fullmatch(r'\(\d+\)',p.text.strip()) and p._p.xpath('.//m:oMath')]
    raw_math=[p.text for p in doc.paragraphs if '$$' in p.text]
    report['word_equations']={'expected':expected_equations,'native_numbered':native_equations,'unconverted_math':raw_math,'status':'passed' if native_equations==expected_equations and not raw_math else 'failed'}
    log=(output/'paper.log').read_text(encoding='utf-8',errors='replace')
    report['latex_log_failures']=[line for line in log.splitlines() if any(term in line for term in ['Missing character','Overfull','undefined','Undefined control'])]
    report['status']='passed' if report['word_equations']['status']=='passed' and not report['latex_log_failures'] and report['word_original_images_match'] and all(v['pdf_check']['status']=='passed' and v.get('abstract_pagination',{}).get('status','passed')=='passed' and not v['missing_chinese_paragraphs'] and v['pages'] and v['all_figures_referenced'] and all(not p['outside'] and p['minimum_font_pt']>=5 for p in v['pages']) for v in report['formats'].values()) else 'failed'
    (qa/'render-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
