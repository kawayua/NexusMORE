"""NexusMORE read-only template inspection and byte-preserving Office workspaces.

Engineering probes only. No automatic repair, revision merge or edited publishing.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
from .latex_tools import contained, write_new
from .pdf_checks import sha

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
NS={'w':W,'a':A}


def _xml(raw):
    from lxml import etree
    node=etree.fromstring(raw,parser=etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
    if node.getroottree().docinfo.doctype:raise ValueError('Office XML DTD is not allowed')
    return node


def _name(name):
    path=PurePosixPath(name)
    if (not name or name.startswith('/') or ':' in name or '\\' in name or any(part in {'.','..'} for part in path.parts)
        or any(part.endswith((' ','.')) or re.match(r'^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',part,re.I) for part in path.parts)):
        raise ValueError('Unsafe Office member path')
    if path.as_posix()!=name.rstrip('/'):raise ValueError('Noncanonical Office member path')
    return path.as_posix()


def parts(source):
    """Validate archive limits and XML without changing any member byte."""
    source=Path(source)
    if source.suffix.lower() not in {'.docx','.xlsx'}:raise ValueError('Only DOCX/XLSX engineering workspaces supported')
    result={};seen=set();total=0
    with zipfile.ZipFile(source) as archive:
        members=archive.infolist()
        if len(members)>2000:raise ValueError('Office archive has too many members')
        for item in members:
            name=_name(item.filename);key=name.casefold()
            if key in seen:raise ValueError('Duplicate/case-conflicting Office member')
            seen.add(key)
            mode=item.external_attr>>16
            if stat.S_ISLNK(mode) or item.flag_bits&1:raise ValueError('Linked/encrypted Office member')
            total+=item.file_size
            if total>80_000_000 or item.file_size>20_000_000 or item.file_size>max(1,item.compress_size)*1000:
                raise ValueError('Office archive exceeds resource limit')
            if item.is_dir():continue
            if name=='workspace.json':raise ValueError('Reserved workspace member')
            raw=archive.read(item)
            if len(raw)!=item.file_size:raise ValueError('Office member size mismatch')
            if name.endswith(('.xml','.rels')):_xml(raw)
            result[name]=raw
    required={'[Content_Types].xml','_rels/.rels','word/document.xml' if source.suffix.lower()=='.docx' else 'xl/workbook.xml'}
    if not required<=set(result):raise ValueError('Incomplete Office package')
    return result


def _identities(values):return {name:hashlib.sha256(raw).hexdigest() for name,raw in values.items()}


def unpack(root, source, output):
    source=contained(root,source);output=contained(root,output);before=sha(source);data=parts(source)
    output.mkdir(parents=True,exist_ok=False)
    for name,raw in data.items():
        p=contained(output,name);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(raw)
    if sha(source)!=before:raise ValueError('Office input changed while reading')
    manifest={'schema_version':'1.0.0','purpose':'engineering_probe','source':str(source),'source_sha256':before,
              'suffix':source.suffix.lower(),'members':_identities(data),'original_unchanged':True,'automatic_edits':False,
              'formal_approval':False,'visual_review':'PENDING','W2':'NOT_RUN'}
    write_new(output/'workspace.json',manifest)
    return {'status':'passed','members':len(data),'workspace':str(output),'formal_approval':False}


def pack(root, workspace, output):
    """Round-trip original members only; edited workspaces require another workflow."""
    workspace=contained(root,workspace);output=contained(root,output)
    if output.is_relative_to(workspace) or workspace.is_relative_to(output):raise ValueError('Output must be separate from workspace')
    value=json.loads((workspace/'workspace.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!='1.0.0' or value.get('purpose')!='engineering_probe' or value.get('suffix') not in {'.docx','.xlsx'}:
        raise ValueError('Unknown Office workspace protocol')
    source=contained(root,value['source'])
    if sha(source)!=value['source_sha256']:raise ValueError('Original Office source changed')
    original=parts(source)
    if _identities(original)!=value['members']:raise ValueError('Original member identities differ')
    actual={}
    for p in workspace.rglob('*'):
        if p.is_symlink() or p.is_junction():raise ValueError('Linked workspace member')
        if p.is_file() and p!=workspace/'workspace.json':
            name=p.relative_to(workspace).as_posix();_name(name);actual[name]=sha(p)
    if actual!=value['members']:raise ValueError('Workspace edited; byte-preserving pack refuses changed members')
    output.mkdir(parents=True,exist_ok=False);target=output/('roundtrip'+value['suffix'])
    try:
        with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(actual):archive.writestr(name,(workspace/name).read_bytes())
        if _identities(parts(target))!=value['members'] or sha(source)!=value['source_sha256']:
            raise ValueError('Round-trip identity differs')
        check={'status':'passed','purpose':'engineering_probe','source_sha256':value['source_sha256'],
               'output_sha256':sha(target),'member_bytes_preserved':True,'archive_bytes_equal_claimed':False,
               'formal_approval':False,'schema_validation':'NOT_RUN','visual_review':'PENDING','W2':'NOT_RUN'}
    except Exception as exc:
        write_new(output/'pack-check.json',{'status':'failed','error_type':type(exc).__name__,'formal_approval':False});raise
    write_new(output/'pack-check.json',check)
    return check


def profile(root, source, output):
    """Report raw and inherited style properties; never infer official roles/layout."""
    source=contained(root,source);output=contained(root,output)
    if source.suffix.lower()!='.docx':raise ValueError('DOCX template required')
    before=sha(source);data=parts(source);document=_xml(data['word/document.xml'])
    styles=_xml(data.get('word/styles.xml',b'<styles/>'));by_id={}
    def properties(node,depth=0):
        if depth>40:raise ValueError('Office property nesting exceeds limit')
        return [] if node is None else [{'tag':child.tag,'attributes':dict(child.attrib),'children':properties(child,depth+1)} for child in node]
    for node in styles.findall('w:style',NS):
        key=node.get('{'+W+'}styleId')
        if not key or key in by_id:raise ValueError('Missing/duplicate Word style')
        parent=node.find('w:basedOn',NS)
        by_id[key]={'type':node.get('{'+W+'}type'),'default':node.get('{'+W+'}default') in {'1','true'},'based_on':parent.get('{'+W+'}val') if parent is not None else None,
                    'pPr':properties(node.find('w:pPr',NS)),'rPr':properties(node.find('w:rPr',NS))}
    def chain(key,stack=()):
        if key in stack:raise ValueError('Cyclic Word style inheritance')
        if len(stack)>64:raise ValueError('Word style inheritance exceeds limit')
        if key not in by_id:return [{'unresolved_style':key}]
        parent=by_id[key]['based_on']
        return (chain(parent,stack+(key,)) if parent else [])+[{'style_id':key,**by_id[key]}]
    inherited={key:chain(key) for key in by_id}
    defaults=[key for key,value in by_id.items() if value['type']=='paragraph' and value['default']]
    if len(defaults)>1:raise ValueError('Multiple default Word paragraph styles')
    paragraphs=[]
    for paragraph in document.findall('.//w:p',NS):
        ppr=paragraph.find('w:pPr',NS);style=paragraph.find('w:pPr/w:pStyle',NS)
        style_id=style.get('{'+W+'}val') if style is not None else (defaults[0] if defaults else None)
        paragraphs.append({'style':style_id,'style_explicit':style is not None,'style_chain':chain(style_id) if style_id else [],
                           'pPr':properties(ppr),'runs':[{'rPr':properties(run.find('w:rPr',NS))} for run in paragraph.findall('w:r',NS)]})
    themes={name:[{'tag':node.tag,'attributes':dict(node.attrib)} for node in _xml(raw).iter() if node.tag in {'{'+A+'}latin','{'+A+'}ea','{'+A+'}font'}]
            for name,raw in data.items() if name.startswith('word/theme/') and name.endswith('.xml')}
    result={'status':'passed','source_sha256':before,'purpose':'read_only_observation','official_compliance':False,
            'defaults':properties(styles.find('w:docDefaults',NS)),'styles':inherited,'paragraphs':paragraphs,
            'sections':[properties(node) for node in document.findall('.//w:sectPr',NS)],
            'tables':[properties(node.find('w:tblPr',NS)) for node in document.findall('.//w:tbl',NS)],'themes':themes,
            'limitations':['Style layers retained in precedence order; no complete Word layout or theme substitution engine.',
                           'Table conditional formatting, headers/footers and numbering are not fully resolved; no semantic role inference.'],
            'formal_approval':False,'visual_review':'NOT_RUN','W2':'NOT_RUN'}
    if sha(source)!=before:raise ValueError('Template changed during inspection')
    output.mkdir(parents=True,exist_ok=False);write_new(output/'template-profile.json',result)
    return result


def doctor(output):
    from importlib.metadata import version,PackageNotFoundError
    output=Path(output);output.mkdir(parents=True,exist_ok=False);dependencies=[]
    for module,package in [('docx','python-docx'),('lxml','lxml'),('defusedxml','defusedxml'),('openpyxl','openpyxl')]:
        available=importlib.util.find_spec(module) is not None
        try:installed=version(package) if available else None
        except PackageNotFoundError:installed=None
        dependencies.append({'module':module,'package':package,'version':installed,'available':available and installed is not None})
    result={'status':'passed' if all(d['available'] for d in dependencies) else 'blocked','dependencies':dependencies,
            'scope':'Office workbench plus registered document checks prerequisites; no native renderer/export compatibility assertion',
            'native_render_verified':False,'downloaded':False}
    write_new(output/'doctor.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    for action in ['unpack','pack','profile']:
        s=sub.add_parser(action);s.add_argument('--root',required=True);s.add_argument('--output',required=True)
        s.add_argument('--workspace' if action=='pack' else '--source',required=True)
    s=sub.add_parser('doctor');s.add_argument('--output',required=True)
    args=vars(p.parse_args());action=args.pop('action')
    result={'unpack':unpack,'pack':pack,'profile':profile,'doctor':doctor}[action](**args)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
