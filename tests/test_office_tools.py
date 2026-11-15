"""Real synthetic Office inputs; no approved paper or upstream extension execution."""
import hashlib
import json
import zipfile
from pathlib import Path
import pytest
from modelcrew import office_tools as tools


def document(tmp_path):
    from docx import Document
    doc=Document();doc.add_paragraph('Synthetic workspace probe; not a paper.')
    doc.add_paragraph('Styled text',style='Heading 1')
    path=tmp_path/'input.docx';doc.save(path);return path


def test_docx_profile_preserves_input_and_exposes_inheritance_and_defaults(tmp_path):
    source=document(tmp_path);before=source.read_bytes()
    result=tools.profile(tmp_path,'input.docx','profile')
    assert result['status']=='passed' and result['sections'] and result['defaults']
    assert result['styles']['Heading1'][-1]['style_id']=='Heading1'
    assert result['paragraphs'][0]['style']=='Normal' and not result['paragraphs'][0]['style_explicit']
    assert result['paragraphs'][0]['style_chain'][-1]['default']
    assert not result['official_compliance'] and result['visual_review']=='NOT_RUN'
    assert source.read_bytes()==before
    with pytest.raises(FileExistsError):tools.profile(tmp_path,'input.docx','profile')


def test_docx_roundtrip_preserves_every_member_and_revision_xml(tmp_path):
    source=document(tmp_path);before=source.read_bytes()
    tools.unpack(tmp_path,'input.docx','workspace');result=tools.pack(tmp_path,'workspace','output')
    assert result['member_bytes_preserved'] and result['schema_validation']=='NOT_RUN'
    assert tools.parts(source)==tools.parts(tmp_path/'output/roundtrip.docx')
    assert source.read_bytes()==before
    with pytest.raises(FileExistsError):tools.pack(tmp_path,'workspace','output')


def test_xlsx_roundtrip_preserves_formula_bytes_without_recalculation(tmp_path):
    from openpyxl import Workbook,load_workbook
    book=Workbook();book.active['A1']='=SUM(1,2)';book.save(tmp_path/'input.xlsx');book.close()
    tools.unpack(tmp_path,'input.xlsx','workspace');tools.pack(tmp_path,'workspace','output')
    assert tools.parts(tmp_path/'input.xlsx')==tools.parts(tmp_path/'output/roundtrip.xlsx')


def test_changed_workspace_and_changed_original_refuse_pack(tmp_path):
    source=document(tmp_path);tools.unpack(tmp_path,'input.docx','workspace')
    (tmp_path/'workspace/word/document.xml').write_bytes(b'changed')
    with pytest.raises(ValueError,match='edited'):tools.pack(tmp_path,'workspace','output')
    assert not (tmp_path/'output').exists()
    source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='Original'):tools.pack(tmp_path,'workspace','other')


@pytest.mark.parametrize('name',['../escape.xml','word/../../escape.xml','word\\bad.xml','word/CON.xml','word/part.xml:stream','/abs.xml'])
def test_unsafe_zip_member_rejected_before_output_creation(tmp_path,name):
    p=tmp_path/'unsafe.docx'
    with zipfile.ZipFile(p,'w') as archive:
        member=zipfile.ZipInfo('entry');member.filename=name;archive.writestr(member,b'<x/>')
    with pytest.raises(ValueError):tools.unpack(tmp_path,'unsafe.docx','workspace')
    assert not (tmp_path/'workspace').exists()


def test_archive_case_collision_rejected(tmp_path):
    p=tmp_path/'unsafe.docx'
    with zipfile.ZipFile(p,'w') as archive:
        archive.writestr('word/a.xml',b'<x/>');archive.writestr('word/A.xml',b'<x/>')
    with pytest.raises(ValueError,match='case'):tools.parts(p)


def test_edited_manifest_cannot_authorize_different_original_members(tmp_path):
    document(tmp_path);tools.unpack(tmp_path,'input.docx','workspace')
    path=tmp_path/'workspace/workspace.json';value=json.loads(path.read_text(encoding='utf-8'));value['members']['word/document.xml']='0'*64;path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError,match='identities'):tools.pack(tmp_path,'workspace','output')


def test_registry_and_frozen_math_rules_follow_local_contract(tmp_path):
    from modelcrew.capabilities import load_capabilities
    from modelcrew.hand_guidance import freeze_guidance,frozen_context
    registry=load_capabilities();assert registry['paper_discovery']['require_two_sources'] is False
    assert all(x['entry_available'] for x in registry['capabilities'])
    frozen=freeze_guidance(tmp_path);context=frozen_context(tmp_path,frozen,'M1')
    texts={x['path']:x['text'] for x in context['documents']}
    assert context['guidance_version']=='1.3.0' and context['read_only']
    assert 'statistical-validation.md' in texts and 'BH' in texts['statistical-validation.md']
    assert 'proof-review.md' in texts and 'open_gaps' in texts['proof-review.md']


def test_xml_dtd_is_refused_without_entity_expansion():
    with pytest.raises(ValueError,match='DTD'):
        tools._xml(b'<!DOCTYPE x [<!ENTITY value "content">]><x>&value;</x>')

def test_style_inheritance_cycle_is_rejected(tmp_path):
    source=document(tmp_path);data=tools.parts(source)
    data['word/styles.xml']=b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:styleId="a"><w:basedOn w:val="b"/></w:style><w:style w:styleId="b"><w:basedOn w:val="a"/></w:style></w:styles>'
    with zipfile.ZipFile(source,'w') as archive:
        for name,raw in data.items():archive.writestr(name,raw)
    with pytest.raises(ValueError,match='Cyclic'):tools.profile(tmp_path,'input.docx','profile')
    assert not (tmp_path/'profile').exists()
