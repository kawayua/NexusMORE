"""One global symbol table with explicit source coverage; no inferred semantics."""
import re


def cells(line):
    return [v.strip() for v in re.split(r'(?<!\\)\|',line.strip())[1:-1]]


def key(symbol):
    return re.sub(r'\s+', '',symbol.strip().strip('$'))


def atoms(symbol):
    text=symbol.strip().strip('$');parts=[];start=0;depth=0
    for i,c in enumerate(text):
        if c in '({[':depth+=1
        elif c in ')}]':depth-=1
        elif c==',' and depth==0:parts.append(text[start:i]);start=i+1
    parts.append(text[start:])
    return [key(p.split('=',1)[0]) for p in parts]


def source_table(question,text):
    lines=text.strip().splitlines()
    starts=[i for i,l in enumerate(lines) if l.strip().startswith('|') and i+1<len(lines) and re.fullmatch(r'\|[ :|\-]+\|',lines[i+1].strip())]
    if len(starts)!=1:raise ValueError('Each source symbol section must contain one table: '+question)
    start=starts[0];headers=cells(lines[start])
    if headers!=['符号','含义','单位']:raise ValueError('Source symbol table requires 符号/含义/单位 columns')
    end=start+2;rows=[]
    while end<len(lines) and lines[end].strip().startswith('|'):
        values=cells(lines[end])
        if len(values)!=3 or not all(values):raise ValueError('Invalid symbol row: '+question)
        rows.append(dict(zip(['symbol','meaning','unit'],values)));end+=1
    rest='\n'.join(lines[:start]+lines[end:]).strip()
    captions=re.findall(r'^表(\d+)\s+.+$',rest,re.M)
    if len(captions)!=1 or re.sub(r'^表\d+\s+.+$','',rest,flags=re.M).strip():
        raise ValueError('Source symbol notes require explicit consolidation before assembly')
    keys=[key(r['symbol']) for r in rows]
    if not rows or len(keys)!=len(set(keys)):raise ValueError('Empty or duplicate source symbol rows')
    return {'question_id':question,'local_table_number':captions[0],'rows':rows}


def build(inputs,provided=None):
    tables=[source_table(i['question_id'],i['sections']['符号说明']) for i in inputs]
    sources={(t['question_id'],key(r['symbol'])):r for t in tables for r in t['rows']}
    if provided is None:
        # Only byte-identical definitions may merge without an explicit map.
        rows=[];definitions={};used_atoms=set()
        for (q,k),r in sources.items():
            identity=(r['symbol'],r['meaning'],r['unit'])
            ref={'question_id':q,'symbol':r['symbol']}
            if identity in definitions:rows[definitions[identity]]['sources'].append(ref);continue
            if set(atoms(r['symbol'])) & used_atoms:
                raise ValueError('Symbol conflict needs an explicit global symbol_table mapping: '+r['symbol'])
            used_atoms.update(atoms(r['symbol']));definitions[identity]=len(rows)
            rows.append({**r,'sources':[ref],'reason':'Identical source definition or unique source symbol; no semantic merge inferred'})
    else:rows=provided
    covered=set();seen=set();validated=[]
    for row in rows:
        for name in ['symbol','meaning','unit','reason']:
            value=row.get(name,'')
            if not isinstance(value,str) or not value.strip() or re.search(r'[\r\n]|(?<!\\)\|',value):
                raise ValueError('Invalid global symbol field: '+name)
        row_atoms=set(atoms(row['symbol']))
        if seen & row_atoms:raise ValueError('Duplicate or overlapping global symbol definitions')
        seen.update(row_atoms)
        refs=row.get('sources',[])
        if not refs:raise ValueError('Every global symbol needs source references')
        row_covered=set()
        for ref in refs:
            identity=(ref['question_id'],key(ref['symbol']))
            if identity not in sources:raise ValueError('Unknown source symbol reference')
            if identity in row_covered:raise ValueError('Duplicate source reference in global symbol row')
            row_covered.add(identity)
            original=sources[identity];original_atoms=atoms(original['symbol'])
            if not row_atoms<=set(original_atoms):raise ValueError('Renamed/new symbols require explicit upstream patches first')
            units=[u.strip() for u in original['unit'].split(',')]
            relevant=[units[original_atoms.index(a)] if len(units)==len(original_atoms) else original['unit'] for a in row_atoms]
            if any(key(u)!=key(row['unit']) for u in relevant):raise ValueError('Symbol unit conflict; resolve in source patches first')
            covered.update((identity,a) for a in row_atoms)
        source_questions=list(dict.fromkeys(ref['question_id'] for ref in refs))
        scope=row.get('applicable_questions') or source_questions
        if not set(source_questions)<=set(scope)<=set(i['question_id'] for i in inputs) or len(scope)!=len(set(scope)):
            raise ValueError('Invalid applicable question scope')
        validated.append({**row,'question_ids':scope})
    expected={(identity,a) for identity,r in sources.items() for a in atoms(r['symbol'])}
    if covered!=expected:raise ValueError('Global symbol table does not cover every source symbol component')
    if not validated:raise ValueError('Global symbol table must not be empty')
    return {'rows':validated,'source_tables':tables,'source_rows':len(sources),'source_components':len(expected),
            'coverage':'complete','mode':'explicit_mapping' if provided is not None else 'identical_definition_only',
            'semantic_review':'pending; explicit author mappings are not independent scientific approval'}


def markdown(report,question_titles):
    first=report['source_tables'][0]
    token='@@ASM_tables_'+first['question_id']+'_'+first['local_table_number']+'@@'
    lines=[token+' 全局符号说明','', '| 符号 | 含义 | 单位 | 适用范围 |','|---|---|---|---|']
    for row in report['rows']:
        scope='、'.join(question_titles[q] for q in row['question_ids'])
        lines.append('| '+ ' | '.join([row['symbol'],row['meaning'],row['unit'],scope])+' |')
    return '\n'.join(lines)+'\n\n'


def validate_global_table(text):
    """Structural export guard; semantic consistency still needs review."""
    parts=re.split(r'^##\s+(.+?)\s*$',text,flags=re.M)
    matches=[parts[i+1] for i in range(1,len(parts),2) if re.sub(r'^[一二三四五六七八九十0-9]+[、.． ]+','',parts[i])=='符号说明']
    if len(matches)!=1:raise ValueError('Exactly one global symbol section required')
    body=matches[0]
    if re.search(r'^#{1,6}\s',body,re.M):raise ValueError('Question symbol subheadings are forbidden')
    lines=body.strip().splitlines()
    starts=[i for i,l in enumerate(lines) if l.strip().startswith('|') and i+1<len(lines) and re.fullmatch(r'\|[ :|\-]+\|',lines[i+1].strip())]
    if len(starts)!=1:raise ValueError('Exactly one global logical symbol table required')
    start=starts[0]
    if cells(lines[start])!=['符号','含义','单位','适用范围']:raise ValueError('Global symbol columns must include applicable scope')
    seen=set();count=0
    for line in lines[start+2:]:
        if not line.strip().startswith('|'):break
        row=cells(line)
        if len(row)!=4 or not all(row):raise ValueError('Invalid global symbol table row')
        current=set(atoms(row[0]))
        if seen & current:raise ValueError('Duplicate global symbol definitions')
        seen.update(current);count+=1
    if not count:raise ValueError('Global symbol table must not be empty')
    return {'status':'passed','logical_tables':1,'rows':count,'question_subtables':0,'scope':'Structure only; semantic review remains required'}
