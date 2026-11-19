from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
from modelcrew.pdf_checks import _fonts


def test_cff_font_mislabeled_as_truetype_is_disclosed():
    stream=DecodedStreamObject();stream.set_data(b'OTTOtest')
    descriptor=DictionaryObject({NameObject('/FontFile2'):stream})
    descendant=DictionaryObject({NameObject('/FontDescriptor'):descriptor})
    from pypdf.generic import ArrayObject
    font=DictionaryObject({NameObject('/Subtype'):NameObject('/Type0'),NameObject('/DescendantFonts'):ArrayObject([descendant])})
    resource=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    item=_fonts(resource)[0]
    assert item['embedded'] and item['program_type_mismatches']
    stream.set_data(b'\x00\x01\x00\x00test')
    assert not _fonts(resource)[0].get('program_type_mismatches')

def test_failed_pdf_report_names_the_file_page_and_finding(tmp_path):
    from modelcrew.pdf_checks import sha,verify_pdf_report
    import pytest
    source=tmp_path/'candidate.pdf';source.write_bytes(b'unchanged synthetic PDF')
    report={'source_sha256':sha(source),'status':'failed','pages':[{'page':1,'findings':['type3_font']}]}
    with pytest.raises(ValueError,match=r'PDF check failed: candidate\.pdf; page 1: type3_font'):
        verify_pdf_report(source,tmp_path,report)
    report['source_sha256']='0'*64
    with pytest.raises(ValueError,match='PDF source changed: candidate.pdf'):
        verify_pdf_report(source,tmp_path,report)
