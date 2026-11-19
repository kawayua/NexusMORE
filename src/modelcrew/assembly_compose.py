"""Deterministic multi-question Markdown composition; never invents results."""
import copy
import json
import re
from pathlib import Path

from .collaboration import sha_file
from .contracts import digest
from .paper_layout import frontmatter
from . import assembly_symbols as symbols
from .modeling_paper import inside, policy, validate_draft

VERSION = 'assembly-compose-1.2.0'
MD_NAME = '单题论文-中文审阅稿.md'


def implementation_sha256():
    return digest({'composer':sha_file(Path(__file__)),
                   'symbols':sha_file(Path(symbols.__file__)),
                   'layout':sha_file(Path(__file__).with_name('paper_layout.py')),
                   'checker':sha_file(Path(__file__).with_name('modeling_paper.py'))})


def sections(text):
    chunks = re.split(r'^##\s+(.+?)\s*$', text, flags=re.M)
    result = {}
    for i in range(1, len(chunks), 2):
        name = re.sub(r'^[一二三四五六七八九十0-9]+[、.． ]+', '', chunks[i]).strip()
        if name in result:
            raise ValueError('Duplicate section: '+name)
        result[name] = chunks[i+1].strip()
    missing = set(policy()['required_sections'])-result.keys()
    if missing:
        raise ValueError('Missing source sections: '+str(sorted(missing)))
    return result



def numbered_references(text):
    """Accept explicit [n] and Markdown n. / n) entries without inventing sources."""
    refs = {}; current = None
    for line in text.splitlines():
        if not line.strip():continue
        match = re.fullmatch(r'\s*(?:\[(\d+)\]\s*|(\d+)[.)]\s+)(.+)',line)
        if match:
            current = str(int(match[1] or match[2]))
            if current == '0':raise ValueError('Invalid reference number')
            if current in refs:raise ValueError('Duplicate reference number')
            refs[current] = match[3].strip()
        elif current is None or re.match(r'^\s*(?:\[\d+\]|\d+[.)])\s*$',line):
            raise ValueError('References must use explicit numbered entries')
        else:refs[current] += '\n'+line
    return refs


def figure_asset_stem(question, figure_id):
    """Catalog IDs are semantic identifiers; filenames must also work on Windows."""
    original=question+'-'+figure_id
    if re.fullmatch(r'[A-Za-z0-9_.-]+',original):return original
    return question+'-figure-'+digest(figure_id)[:24]


def normalize(question, text, catalog, patches):
    if '@@ASM_' in text:
        raise ValueError('Reserved assembly marker in source')
    edits = []
    for patch in patches:
        if patch['question_id'] != question:
            continue
        before, after = patch['before'], patch['after']
        count = text.count(before)
        if not before or count != patch['expected_count']:
            raise ValueError('Patch occurrence mismatch: '+patch['reason'])
        text = text.replace(before, after)
        edits.append({**patch, 'actual_count': count})
    split = sections(text)
    # Give previously uncaptioned Markdown tables local identities so symbol
    # tables participate in global numbering too. Existing captions stay intact.
    next_table = max([int(n) for n in re.findall(r'^表(\d+)\s+', text, re.M)] or [0])
    generated_captions = []
    for name, body in list(split.items()):
        if name == '参考文献':
            continue
        original_body = body
        def caption(match):
            nonlocal next_table
            prefix = original_body[:match.start()].rstrip()
            if prefix and re.fullmatch(r'表\d+\s+.+',prefix.splitlines()[-1]):
                return match[0]
            next_table += 1
            title = '表'+str(next_table)+' '+name+'表'
            generated_captions.append({'section':name,'local_number':next_table,'caption':title})
            return title+'\n\n'+match[0]
        split[name] = re.sub(r'^\|[^\n]+\|\n\|[ :|\-]+\|(?:\n\|[^\n]*\|)*', caption, body, flags=re.M)
    refs = numbered_references(split.pop('参考文献'))
    figures = copy.deepcopy(catalog['figures'])
    formal = [f for f in figures if f['formal']]
    if len({f['number'] for f in formal}) != len(formal):
        raise ValueError('Duplicate local figure number')
    # Resolve paths and hashes before changing paths or numbering.
    return {'version': VERSION, 'question_id': question, 'sections': split,
            'references': refs, 'figures': figures, 'edits': edits, 'generated_captions':generated_captions}


def compose(inputs, output, title, cross_references=None, question_titles=None, abstract=None, keywords=None, symbol_table=None):
    """Inputs contain normalized chapters and verified source figure paths."""
    if len(inputs)>1 and (not abstract or not keywords):
        raise ValueError('Multi-question assembly requires one full-paper abstract and unified keywords')
    abstract=abstract or inputs[0]['sections']['摘要']
    keywords=keywords or inputs[0]['sections']['关键词']
    frontmatter('## 摘要\n\n'+abstract+'\n\n## 关键词\n\n'+keywords)
    symbol_report=symbols.build(inputs,symbol_table)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output/'figures').mkdir()
    chapters = {i['question_id']: i for i in inputs}
    question_titles = question_titles or {q:'问题'+str(n) for n,q in enumerate(chapters,1)}
    if set(question_titles)!=set(chapters) or any(not isinstance(v,str) or not v.strip() or re.search(r'[\r\n#]',v) for v in question_titles.values()):
        raise ValueError('Question titles must name each input question once')
    maps = {'figures': {}, 'tables': {}, 'equations': {}, 'citations': {}, 'labels': {}}
    refs = []
    catalog_figures = []
    source_map = []
    # Deterministic local identities; final equation/figure/table numbers follow
    # their actual order in the merged document, not each chapter's old order.
    for item in inputs:
        q = item['question_id']
        maps['figures'][q] = {}
        maps['tables'][q] = {}
        maps['equations'][q] = {}
        maps['citations'][q] = {}
        maps['labels'][q] = {}
        for key, value in item['references'].items():
            if value not in refs:
                refs.append(value)
            maps['citations'][q][key] = refs.index(value)+1
        for figure in item['figures']:
            # Retain backup candidates and their evidence; only formal figures enter prose.
            f = copy.deepcopy(figure)
            f['id'] = q+'-'+f['id']
            f['question_ids'] = [q]
            for fmt, asset in f['files'].items():
                src = inside(Path(item['figure_base']), asset['path'])
                if sha_file(src) != asset['sha256']:
                    raise ValueError('Changed figure asset')
                name = figure_asset_stem(q,figure['id'])+'.'+fmt
                # IDs supplied by catalogs must also be safe filename parts.
                if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
                    raise ValueError('Unsafe figure ID')
                target = output/'figures'/name
                with target.open('xb') as stream:
                    stream.write(src.read_bytes())
                asset['path'] = 'figures/'+name
            f['local_number'] = f.get('number')
            catalog_figures.append(f)
        source_map.append({'question_id': q, 'identity': item['identity'],
                           'normalized_sha256': item['normalized_sha256'], 'edits': item['edits'],
                           'generated_captions':item.get('generated_captions',[])})
    by_png = {f['files']['png']['path']:f for f in catalog_figures if f['formal']}
    cross_references = cross_references or []
    cross_usage = [0 for rule in cross_references]
    bodies = {}
    equation_counts = {q:0 for q in chapters}
    for item in inputs:
        q = item['question_id']
        local_paths = {f['files']['png']['path']:figure_asset_stem(q,f['id']) for f in item['figures'] if f['formal']}
        body = {}
        for name, original in item['sections'].items():
            if name=='符号说明':continue
            text = original
            # Explicit cross-question phrases are resolved before local refs.
            for rule_index,rule in enumerate(cross_references):
                if rule['source_question'] == q:
                    if rule['target_question'] not in chapters:
                        raise ValueError('Unknown cross-question target')
                    key = rule['kind']
                    token = f'@@ASM_{key}_{rule["target_question"]}_{rule["local_number"]}@@'
                    if key=='equations':token='式（'+token+'）'
                    cross_usage[rule_index] += text.count(rule['phrase'])
                    text = text.replace(rule['phrase'], token)
            if re.search(r'(?:第[一二三四五六七八九十0-9]+题|问题[一二三四五六七八九十0-9]+)(?:的)?\s*(?:图|表|式)\s*[（(]?\d+', text):
                raise ValueError('Undeclared cross-question reference')
            text = re.sub(r'图\s*(\d+)', lambda m:f'@@ASM_figures_{q}_{m[1]}@@', text)
            text = re.sub(r'表\s*(\d+)', lambda m:f'@@ASM_tables_{q}_{m[1]}@@', text)
            text = re.sub(r'式[（(](\d+)[）)]', lambda m:f'式（@@ASM_equations_{q}_{m[1]}@@）', text)
            def citation(m):
                if m[1] not in maps['citations'][q]:
                    raise ValueError('Unknown local citation: '+m[1])
                return '['+str(maps['citations'][q][m[1]])+']'
            text = re.sub(r'(?<!!)\[(\d+)\](?!\()', citation, text)
            def image(m):
                if m[2] not in local_paths:
                    raise ValueError('Image absent from formal catalog: '+m[2])
                return '!['+m[1]+'](figures/'+local_paths[m[2]]+'.png)'
            text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', image, text)
            for local_label in re.findall(r'\\label\{([^}]+)\}',text):
                maps['labels'][q][local_label]=q+'-'+local_label
            text = re.sub(r'\\label\{([^}]+)\}',lambda m:'\\label{'+q+'-'+m[1]+'}',text)
            text = re.sub(r'\\(eqref|ref)\{([^}]+)\}',lambda m:'\\'+m[1]+'{'+q+'-'+m[2]+'}',text)
            def equation(m):
                equation_counts[q] += 1
                math = m[1].strip()
                tags = re.findall(r'\\tag\{(\d+)\}', math)
                if len(tags)>1:
                    raise ValueError('Multiple equation tags in one display')
                local = tags[0] if tags else str(equation_counts[q])
                math = re.sub(r'\\tag\{\d+\}', '', math).strip()
                return '$$\n'+math+'\n\\tag{@@ASM_equations_'+q+'_'+local+'@@}\n$$'
            text = re.sub(r'\$\$\s*([\s\S]*?)\s*\$\$', equation, text)
            # Preserve the chapter hierarchy under its new per-question heading.
            text = re.sub(r'^(#{3,5}) ', r'\1# ', text, flags=re.M)
            body[name] = text
        bodies[q] = body
    if any(count==0 for count in cross_usage):
        raise ValueError('Declared cross-reference phrase not found')
    text = '# '+title+'\n\n## 摘要\n\n'+abstract.strip()+'\n\n## 关键词\n\n'+keywords.strip()+'\n\n'
    names = [n for n in policy()['required_sections'] if n not in ['参考文献','摘要','关键词']]
    extras = sorted({s for b in bodies.values() for s in b if s not in names and s not in ['摘要','关键词']})
    for name in names+extras:
        text += '## '+name+'\n\n'
        if name=='符号说明':
            text+=symbols.markdown(symbol_report,question_titles)
            continue
        for q in chapters:
            if name in bodies[q]:
                text += '### '+question_titles[q]+'\n\n'+bodies[q][name]+'\n\n'
    text += '## 参考文献\n\n'+'\n\n'.join('['+str(i)+'] '+v for i,v in enumerate(refs,1))+'\n'
    # Identify definitions, then resolve all references (including forward refs).
    formal_order = re.findall(r'!\[[^\]]*\]\((figures/[^)]+)\)', text)
    if len(formal_order) != len(set(formal_order)) or set(formal_order) != set(by_png):
        raise ValueError('Each formal figure must appear exactly once')
    for n,path in enumerate(formal_order,1):
        f = by_png[path]
        q = f['question_ids'][0]
        maps['figures'][q][str(f['local_number'])] = n
        f['number'] = n
    for n,(q,local) in enumerate(re.findall(r'^@@ASM_tables_([^@]+?)_(\d+)@@\s+.+$', text, re.M),1):
        if local in maps['tables'][q]:
            raise ValueError('Duplicate local table definition')
        maps['tables'][q][local] = n
    first=symbol_report['source_tables'][0]
    global_number=maps['tables'][first['question_id']][first['local_table_number']]
    for source_table in symbol_report['source_tables'][1:]:
        maps['tables'][source_table['question_id']][source_table['local_table_number']]=global_number
    symbol_report['global_table_number']=global_number
    for n,(q,local) in enumerate(re.findall(r'\\tag\{@@ASM_equations_([^@]+?)_(\d+)@@\}',text),1):
        if local in maps['equations'][q]:
            raise ValueError('Duplicate local equation identity')
        maps['equations'][q][local] = n
    def resolve(m):
        kind,q,local = m.groups()
        if q not in maps[kind] or local not in maps[kind][q]:
            raise ValueError('Unresolved reference: '+m[0])
        prefix = {'figures':'图','tables':'表','equations':''}[kind]
        return prefix+str(maps[kind][q][local])
    text = re.sub(r'@@ASM_(figures|tables|equations)_([^@]+?)_(\d+)@@',resolve,text)
    if '@@ASM_' in text:
        raise ValueError('Unresolved assembly token')
    labels = re.findall(r'\\label\{([^}]+)\}',text)
    if len(labels)!=len(set(labels)) or not set(re.findall(r'\\(?:eqref|ref)\{([^}]+)\}',text))<=set(labels):
        raise ValueError('Duplicate or unresolved LaTeX label')
    # Keep images separate from caption paragraphs for the existing exporter.
    text = re.sub(r'(!\[[^]]+\]\([^)]+\))\n(图\d+)',r'\1\n\n\2',text)
    (output/MD_NAME).write_text(text,encoding='utf-8')
    catalog = {'question_ids':list(chapters), 'figures': sorted(catalog_figures,key=lambda f:(not f['formal'],f.get('number') or 0,f['id'])),
               'evidence': {'chapters':source_map, 'composer_version':VERSION}}
    (output/'figure-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    report = validate_draft(output/MD_NAME,output/'figure-catalog.json')
    if report['status'] != 'passed':
        raise ValueError('Composed manuscript checks failed: '+str(report['findings']))
    return {'maps':maps,'chapters':source_map,'mechanical':report,'symbol_table':symbol_report,
            'cross_references':[dict(rule,occurrences=count) for rule,count in zip(cross_references,cross_usage)],
            'new_scientific_results':False, 'user_review':'pending', 'W2':'NOT_RUN'}
