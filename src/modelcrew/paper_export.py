"""Export an explicitly approved Chinese manuscript from one frozen Markdown source."""
import argparse,copy,json,os,re,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.tool_discovery import discover_tool,tex_cache_directory
from modelcrew.modeling_paper import sha,inside,writing_context,require_review_for_export
from modelcrew.paper_layout import contract as layout_contract, frontmatter, split_ast, rendered_frontmatter, text_of


def save(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def esc(s):
    mapping={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}'}
    return ''.join(mapping.get(c,c) for c in s)


def normalize_longtable_widths(latex):
    """Undo Pandoc's four-decimal column rounding without scaling table text."""
    from decimal import Decimal, ROUND_FLOOR
    def table(match):
        value=match[0]
        weights=[Decimal(v) for v in re.findall(r'\\real\{([0-9.]+)\}',value)]
        total=sum(weights)
        if not weights or abs(total-1)<=Decimal('0.000000001'):return value
        return re.sub(r'\\real\{([0-9.]+)\}',lambda m:r'\real{'+str((Decimal(m[1])/total).quantize(Decimal('0.0000000001'),rounding=ROUND_FLOOR))+'}',value)
    return re.sub(r'\\begin\{longtable\}[\s\S]*?\\toprule',table,latex)


def reference_layout(latex):
    """Use ragged-right layout for bibliography URLs, preserving reference text."""
    pattern=r'(\\section\{参考文献\}[^\n]*\n)([\s\S]*?)(?=\\section\{|\Z)'
    return re.sub(pattern,lambda match:match[1]+r'\begingroup\raggedright'+'\n'+match[2]+r'\par\endgroup'+'\n',latex)


def latex_line_breaks(latex):
    """Offer line breaks in table math and inline code without changing tokens."""
    def table(match):
        def math(expr):
            value=re.sub(r'(=|,|\\approx\b|\\times\b)',lambda m:m[0]+r'\allowbreak ',expr[1])
            return r'\('+value+r'\)'
        return re.sub(r'\\\(([\s\S]*?)\\\)',math,match[0])
    latex=re.sub(r'\\begin\{longtable\}[\s\S]*?\\end\{longtable\}',table,latex)
    def code(match):
        return r'\texttt{'+re.sub(r'([.(=])',lambda m:m[0]+r'\allowbreak ',match[1])+'}'
    return re.sub(r'\\texttt\{((?:[^{}]|\{[^{}]*\})*)\}',code,latex)


def figure_embedding(source,figure,width_mm=160):
    """Crop only measured white outer margins when small labels need more room."""
    import math
    import fitz
    from PIL import Image, ImageChops
    def box(image,pad):
        image=image.convert('RGB')
        bounds=ImageChops.difference(image,Image.new('RGB',image.size,'white')).getbbox()
        if bounds is None:raise ValueError('Empty figure')
        return [max(0,bounds[0]-pad),max(0,bounds[1]-pad),min(image.width,bounds[2]+pad),min(image.height,bounds[3]+pad)]
    with fitz.open(inside(source,figure['files']['pdf']['path'])) as d:
        if len(d)!=1:raise ValueError('One-page figure PDF required')
        page=d[0]
        fonts=[s['size'] for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans'] if s['text'].strip()]
        minimum=min(fonts,default=0)*width_mm/(page.rect.width*25.4/72)
        if minimum>=5:return {'crop':False,'width_mm':width_mm,'minimum_label_pt':minimum}
        pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
        image=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
        bounds=box(image,math.ceil(.5*72/25.4*2))
        left,top,right,bottom=[v/2 for v in bounds]
        effective_min=min(fonts)*width_mm/((right-left)*25.4/72)
        if effective_min<5:raise ValueError('Figure labels need a new layout; safe outer whitespace crop is insufficient')
        pdf_trim=[left,page.rect.height-bottom,page.rect.width-right,top]
    with Image.open(inside(source,figure['files']['png']['path'])) as image:
        dpi=image.info.get('dpi',(300,300))[0];bounds=box(image,math.ceil(.5*dpi/25.4))
        a,b,c,e=bounds
        png_crop={'l':round(a/image.width*100000),'t':round(b/image.height*100000),
                  'r':round((image.width-c)/image.width*100000),'b':round((image.height-e)/image.height*100000)}
        ratio=(e-b)/(c-a)
    return {'crop':True,'width_mm':width_mm,'height_mm':width_mm*ratio,'pdf_trim_pt':pdf_trim,
            'png_crop_100000':png_crop,'minimum_label_pt_before':minimum,'minimum_label_pt_after':effective_min,
            'scope':'Only detected outer white margins, with 0.5 mm safety padding; original assets unchanged'}


def separate_image_captions(ast, catalog):
    """Split only exact catalog captions joined to images by a soft line break.

    This is an AST layout transform; the approved Markdown stays byte-identical.
    Narrative text following an image must never be mistaken for its caption.
    """
    result=copy.deepcopy(ast); captions={f['files']['png']['path']:'\u56fe'+str(f['number'])+' '+f['title'] for f in catalog['figures'] if f['formal']}
    blocks=[];changes=[]
    for block in result['blocks']:
        inlines=block.get('c',[]) if block.get('t')=='Para' else []
        if (len(inlines)>=3 and inlines[0].get('t')=='Image'
                and inlines[1].get('t') in ('SoftBreak','LineBreak')):
            path=inlines[0]['c'][2][0]
            if path in captions and text_of(inlines[2:]).strip()==captions[path]:
                blocks.extend([{'t':'Para','c':[inlines[0]]},{'t':'Para','c':inlines[2:]}])
                changes.append({'image':path,'caption':captions[path],'operation':'separate_image_and_exact_caption'})
                continue
        blocks.append(block)
    result['blocks']=blocks
    return result,changes


def set_symbol_table_widths(ast):
    """Reserve most of the global table for meaning, preserving every cell."""
    for block in ast['blocks']:
        if block['t']=='Table' and len(block['c'][2]) in (4,5) and '适用范围' in text_of(block['c'][3]):
            widths=[0.18,0.52,0.10,0.20] if len(block['c'][2])==4 else [0.11,0.27,0.13,0.20,0.29]
            for column,width in zip(block['c'][2],widths):
                column[1]={'t':'ColWidth','c':width}
    return ast


def word_math_compatible(expr):
    """Use equivalent scalable delimiters accepted by Pandoc's OMML writer."""
    expr=re.sub(r'\\tag\{[^}]+\}','',expr)
    expr=re.sub(r'\\(?:big|Big|bigg|Bigg)([lr])',lambda m:r'\left' if m[1]=='l' else r'\right',expr)
    if r'\rho_k(a)=' in expr and r'g_{ij}=' in expr and r'\qquad' in expr:
        first,second=expr.split(r'\qquad',1)
        expr=r'\begin{aligned}'+first+r'\\'+second+r'\end{aligned}'
    return expr


def reference_docx(path):
    from docx import Document
    from docx.shared import Mm,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document();section=doc.sections[0];section.page_width=Mm(210);section.page_height=Mm(297)
    section.top_margin=section.bottom_margin=section.left_margin=section.right_margin=Mm(25)
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


def _build(source,output,pandoc,compiler,attempt_id):
    output=output.resolve()
    output.mkdir(parents=True,exist_ok=False);(output/'figures').mkdir();(output/'build').mkdir()
    save(output/'build-attempt.json',{'attempt_id':attempt_id,'state':'building','scope':'Approved-source export attempt; workflow approvals, visual review and W2 remain separate'})
    pandoc=discover_tool('pandoc',pandoc);compiler=discover_tool('tectonic',compiler)
    context=writing_context();layout=layout_contract(context);source=source.resolve()
    frontmatter((source/'单题论文-中文审阅稿.md').read_text(encoding='utf-8'))
    review=json.loads((source/'user-review-confirmed.json').read_text(encoding='utf-8'))
    approved=require_review_for_export(source/'单题论文-中文审阅稿.md',source/'figure-catalog.json',review)
    catalog=json.loads((source/'figure-catalog.json').read_text(encoding='utf-8'))
    source_hashes={name:sha(source/name) for name in ['单题论文-中文审阅稿.md','figure-catalog.json','user-review-confirmed.json']}
    (output/'fonts').mkdir()
    for name in ['simsun.ttc','simhei.ttf','simkai.ttf','simfang.ttf','times.ttf','timesbd.ttf','timesi.ttf','timesbi.ttf']:shutil.copyfile(Path('C:/Windows/Fonts')/name,output/'fonts'/name)
    for name in source_hashes:shutil.copyfile(source/name,output/name)
    for figure in catalog['figures']:
        for asset in figure['files'].values():
            dest=inside(output,asset['path']);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(inside(source,asset['path']),dest)
    from modelcrew.figure_tools import audit_catalog
    audit_catalog(output/'figure-catalog.json',output/'build/figure-check')
    for name in ['selected-results.csv','constraint-diagnostics.csv']:
        if (source/name).exists():shutil.copyfile(source/name,output/name)
    save(output/'writer-context.json',context);save(output/'approval-check.json',approved);save(output/'format-requirement-map.json',layout)
    calls=[]
    def convert(args,data=None):
        from modelcrew.latex_tools import run_logged
        name='pandoc-'+str(len(calls)+1).zfill(3)
        try:
            raw=run_logged([str(pandoc.resolve()),*args],output/'build',name,
                           cwd=output,timeout=600,input_data=data,raw_output=True)
        finally:
            result_path=output/'build'/(name+'-result.json')
            if result_path.exists():
                result=json.loads(result_path.read_text(encoding='utf-8'))
                error=(output/'build'/(name+'-stderr.log')).read_text(encoding='utf-8',errors='replace')
                calls.append({'args':args,'returncode':result['returncode'],'stderr':error,'status':result['status']})
                save(output/'build/conversion-log.json',calls)
        if 'Could not convert TeX math' in calls[-1]['stderr']:
            raise RuntimeError('Pandoc failed to produce editable math; inspect conversion logs')
        return raw.replace(b"\r\n",b"\n")
    md=output/'单题论文-中文审阅稿.md'
    ast=json.loads(convert(['-f','markdown-implicit_figures+tex_math_dollars','-t','json',str(md)]))
    ast,caption_layout=separate_image_captions(ast,catalog)
    save(output/'build/caption-layout-transform.json',{'changes':caption_layout,'approved_markdown_unchanged':True})
    ast=set_symbol_table_widths(ast)
    save(output/'build/source-ast.json',ast)
    title=md.read_text(encoding='utf-8').splitlines()[0].removeprefix('# ')
    parts=split_ast(ast)
    blocks=parts['body']
    base={**ast,'blocks':blocks,'meta':{'title':{'t':'MetaInlines','c':[{'t':'Str','c':title}]}}}
    abstract_tex=convert(['-f','json','-t','latex','--wrap=none'],json.dumps({**ast,'blocks':parts['abstract']},ensure_ascii=False).encode()).decode().strip()
    keywords_tex=convert(['-f','json','-t','latex','--wrap=none'],json.dumps({**ast,'blocks':parts['keywords']},ensure_ascii=False).encode()).decode().strip()
    figures={f['files']['png']['path']:f for f in catalog['figures'] if f['formal']}
    placements={f['id']:figure_embedding(output,f) for f in figures.values()}
    latex_blocks=[];i=0;embedded=[]
    while i<len(blocks):
        block=blocks[i]
        if block['t']=='Para' and len(block['c'])==1 and block['c'][0]['t']=='Image':
            image=block['c'][0];path=image['c'][2][0];figure=figures[path];caption=blocks[i+1]
            caption_tex=convert(['-f','json','-t','latex'],json.dumps({**ast,'blocks':[caption]},ensure_ascii=False).encode()).decode().strip()
            pdf=figure['files']['pdf']['path']
            place=placements[figure['id']]
            crop=',trim='+' '.join(f'{v:.5f}pt' for v in place['pdf_trim_pt'])+',clip' if place['crop'] else ''
            raw=r'\begin{figure}[H]\centering'+'\n'+r'\includegraphics[width=\linewidth'+crop+']{'+pdf+'}\n'+r'\caption*{'+caption_tex+'}\n'+r'\end{figure}'
            latex_blocks.append({'t':'RawBlock','c':['latex',raw]});embedded.append({'id':figure['id'],'number':figure['number'],'pdf':pdf,'sha256':figure['files']['pdf']['sha256'],'width_mm':160,'placement':place});i+=2;continue
        if block['t']=='Para' and i+1<len(blocks) and blocks[i+1]['t']=='Table' and re.match(r'^表\d+ ',text_of(block)):
            latex_blocks.append({'t':'RawBlock','c':['latex',r'\par\begingroup\dimen0=\dimexpr\pagegoal-\pagetotal\relax\ifdim\dimen0<7\baselineskip\clearpage\fi\endgroup']})
        if block['t']=='Table':latex_blocks.extend([{'t':'RawBlock','c':['latex',r'\begingroup\small']},block,{'t':'RawBlock','c':['latex',r'\endgroup']}])
        else:latex_blocks.append(block)
        i+=1
    if len(embedded)!=len(figures):raise ValueError('Not all approved figures embedded')
    latex=convert(['-f','json','-t','latex','--wrap=none'],json.dumps({**base,'blocks':latex_blocks},ensure_ascii=False).encode()).decode()
    latex=re.sub(r'https?://[^\s{}]+',lambda m:r'\url{'+m.group(0)+'}',latex)
    latex=latex_line_breaks(reference_layout(normalize_longtable_widths(latex)))
    # Keep the approved display equation with its preceding explanation.
    latex=latex.replace('\n\n'+r'\[', '\n\n'+r'\nopagebreak[4]'+'\n'+r'\[')
    # Use the actually read Chinese baseline preamble. Replace only the
    # documented sample body slots, with explicit local font/tool mappings.
    main=next(d['text'] for d in context['documents'] if d['path']==layout['template'])
    preamble=main.split(r'\begin{document}',1)[0]
    preamble=preamble.replace('[UTF8,12pt,a4paper]','[UTF8,fontset=none,12pt,a4paper]')
    preamble=preamble.replace('LATEX_TEMPLATE_TITLE',esc(title))
    # Replace baseline font mappings once, rather than redefining CJK families.
    preamble=re.sub(r'^\\set(?:mainfont|CJKmainfont|CJKsansfont|CJKmonofont)\b[^\n]*\n?', '', preamble, flags=re.M)
    preamble+=r'''
\usepackage{fontspec,float,longtable,array,calc,caption,url}
\setmainfont[Path=fonts/,BoldFont=timesbd.ttf,ItalicFont=timesi.ttf,BoldItalicFont=timesbi.ttf]{times.ttf}
\setCJKmainfont[Path=fonts/,BoldFont=simhei.ttf,ItalicFont=simkai.ttf]{simsun.ttc}
\setCJKsansfont[Path=fonts/]{simhei.ttf}
\setCJKmonofont[Path=fonts/]{simfang.ttf}
\providecommand{\heiti}{\sffamily}
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
\hypersetup{pageanchor=false}
\maketitle
\thispagestyle{empty}
\begin{abstract}
\normalsize
'''
    front=abstract_tex+'\n\\keywords{'+keywords_tex+'}\n\\end{abstract}\n\\clearpage\n\\pagenumbering{arabic}\n\\hypersetup{pageanchor=true}\n'
    tex=output/'paper.tex';tex.write_text(preamble+front+latex+'\n\\end{document}\n',encoding='utf-8')
    # A separate DOCX AST retains the same prose/images, replacing only unsupported equation tags by visible numbers.
    doc_ast=copy.deepcopy({**base,'blocks':parts['word_blocks']})
    def walk(value):
        if isinstance(value,dict):
            if value.get('t')=='Para':
                new=[]
                for inline in value['c']:
                    if inline.get('t')=='Math' and inline['c'][0]['t']=='DisplayMath':
                        expr=inline['c'][1];tag=re.search(r'\\tag\{([^}]+)\}',expr)
                        inline['c'][1]=word_math_compatible(expr)
                        new.append(inline)
                        if tag:new += [{'t':'Space'},{'t':'Str','c':'('+tag.group(1)+')'}]
                    else:new.append(inline)
                value['c']=new
            if value.get('t')=='Image':value['c'][0][2]=[['width','160mm']]
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(doc_ast);save(output/'build/docx-ast.json',doc_ast)
    ref=output/'build/reference.docx';reference_docx(ref)
    convert(['-f','json','-t','docx','--standalone','--resource-path',str(output),'--reference-doc',str(ref),'-o',str(output/'paper.docx')],json.dumps(doc_ast,ensure_ascii=False).encode())
    from docx import Document
    from docx.shared import Pt,Mm
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document(output/'paper.docx')
    by_hash={f['files']['png']['sha256']:placements[f['id']] for f in figures.values()}
    import hashlib
    for shape in doc.inline_shapes:
        blip=shape._inline.xpath('.//a:blip')[0]
        rid=blip.get(qn('r:embed'));place=by_hash[hashlib.sha256(doc.part.related_parts[rid].blob).hexdigest()]
        if place['crop']:
            fill=shape._inline.xpath('.//pic:blipFill')[0]
            crop_node=OxmlElement('a:srcRect')
            for name,value in place['png_crop_100000'].items():crop_node.set(name,str(value))
            fill.insert(1,crop_node)
            shape.width=Mm(place['width_mm']);shape.height=Mm(place['height_mm'])
    caption_labels={'图'+str(f['number'])+' '+f['title'] for f in figures.values()}
    for p in doc.paragraphs:
        if p.text==title and len(title)>=24 and '与' in title:
            first,last=title.rsplit('与',1)
            if .35*len(title)<=len(first)<=.75*len(title):
                p.clear();p.add_run(first).add_break();p.add_run('与'+last)
        if p.text==title and '的板凳龙' in title:
            first,last=title.split('的板凳龙',1);p.clear();p.add_run(first+'的').add_break();p.add_run('板凳龙'+last)
        if p.text==parts['body_start_heading'] and p.style.name.startswith('Heading'):
            p.paragraph_format.page_break_before=True
        if p.text=='摘要':
            p.alignment=1
            p.paragraph_format.keep_with_next=True
        if p.text.startswith('关键词：'):
            p.paragraph_format.first_line_indent=Mm(0)
            p.paragraph_format.keep_with_next=False
        if p._p.xpath('.//w:drawing'):
            p.alignment=1;p.paragraph_format.first_line_indent=Mm(0);p.paragraph_format.keep_with_next=True;p.paragraph_format.space_after=Pt(3)
        elif p.text.strip() in caption_labels:p.style=doc.styles['Caption'];p.paragraph_format.keep_with_next=False
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
            p.alignment=0;p.paragraph_format.tab_stops.add_tab_stop(Mm(80),WD_TAB_ALIGNMENT.CENTER);p.paragraph_format.tab_stops.add_tab_stop(Mm(160),WD_TAB_ALIGNMENT.RIGHT)
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
        previous.paragraph_format.tab_stops.add_tab_stop(Mm(80),WD_TAB_ALIGNMENT.CENTER)
        previous.paragraph_format.tab_stops.add_tab_stop(Mm(160),WD_TAB_ALIGNMENT.RIGHT)
        run=OxmlElement('w:r');run.append(OxmlElement('w:tab'));previous._p.insert(1,run)
        previous.add_run('\t'+number)
        p._p.getparent().remove(p._p)
    paragraphs=list(doc.paragraphs)
    for previous,current in zip(paragraphs,paragraphs[1:]):
        if previous.text.rstrip().endswith(('：',':')) and re.fullmatch(r'\(\d+\)',current.text.strip()) and current._p.xpath('.//m:oMath'):
            previous.paragraph_format.keep_with_next=True
    for table in doc.tables:
        global_symbols=[c.text.strip() for c in table.rows[0].cells][:4]==['符号','含义','单位','适用范围']
        if global_symbols:
            weights=[.18,.52,.10,.20] if len(table.columns)==4 else [.11,.27,.13,.20,.29]
            for col,weight in zip(table.columns,weights):col.width=Mm(160*weight)
            for row in table.rows:
                for cell,weight in zip(row.cells,weights):cell.width=Mm(160*weight)
        table.autofit=False
        borders=OxmlElement('w:tblBorders')
        for edge in ['top','bottom','left','right','insideH','insideV']:
            e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single' if edge in ['top','bottom'] else 'nil');e.set(qn('w:sz'),'8');e.set(qn('w:color'),'000000');borders.append(e)
        table._tbl.tblPr.append(borders)
        for cell in table.rows[0].cells:
            border=OxmlElement('w:tcBorders');line=OxmlElement('w:bottom');line.set(qn('w:val'),'single');line.set(qn('w:sz'),'4');border.append(line);cell._tc.get_or_add_tcPr().append(border)
        repeat=OxmlElement('w:tblHeader');table.rows[0]._tr.get_or_add_trPr().append(repeat)
        if global_symbols:
            # Keep the header and at least three body rows together.
            for row in table.rows[:3]:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:paragraph.paragraph_format.keep_with_next=True
        for row in table.rows:
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent=Mm(0);p.paragraph_format.line_spacing=1.1
                    if global_symbols:p.paragraph_format.space_after=Pt(2);p.paragraph_format.space_before=Pt(0)
                    for run in p.runs:run.font.size=Pt(10.5)
    doc.save(output/'paper.docx')
    save(output/'build/conversion-log.json',calls)
    cache=tex_cache_directory(ROOT);cache.mkdir(parents=True,exist_ok=True)
    command=[str(compiler.resolve()),'--untrusted','--only-cached','--keep-logs','--keep-intermediates','--outdir',str(output),str(tex)]
    env={**os.environ,'TECTONIC_CACHE_DIR':str(cache),'TEMP':str(cache),'TMP':str(cache)}
    from modelcrew.latex_tools import run_logged
    try:
        run_logged(command,output/'build','latex',timeout=600,env=env,cwd=output)
    finally:
        result_path=output/'build/latex-result.json'
        if result_path.exists():
            result=json.loads(result_path.read_text(encoding='utf-8'))
            save(output/'build-command.json',{'command':command,'returncode':result['returncode'],
                 'status':result['status'],'cache':str(cache),'network':'Only cached TeX resources; no automatic provisioning'})
    log=(output/'paper.log').read_text(encoding='utf-8',errors='replace')
    findings=[line for line in log.splitlines() if re.search(r'undefined|Missing character|(?:Over|Under)full|(?:LaTeX|Package .*|Class .*|Font) Warning:',line,re.I)]
    save(output/'build/compiler-check.json',{'status':'failed' if findings else 'passed','findings':findings,'warning_exceptions':[]})
    if findings:raise RuntimeError('Unresolved compiler warnings; inspect compiler-check.json')
    from modelcrew.pdf_checks import inspect_pdf, verify_pdf_report
    pdf_checked=inspect_pdf(output/'paper.pdf',output/'build/latex-pdf-check')
    verify_pdf_report(output/'paper.pdf',output/'build/latex-pdf-check',pdf_checked)
    pagination=rendered_frontmatter(output/'paper.pdf',md.read_text(encoding='utf-8'))
    save(output/'build/abstract-page-check.json',pagination)
    if pagination['status']!='passed':raise RuntimeError('Abstract/title/keywords must fit on page 1; revise the abstract without shrinking fonts')
    assert all(sha(source/name)==value for name,value in source_hashes.items())
    save(output/'build-manifest.json',{'created_at':datetime.now(timezone.utc).isoformat(),'source_bundle':str(source.relative_to(ROOT)),'source_hashes':source_hashes,'figures':embedded,'source_unchanged':True,'new_figures_generated':0,'compiler_sha256':sha(compiler),'pandoc_sha256':sha(pandoc),'script_sha256':sha(Path(__file__)),'layout':'Chinese A4 research paper; not verified against year-specific official submission rules','figure_count':len(embedded),'word_equations':'Native OMML; equation tags rendered as visible numbers','manual_review':'pending','format_requirements':layout,'abstract_page_check':pagination,'latex_pdf_check_sha256':sha(output/'build/latex-pdf-check/pdf-check.json')})
    print(json.dumps({'output':str(output),'pdf':True,'tex':True,'docx':True,'figures':len(embedded)}))

def build(source,output,pandoc=None,compiler=None):
    """Preserve complete failure evidence in this newly owned export attempt."""
    import uuid
    token=uuid.uuid4().hex
    try:
        return _build(source,output,pandoc,compiler,token)
    except BaseException as exc:
        marker=Path(output)/'build-attempt.json'
        if marker.is_file() and json.loads(marker.read_text(encoding='utf-8')).get('attempt_id')==token:
            save(Path(output)/'build-error.json',{'status':'failed','error_type':type(exc).__name__,
                 'error':str(exc),'visual_review':'PENDING','W2':'NOT_RUN'})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--pandoc',type=Path,default=None);p.add_argument('--compiler',type=Path,default=None);a=p.parse_args();build(a.source,a.output,a.pandoc,a.compiler)
