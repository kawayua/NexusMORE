"""Read the selected Chinese baseline and enforce the user's one-page front matter."""
import copy
import re
from pathlib import Path

LEGACY_REQUIRED = ['resources/paper/reference/'+name for name in
                   ['章节模板.md','写作规范.md','论文格式规范.md','LaTeX格式规范.md','main.tex']]
REQUIRED = ['resources/paper/reference/'+name for name in
            ['chapter-template.md','writing-guidelines.md','paper-format.md','latex-format.md']] + [
                'resources/paper/templates/chinese-research/main.tex']


def heading(text):
    return re.sub(r'^[一二三四五六七八九十0-9]+[、.． ]+', '', text.strip())


def text_of(value):
    if isinstance(value,dict):
        if value.get('t') in ['Str','Code']:return value['c'] if isinstance(value['c'],str) else value['c'][-1]
        if value.get('t') in ['Space','SoftBreak','LineBreak']:return ' '
        return ''.join(text_of(v) for v in value.values())
    if isinstance(value,list):return ''.join(map(text_of,value))
    return ''


def frontmatter(markdown):
    parts=re.split(r'^##\s+(.+?)\s*$',markdown,flags=re.M)
    names=[heading(parts[n]) for n in range(1,len(parts),2)]
    if len(names)!=len(set(names)):raise ValueError('Duplicate paper sections')
    values={heading(parts[n]):parts[n+1].strip() for n in range(1,len(parts),2)}
    abstract=values.get('摘要','');keywords=values.get('关键词','')
    if not abstract or not keywords:raise ValueError('An abstract and keywords are required')
    if re.search(r'^#{1,6}\s|!\[|\$\$|^\|',abstract,flags=re.M):
        raise ValueError('Use one full-paper abstract without question subheadings, figures, tables or display equations')
    if re.search(r'^#{1,6}\s|!\[|^\|',keywords,flags=re.M):
        raise ValueError('Keywords must be one unified paragraph')
    if len(keywords.splitlines())!=1:raise ValueError('Keywords must be one unified paragraph')
    return {'abstract':abstract,'keywords':keywords,'abstract_characters':len(re.sub(r'\s+','',abstract))}


def contract(context):
    documents={d['path']:d for d in context['documents']}
    # A declared current workflow must not silently downgrade to historical references.
    current=context.get('workflow',{}).get('paper_reference_version')
    required=REQUIRED if current or set(REQUIRED)<=documents.keys() else LEGACY_REQUIRED
    if not set(required)<=documents.keys():raise ValueError('Typesetting requires reading all five selected template/reference files')
    main=documents[required[-1]]['text']
    if not re.search(r'\\documentclass\[[^]]*12pt[^]]*a4paper[^]]*\]\{ctexart\}',main):
        raise ValueError('Unsupported baseline document class; map the selected template explicitly')
    if r'\geometry{left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm}' not in main:
        raise ValueError('Selected template margins need an explicit mapping')
    return {'version':'1.1.0' if required==REQUIRED else '1.0.0','template':required[-1],
            'template_sha256':documents[required[-1]]['sha256'],
            'read_log':[{'path':p,'sha256':documents[p]['sha256']} for p in required],
            'source':'nexusmore_authored_chinese_research_baseline_1.0.0' if required==REQUIRED else 'bundled_chinese_research_baseline','official_compliance_verified':False,
            'page_mm':[210,297],'margins_mm':25,'body_font_pt':12,
            'frontmatter_max_pages':1,'frontmatter_includes':['title','abstract','keywords'],
            'body_starts_new_page':True,'shrink_text_to_fit':False,
            'bibliography':'approved Markdown numbered entries; no BibTeX/BibLaTeX backend selected',
            'mapping':{'page_and_margins':'A4 / ctexart 12pt / geometry from selected main.tex',
                       'fonts':'explicit local SimSun/SimHei and Times New Roman mapping; preserve 12pt body',
                       'frontmatter':'selected title+abstract+keywords frame; one page required after actual render',
                       'body':'approved structured Markdown replaces the baseline sample chapter placeholders',
                       'equations':'native LaTeX and editable Word OMML',
                       'tables_figures_references':'existing export adapter; actual rendered checks and W2 still required'}}


def split_ast(ast):
    blocks=copy.deepcopy(ast['blocks'])
    if not blocks or blocks[0]['t']!='Header' or blocks[0]['c'][0]!=1:raise ValueError('Paper title required')
    blocks=blocks[1:]
    for b in blocks:
        if b['t']=='Header':b['c'][0]-=1
    positions={}
    for n,b in enumerate(blocks):
        if b['t']=='Header' and b['c'][0]==1:
            name=heading(text_of(b['c'][2]))
            if name in ['摘要','关键词']:positions[name]=n
    a=positions.get('摘要');k=positions.get('关键词')
    if a is None or k is None or a>=k:raise ValueError('Abstract must precede keywords')
    body_start=next((n for n in range(k+1,len(blocks)) if blocks[n]['t']=='Header' and blocks[n]['c'][0]==1),None)
    if body_start is None:raise ValueError('Body section required')
    abstract=blocks[a+1:k];keywords=blocks[k+1:body_start];body=blocks[body_start:]
    if not abstract or any(b['t']!='Para' for b in abstract) or len(keywords)!=1 or keywords[0]['t']!='Para':
        raise ValueError('Abstract must contain prose paragraphs and keywords one paragraph')
    keypara={'t':'Para','c':[{'t':'Strong','c':[{'t':'Str','c':'关键词：'}]},*keywords[0]['c']]}
    return {'abstract':abstract,'keywords':keywords,'body':body,
            'word_blocks':[blocks[a],*abstract,keypara,*body],
            'body_start_heading':text_of(body[0]['c'][2])}


def rendered_frontmatter(pdf,markdown):
    import fitz
    front=frontmatter(markdown)
    key=re.sub(r'\s+','',front['keywords'])
    chunks=re.split(r'^##\s+(.+?)\s*$',markdown,flags=re.M)
    names=[heading(chunks[n]) for n in range(1,len(chunks),2)]
    body_name=names[names.index('关键词')+1]
    with fitz.open(pdf) as document:
        raw=[p.get_text(clip=fitz.Rect(0,50,p.rect.width,p.rect.height-45)) for p in document]
        texts=[''.join(t.split()) for t in raw]
    abstract_page=next((n+1 for n,t in enumerate(texts) if '摘要' in t),None)
    keywords_page=next((n+1 for n,t in enumerate(texts) if key in t and '关键词' in t),None)
    body_page=next((n+1 for n,t in enumerate(raw) if any(heading(line)==body_name for line in t.splitlines())),None)
    title=''.join(markdown.splitlines()[0].removeprefix('# ').split())
    title_page=next((n+1 for n,t in enumerate(texts) if title in t),None)
    passed=title_page==1 and abstract_page==1 and keywords_page==1 and body_page==2
    return {'status':'passed' if passed else 'failed','title_page':title_page,'abstract_start_page':abstract_page,
            'keywords_page':keywords_page,'body_start_page':body_page,
            'maximum_frontmatter_pages':1,'rule':'Title, full-paper abstract and keywords on page 1; body begins on page 2',
            'scope':'Actual rendered pagination, not an estimate from character count'}
