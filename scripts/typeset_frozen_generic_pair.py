"""Typeset an authorized composition from two approved generic Writer snapshots."""
import argparse,copy,json,os,re,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.modeling_paper import sha,inside,writing_context,require_review_for_export


def save(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def esc(s):
    mapping={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}'}
    return ''.join(mapping.get(c,c) for c in s)


def reference_docx(path):
    from docx import Document
    from docx.shared import Mm,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document();section=doc.sections[0];section.page_width=Mm(210);section.page_height=Mm(297)
    section.top_margin=section.bottom_margin=section.left_margin=section.right_margin=Mm(20)
    for name in ['Normal','Body Text','First Paragraph','Title','Subtitle','Heading 1','Heading 2','Heading 3','Caption','Table','Abstract','Bibliography']:
        if name not in doc.styles:continue
        style=doc.styles[name];style.font.name='Times New Roman';style.font.size=Pt(12);style.font.color.rgb=RGBColor(0,0,0)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'SimSun')
        pf=style.paragraph_format;pf.space_after=Pt(5);pf.line_spacing=1.3
        if name in ['Normal','Body Text','First Paragraph']:pf.first_line_indent=Mm(8.5)
        if name.startswith('Heading') or name=='Title':
            style.font.name='SimHei';style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'SimHei');style.font.bold=True;style.font.size=Pt(18 if name=='Title' else (14 if name=='Heading 1' else 12));pf.keep_with_next=True;pf.space_before=Pt(12);pf.space_after=Pt(6);pf.first_line_indent=Mm(0)
        if name=='Title':pf.alignment=1
        if name=='Caption':pf.alignment=1;pf.first_line_indent=Mm(0);style.font.size=Pt(10.5)
    for node in doc.styles['Title'].element.xpath('.//w:pBdr'):node.getparent().remove(node)
    footer=section.footer.paragraphs[0];footer.alignment=1
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    doc.save(path)


def verify_assembly_authorization(source):
    from modelcrew.workflow import Workflow
    from modelcrew import hand_runtime as hr
    from modelcrew.modeling_paper import validate_draft
    authorization=json.loads((source/'assembly-authorization.json').read_text(encoding='utf-8'))
    frozen=ROOT/authorization['frozen_input_manifest']
    if sha(frozen)!=authorization['frozen_input_manifest_sha256']:raise ValueError('Frozen input manifest changed')
    manifest=json.loads(frozen.read_text(encoding='utf-8'))
    for item in manifest['files']:
        if sha(frozen.parent/item['snapshot'])!=item['sha256']:raise ValueError('Frozen input bytes changed')
    if sha(source/'单题论文-中文审阅稿.md')!=authorization['combined_markdown_sha256'] or sha(source/'figure-catalog.json')!=authorization['combined_catalog_sha256']:raise ValueError('Composition changed after authorization snapshot')
    checks={}
    with Workflow() as w:
        for chapter in manifest['chapters']:
            state=w.hand_status(chapter['task_id'],chapter['generic_writer_run_id'])
            if state['phase']!='READY_FOR_E_EXPORT' or not state['reviews']['can_export']:raise ValueError('Current generic Writer dual approval required')
            if state['binding']!=chapter['binding']:raise ValueError('Current execution or result version differs')
            row=hr.load(w,chapter['task_id'],chapter['generic_writer_run_id']);folder=hr.run_folder(row)
            if sha(ROOT/row['payload']['manuscript'])!=chapter['manuscript_sha256'] or sha(folder/'figure-catalog.json')!=chapter['figure_catalog_sha256']:raise ValueError('Approved source changed')
            checks[chapter['question_id']]={'generic_writer_run_id':chapter['generic_writer_run_id'],'current_separate_source_approvals':'approved','binding':chapter['binding'],'original_hashes_verified':True}
    report=validate_draft(source/'单题论文-中文审阅稿.md',source/'figure-catalog.json')
    if report['status']!='passed':raise ValueError(report['findings'])
    return {'source_approval_checks':checks,'composition_mechanical_checks':report,'assembly_authorized':True,'authorization_statement':authorization['user_statement'],'combined_manuscript_user_approval_inferred':False,'editorial_adjustments':authorization['editorial_adjustments'],'W2':'pending'}

def build(source,output,pandoc,compiler):
    context=writing_context();source=source.resolve();output=output.resolve()
    approved=verify_assembly_authorization(source)
    catalog=json.loads((source/'figure-catalog.json').read_text(encoding='utf-8'))
    source_hashes={name:sha(source/name) for name in ['单题论文-中文审阅稿.md','figure-catalog.json','assembly-authorization.json']}
    output.mkdir(parents=True,exist_ok=False);(output/'figures').mkdir();(output/'build').mkdir()
    (output/'fonts').mkdir()
    for name in ['simsun.ttc','simhei.ttf','simkai.ttf','simfang.ttf','times.ttf','timesbd.ttf','timesi.ttf','timesbi.ttf']:shutil.copyfile(Path('C:/Windows/Fonts')/name,output/'fonts'/name)
    for name in source_hashes:shutil.copyfile(source/name,output/name)
    for figure in catalog['figures']:
        for asset in figure['files'].values():
            dest=inside(output,asset['path']);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(inside(source,asset['path']),dest)
    for name in ['selected-results.csv','constraint-diagnostics.csv','result1.xlsx','result2.xlsx','数值精度区间.json']:
        if (source/name).exists():shutil.copyfile(source/name,output/name)
    save(output/'writer-context.json',context);save(output/'approval-check.json',approved)
    calls=[]
    def convert(args,data=None):
        result=subprocess.run([str(pandoc.resolve()),*args],input=data,capture_output=True,timeout=600,cwd=output)
        calls.append({'args':args,'returncode':result.returncode,'stderr':result.stderr.decode('utf-8',errors='replace')})
        if result.returncode:raise RuntimeError('Pandoc failed: '+calls[-1]['stderr'])
        return result.stdout.replace(b"\r\n",b"\n")
    md=output/'单题论文-中文审阅稿.md'
    ast=json.loads(convert(['-f','markdown-implicit_figures+tex_math_dollars','-t','json',str(md)]))
    save(output/'build/source-ast.json',ast)
    title=md.read_text(encoding='utf-8').splitlines()[0].removeprefix('# ')
    blocks=copy.deepcopy(ast['blocks']);assert blocks[0]['t']=='Header' and blocks[0]['c'][0]==1;blocks=blocks[1:]
    for block in blocks:
        if block['t']=='Header':block['c'][0]-=1
    base={**ast,'blocks':blocks,'meta':{'title':{'t':'MetaInlines','c':[{'t':'Str','c':title}]}}}
    figures={f['files']['png']['path']:f for f in catalog['figures'] if f['formal']}
    latex_blocks=[];i=0;embedded=[]
    while i<len(blocks):
        block=blocks[i]
        if block['t']=='Header' and any(x.get('c')=='一、问题重述' for x in block['c'][2]):
            latex_blocks.append({'t':'RawBlock','c':['latex',r'\clearpage']})
        if block['t']=='Para' and len(block['c'])==1 and block['c'][0]['t']=='Image':
            image=block['c'][0];path=image['c'][2][0];figure=figures[path];caption=blocks[i+1]
            caption_tex=convert(['-f','json','-t','latex'],json.dumps({**ast,'blocks':[caption]},ensure_ascii=False).encode()).decode().strip()
            pdf=figure['files']['pdf']['path']
            raw=r'\begin{figure}[H]\centering'+'\n'+r'\includegraphics[width=\linewidth]{'+pdf+'}\n'+r'\caption*{'+caption_tex+'}\n'+r'\end{figure}'
            latex_blocks.append({'t':'RawBlock','c':['latex',raw]});embedded.append({'id':figure['id'],'number':figure['number'],'pdf':pdf,'sha256':figure['files']['pdf']['sha256'],'width_mm':170});i+=2;continue
        if block['t']=='Table':latex_blocks.extend([{'t':'RawBlock','c':['latex',r'\begingroup\small']},block,{'t':'RawBlock','c':['latex',r'\endgroup']}])
        else:latex_blocks.append(block)
        i+=1
    if len(embedded)!=len(figures):raise ValueError('Not all approved figures embedded')
    latex=convert(['-f','json','-t','latex','--wrap=none'],json.dumps({**base,'blocks':latex_blocks},ensure_ascii=False).encode()).decode()
    latex=re.sub(r'https?://[^\s{}]+',lambda m:r'\url{'+m.group(0)+'}',latex)
    latex=latex.replace(r'\begin{longtable}[]{',r'\begin{longtable}[]{')
    # Pandoc column widths slightly exceed the line width after rounding.
    latex=latex.replace('\\real{0.1429}','\\real{0.1428}')
    latex=re.sub(r'(?m)^独立差分误差用于交叉核验实现；[^\n]+',lambda m:r'{\raggedright '+m[0]+r'\par}',latex)
    preamble=r'''\documentclass[UTF8,fontset=none,12pt,a4paper]{ctexart}
\usepackage{amsmath,amssymb,geometry,graphicx,float,booktabs,longtable,array,calc,caption,url}
\usepackage[hidelinks]{hyperref}
\usepackage{fontspec}
\setmainfont[Path=fonts/,BoldFont=timesbd.ttf,ItalicFont=timesi.ttf,BoldItalicFont=timesbi.ttf]{times.ttf}
\setCJKmainfont[Path=fonts/,BoldFont=simhei.ttf,ItalicFont=simkai.ttf]{simsun.ttc}
\setCJKsansfont[Path=fonts/]{simhei.ttf}
\setCJKmonofont[Path=fonts/]{simfang.ttf}
\providecommand{\heiti}{\sffamily}
\geometry{left=20mm,right=20mm,top=20mm,bottom=20mm}
\setcounter{secnumdepth}{-1}
\ctexset{section={format=\heiti\zihao{4},beforeskip=14pt,afterskip=8pt},subsection={format=\heiti\zihao{-4},beforeskip=10pt,afterskip=6pt}}
\linespread{1.3}\setlength{\parindent}{2em}\setlength{\parskip}{3pt}
\setlength{\tabcolsep}{4pt}\renewcommand{\arraystretch}{1.2}
\setlength{\LTpre}{6pt}\setlength{\LTpost}{6pt}
\captionsetup{font=small,justification=centering}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\passthrough}[1]{#1}
\providecommand{\pandocbounded}[1]{#1}
\newlength{\cslhangindent}\setlength{\cslhangindent}{1.5em}
\newlength{\csllabelwidth}\setlength{\csllabelwidth}{3em}
\raggedbottom\emergencystretch=2em
\widowpenalty=10000\clubpenalty=10000\displaywidowpenalty=10000
\begin{document}
\begin{center}{\heiti\zihao{2}TITLE}\end{center}
'''.replace('TITLE',esc(title).replace('的板凳龙',r'的\\板凳龙'))
    tex=output/'paper.tex';tex.write_text(preamble+latex+'\n\\end{document}\n',encoding='utf-8')
    # A separate DOCX AST retains the same prose/images, replacing only unsupported equation tags by visible numbers.
    doc_ast=copy.deepcopy(base)
    def walk(value):
        if isinstance(value,dict):
            if value.get('t')=='Para':
                new=[]
                for inline in value['c']:
                    if inline.get('t')=='Math' and inline['c'][0]['t']=='DisplayMath':
                        expr=inline['c'][1].replace(r'\Bigl',r'\left').replace(r'\Bigr',r'\right');tag=re.search(r'\\tag\{([^}]+)\}',expr)
                        inline['c'][1]=re.sub(r'\\tag\{[^}]+\}','',expr)
                        new.append(inline)
                        if tag:new += [{'t':'Space'},{'t':'Str','c':'('+tag.group(1)+')'}]
                    else:new.append(inline)
                value['c']=new
            if value.get('t')=='Image':value['c'][0][2]=[['width','170mm']]
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(doc_ast);save(output/'build/docx-ast.json',doc_ast)
    ref=output/'build/reference.docx';reference_docx(ref)
    convert(['-f','json','-t','docx','--standalone','--resource-path',str(output),'--reference-doc',str(ref),'-o',str(output/'paper.docx')],json.dumps(doc_ast,ensure_ascii=False).encode())
    if any('Could not convert TeX math' in call['stderr'] for call in calls):raise RuntimeError('Unrendered Word math; inspect conversion log')
    from docx import Document
    from docx.shared import Pt,Mm
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document(output/'paper.docx')
    for p in doc.paragraphs:
        if p.text==title and '的板凳龙' in title:
            first,last=title.split('的板凳龙',1);p.clear();p.add_run(first+'的').add_break();p.add_run('板凳龙'+last)
        if p.text=='一、问题重述':p.paragraph_format.page_break_before=True
        if p._p.xpath('.//w:drawing'):
            p.alignment=1;p.paragraph_format.first_line_indent=Mm(0);p.paragraph_format.keep_with_next=True;p.paragraph_format.space_after=Pt(3)
        elif re.match(r'^图\d+ ',p.text):p.style=doc.styles['Caption'];p.paragraph_format.keep_with_next=False
        elif re.match(r'^表\d+ ',p.text):p.paragraph_format.keep_with_next=True;p.paragraph_format.first_line_indent=Mm(0);p.alignment=1
        if p._p.xpath('.//m:oMath'):
            for element in p._p.xpath('.//m:oMath//w:rPr'):
                for child in list(element):
                    if child.tag==qn('w:sz'):child.set(qn('w:val'),'22')
    # Keep native equation objects editable; place their existing numbers on the same baseline.
    for p in doc.paragraphs:
        displays=p._p.xpath('./m:oMathPara')
        if not displays:continue
        number=p.text.strip()
        equations=[node for display in displays for node in display.findall(qn('m:oMath'))]
        for display in displays:
            for node in display.findall(qn('m:oMath')):display.remove(node)
        for child in list(p._p):
            if child.tag!=qn('w:pPr'):p._p.remove(child)
        p.paragraph_format.first_line_indent=Mm(0);p.paragraph_format.keep_together=True
        p.paragraph_format.space_before=Pt(6);p.paragraph_format.space_after=Pt(6)
        if re.fullmatch(r'\(\d+\)',number):
            from docx.enum.text import WD_TAB_ALIGNMENT
            p.alignment=0;p.paragraph_format.tab_stops.add_tab_stop(Mm(85),WD_TAB_ALIGNMENT.CENTER);p.paragraph_format.tab_stops.add_tab_stop(Mm(170),WD_TAB_ALIGNMENT.RIGHT)
            p.add_run('\t')
            for node in equations:p._p.append(node)
            p.add_run('\t'+number)
        else:
            p.alignment=1
            for node in equations:p._p.append(node)
    paragraphs=list(doc.paragraphs)
    for i,p in enumerate(paragraphs):
        number=p.text.strip()
        if i==0 or not re.fullmatch(r'\(\d+\)',number):continue
        previous=paragraphs[i-1]
        if previous.text.strip() or not previous._p.xpath('./m:oMath'):continue
        from docx.enum.text import WD_TAB_ALIGNMENT
        previous.alignment=0;previous.paragraph_format.first_line_indent=Mm(0)
        previous.paragraph_format.tab_stops.add_tab_stop(Mm(85),WD_TAB_ALIGNMENT.CENTER)
        previous.paragraph_format.tab_stops.add_tab_stop(Mm(170),WD_TAB_ALIGNMENT.RIGHT)
        run=OxmlElement('w:r');run.append(OxmlElement('w:tab'));previous._p.insert(1,run)
        previous.add_run('\t'+number)
        p._p.getparent().remove(p._p)
    for table in doc.tables:
        table.autofit=False
        columns=len(table.columns);headers=' '.join(c.text for c in table.rows[0].cells)
        widths=([42]+[128/6]*6) if columns==7 else ([32,105,33] if columns==3 and '符号' in headers else [55,60,55] if columns==3 else [24,18,64,64] if columns==4 and '下界' in headers else [55,38,38,39] if columns==4 else [170/columns]*columns)
        for col,width in zip(table.columns,widths):col.width=Mm(width)
        for row in table.rows:
            for cell,width in zip(row.cells,widths):
                cell.width=Mm(width)
                margins=OxmlElement('w:tcMar')
                for side in ['top','bottom','left','right']:
                    margin=OxmlElement('w:'+side);margin.set(qn('w:w'),'60');margin.set(qn('w:type'),'dxa');margins.append(margin)
                cell._tc.get_or_add_tcPr().append(margins)
        borders=OxmlElement('w:tblBorders')
        for edge in ['top','bottom','left','right','insideH','insideV']:
            e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
        table._tbl.tblPr.append(borders)
        for cell in table.rows[0].cells:
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E8EEF5');cell._tc.get_or_add_tcPr().append(shade)
            border=OxmlElement('w:tcBorders');line=OxmlElement('w:bottom');line.set(qn('w:val'),'single');line.set(qn('w:sz'),'4');line.set(qn('w:color'),'D9D9D9');border.append(line);cell._tc.get_or_add_tcPr().append(border)
        repeat=OxmlElement('w:tblHeader');table.rows[0]._tr.get_or_add_trPr().append(repeat)
        for row in table.rows:
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent=Mm(0);p.paragraph_format.line_spacing=1.1
                    for run in p.runs:run.font.size=Pt(10)
    doc.save(output/'paper.docx')
    save(output/'build/conversion-log.json',calls)
    cache=ROOT/'stage-c-plus/tex-cache';cache.mkdir(exist_ok=True)
    command=[str(compiler.resolve()),'--untrusted','--keep-logs','--keep-intermediates','--outdir',str(output),str(tex)]
    env={**os.environ,'TECTONIC_CACHE_DIR':str(cache),'TEMP':str(cache),'TMP':str(cache)}
    result=subprocess.run(command,capture_output=True,timeout=600,env=env,cwd=output)
    (output/'build/latex.stdout.log').write_bytes(result.stdout);(output/'build/latex.stderr.log').write_bytes(result.stderr)
    save(output/'build-command.json',{'command':command,'returncode':result.returncode,'cache':'stage-c-plus/tex-cache','network':'Compiler may provision missing TeX resources; no paper data sent to an LLM.'})
    if result.returncode:raise RuntimeError('Actual Chinese LaTeX compile failed; inspect build logs')
    assert all(sha(source/name)==value for name,value in source_hashes.items())
    save(output/'build-manifest.json',{'created_at':datetime.now(timezone.utc).isoformat(),'source_bundle':str(source.relative_to(ROOT)),'source_hashes':source_hashes,'figures':embedded,'source_unchanged':True,'new_figures_generated':0,'compiler_sha256':sha(compiler),'pandoc_sha256':sha(pandoc),'script_sha256':sha(Path(__file__)),'layout':'Chinese A4 research paper; not verified against year-specific official submission rules','figure_count':len(embedded),'word_equations':'Native OMML; equation tags rendered as visible numbers','manual_review':'pending'})
    print(json.dumps({'output':str(output),'pdf':True,'tex':True,'docx':True,'figures':len(embedded)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--pandoc',type=Path,default=ROOT/'stage-c-plus/tools/pandoc/pandoc.exe');p.add_argument('--compiler',type=Path,default=ROOT/'stage-c-plus/tools/tectonic.exe');a=p.parse_args();build(a.source,a.output,a.pandoc,a.compiler)
