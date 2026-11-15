"""Own data/export/PDF checks use synthetic engineering fixtures, no paper approval."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from modelcrew.figure_data import read_data, profile_numeric
from modelcrew.pdf_checks import inspect_pdf, verify_pdf_report, sha
from modelcrew.figure_tools import export_figure, audit_catalog


def test_explicit_headers_and_pairwise_n(tmp_path):
    path = tmp_path/'data.csv'
    path.write_text('1,10\n2,\n,30\n4,40\n\n', encoding='utf-8')
    data = read_data(path, header=False, expected_rows=5)
    assert data['rows'][0] == ['1','10'] and data['rows'][-1] == []
    result = profile_numeric(data, [0,1], units={0:'s',1:'m'})
    assert result['columns'][0]['missing_n'] == 2
    pair = next(p for p in result['pairwise'] if p['columns']==[0,1])
    assert pair['retained_n'] == 2 and pair['missing_pair_rows'] == 3
    assert pair['pearson_r'] == pytest.approx(1)
    assert len(data['rows']) == 5 and data['transformations'] == []
    assert read_data(path, header=True)['row_count'] == 4
    with pytest.raises(ValueError, match='explicitly'):
        read_data(path, header=None)
    with pytest.raises(ValueError, match='row count'):
        read_data(path, header=False, expected_rows=4)
    with pytest.raises(ValueError, match='max_cells'):
        read_data(path, header=False, max_cells=2)


def test_xlsx_explicit_sheet_and_unresolved_formula(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = 'observations'
    book.active.append(['x','y'])
    book.active.append([1,2])
    book.active.append([3,'=A3*2'])
    book.create_sheet('other').append([9])
    path = tmp_path/'data.xlsx'
    book.save(path)
    with pytest.raises(ValueError, match='explicit worksheet'):
        read_data(path, header=True)
    data = read_data(path, header=True, sheet='observations', expected_rows=2)
    assert data['rows'][0]==[1,2] and data['rows'][-1][1]=='=A3*2'
    with pytest.raises(ValueError, match='unresolved formula'):
        profile_numeric(data, [1], units={1:'m'})


@pytest.mark.parametrize('value', ['nan', 'inf', True, '=2+2'])
def test_nonfinite_boolean_and_formula_rejected(value):
    with pytest.raises(ValueError):
        profile_numeric({'rows': [[value]], 'column_count': 1, 'row_count': 1,
                         'source_sha256': 'x'}, [0], units={0:'dimensionless'})


def pdf_fixture(path, *, small_last=False):
    import fitz
    with fitz.open() as document:
        for index in range(3):
            page = document.new_page(width=300,height=200)
            page.insert_text((30,70), 'Engineering fixture page '+str(index+1),
                             fontsize=3 if small_last and index==2 else 12)
        document.save(path)


def test_pdf_all_pages_coverage_and_last_preview_tampering(tmp_path):
    source = tmp_path/'three-pages.pdf'
    pdf_fixture(source)
    report = inspect_pdf(source, tmp_path/'previews')
    assert report['page_count'] == 3
    assert [p['page'] for p in report['pages']] == [1,2,3]
    assert report['visual_review']=='PENDING'
    assert verify_pdf_report(source,tmp_path/'previews',report)
    omitted = copy.deepcopy(report)
    omitted['pages'].pop()
    with pytest.raises(ValueError, match='coverage'):
        verify_pdf_report(source,tmp_path/'previews',omitted)
    (tmp_path/'previews'/report['pages'][-1]['preview']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='preview changed'):
        verify_pdf_report(source,tmp_path/'previews',report)
    with pytest.raises(FileExistsError):
        inspect_pdf(source,tmp_path/'previews')


def test_last_page_failure_and_limits_do_not_skip(tmp_path):
    source = tmp_path/'three-pages.pdf'
    pdf_fixture(source,small_last=True)
    report = inspect_pdf(source,tmp_path/'bad')
    assert report['status']=='failed'
    assert 'font_below_minimum' in report['pages'][-1]['findings']
    with pytest.raises(ValueError,match='check failed'):
        verify_pdf_report(source,tmp_path/'bad',report)
    with pytest.raises(ValueError,match='page count'):
        inspect_pdf(source,tmp_path/'limited',max_pages=2)
    assert not (tmp_path/'limited').exists()
    with pytest.raises(ValueError,match='pixel limit'):
        inspect_pdf(source,tmp_path/'pixels',max_page_pixels=1)


@pytest.fixture
def figure_inputs(tmp_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source = tmp_path/'verified.csv'
    source.write_text('time,value\n0,1\n1,3\n2,2\n', encoding='utf-8')
    code = tmp_path/'plot.py'
    code.write_text('# synthetic export fixture; values from verified.csv\n', encoding='utf-8')
    data = read_data(source, header=True, expected_rows=3)
    fig, ax = plt.subplots(figsize=(4,3),layout='constrained')
    ax.plot([float(r[0]) for r in data['rows']], [float(r[1]) for r in data['rows']])
    ax.set(xlabel='Time (s)', ylabel='Value (m)')
    kwargs = {'figure_id':'fixture-result', 'binding':{'task_id':'fixture','contract_version':1,
              'contract_sha256':'a'*64,'execution_id':'fixture-run','result_revision':1},
              'inputs':[{'path':str(source),'sha256':sha(source)}],
              'code':{'path':str(code),'sha256':sha(code)}, 'parameters':{'fixture':True}}
    yield fig, kwargs
    plt.close(fig)


def test_export_all_formats_physical_size_state_and_no_overwrite(tmp_path,figure_inputs):
    import matplotlib as mpl
    from PIL import Image
    fig, kwargs = figure_inputs
    before = dict(mpl.rcParams)
    result = export_figure(fig,tmp_path/'export',**kwargs)
    assert dict(mpl.rcParams)==before
    assert set(result['files'])=={'png','pdf','svg'}
    with Image.open(tmp_path/'export/fixture-result.png') as image:
        assert image.size==(1200,900) and min(image.info['dpi'])>=299
    assert (tmp_path/'export/pdf-preview/page-0001.png').is_file()
    assert 'Type0' in (tmp_path/'export/pdf-preview/pdf-check.json').read_text()
    assert result['visual_review']=='PENDING'
    original = sha(tmp_path/'export/fixture-result.png')
    with pytest.raises(FileExistsError):
        export_figure(fig,tmp_path/'export',**kwargs)
    assert sha(tmp_path/'export/fixture-result.png')==original
    # Metadata and SVG IDs are stable over actual repeat exports.
    repeated=export_figure(fig,tmp_path/'repeat',**kwargs)
    assert {k:v['sha256'] for k,v in result['files'].items()}=={k:v['sha256'] for k,v in repeated['files'].items()}


def test_export_input_tamper_and_glyph_failure_no_success_marker(tmp_path,figure_inputs):
    fig, kwargs = figure_inputs
    Path(kwargs['inputs'][0]['path']).write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError,match='data or code changed'):
        export_figure(fig,tmp_path/'changed',**kwargs)
    assert not (tmp_path/'changed').exists()
    kwargs['inputs'][0]['sha256']=sha(kwargs['inputs'][0]['path'])
    fig.axes[0].set_title('Too small',fontsize=3)
    with pytest.raises(ValueError,match='below 5'):
        export_figure(fig,tmp_path/'bad',**kwargs)
    assert not (tmp_path/'bad/figure-export.json').exists()
    assert (tmp_path/'bad/figure-export-failed.json').is_file()


def test_catalog_checks_unselected_candidates_and_nested_pdf_pages(tmp_path,figure_inputs):
    fig, kwargs = figure_inputs
    export=export_figure(fig,tmp_path/'export',**kwargs)
    catalog={'figures':[{'id':'fixture-result','formal':False,'files':export['files']}]}
    path=tmp_path/'export/figure-catalog.json'
    path.write_text(json.dumps(catalog),encoding='utf-8')
    report=audit_catalog(path,tmp_path/'catalog-qa')
    assert report['figures'][0]['page_count']==1
    pdf=tmp_path/'export/fixture-result.pdf'
    pdf_fixture(tmp_path/'replacement.pdf',small_last=True)
    pdf.write_bytes((tmp_path/'replacement.pdf').read_bytes())
    catalog['figures'][0]['files']['pdf']['sha256']=sha(pdf)
    path.write_text(json.dumps(catalog),encoding='utf-8')
    with pytest.raises(ValueError,match='check failed'):
        audit_catalog(path,tmp_path/'broken-catalog-qa')
    assert not (tmp_path/'broken-catalog-qa/catalog-check.json').exists()

def test_pdf_tree_checks_every_file_and_preserves_failure(tmp_path):
    from modelcrew.pdf_checks import audit_pdf_tree
    source=tmp_path/'bundle'
    (source/'nested').mkdir(parents=True)
    pdf_fixture(source/'good.PDF')
    pdf_fixture(source/'nested/bad.pdf',small_last=True)
    report=audit_pdf_tree(source,tmp_path/'tree-check')
    assert report['status']=='failed'
    assert len(report['documents'])==2
    assert {item['status'] for item in report['documents']}=={'passed','failed'}
    assert (tmp_path/'tree-check/pdf-0002/page-0003.png').is_file()
    with pytest.raises(ValueError,match='outside'):
        audit_pdf_tree(source,source/'unsafe-check')


def test_catalog_cached_report_rechecks_last_preview(tmp_path,figure_inputs):
    from modelcrew.figure_tools import verify_catalog_report
    fig,kwargs=figure_inputs
    export=export_figure(fig,tmp_path/'export',**kwargs)
    catalog=tmp_path/'export/figure-catalog.json'
    catalog.write_text(json.dumps({'figures':[{'id':'f1','files':export['files']}]}),encoding='utf-8')
    report=audit_catalog(catalog,tmp_path/'checked')
    assert verify_catalog_report(catalog,tmp_path/'checked',report)
    (tmp_path/'checked/figure-0001/page-0001.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='preview changed'):
        verify_catalog_report(catalog,tmp_path/'checked',report)


def test_recursive_form_font_is_not_skipped_on_last_page(tmp_path):
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject,ArrayObject,NumberObject
    source=tmp_path/'base.pdf'
    pdf_fixture(source)
    writer=PdfWriter()
    writer.append(PdfReader(source))
    form=DecodedStreamObject()
    form.set_data(b'')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
                 NameObject('/BBox'):ArrayObject([NumberObject(n) for n in [0,0,20,20]]),
                 NameObject('/Resources'):DictionaryObject({NameObject('/Font'):DictionaryObject({
                     NameObject('/BadFont'):DictionaryObject({NameObject('/Type'):NameObject('/Font'),
                     NameObject('/Subtype'):NameObject('/Type3')})})})})
    writer.pages[-1]['/Resources'][NameObject('/XObject')]=DictionaryObject({NameObject('/Nested'):writer._add_object(form)})
    target=tmp_path/'nested.pdf'
    with target.open('wb') as stream:writer.write(stream)
    report=inspect_pdf(target,tmp_path/'nested-check')
    assert report['status']=='failed'
    assert report['pages'][0]['findings']==[]
    assert 'type3_font' in report['pages'][-1]['findings']


def test_missing_pdf_dependency_never_returns_pass(tmp_path,monkeypatch):
    import builtins
    source=tmp_path/'doc.pdf'
    pdf_fixture(source)
    original=builtins.__import__
    def importing(name,*args,**kwargs):
        if name=='pypdf':raise ImportError('fixture missing PDF parser')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',importing)
    with pytest.raises(ImportError,match='missing PDF parser'):
        inspect_pdf(source,tmp_path/'blocked')
    assert not (tmp_path/'blocked').exists()

def test_spreadsheet_stale_dimension_does_not_truncate_rows_or_columns(tmp_path):
    import io,re,zipfile
    from openpyxl import Workbook
    from modelcrew.document_tools import read_spreadsheet
    book=Workbook();book.active.append(['x','y']);book.active.append([1,2]);book.active.append([3,4])
    stream=io.BytesIO();book.save(stream)
    source=tmp_path/'stale-dimension.xlsx'
    with zipfile.ZipFile(stream) as original,zipfile.ZipFile(source,'w') as revised:
        for item in original.infolist():
            raw=original.read(item.filename)
            if item.filename=='xl/worksheets/sheet1.xml':
                raw=re.sub(br'<dimension ref="[^"]+"/>',b'<dimension ref="A1:A1"/>',raw)
            revised.writestr(item,raw)
    complete=read_spreadsheet(source)
    assert complete['sheets'][0]['rows']==[['x','y'],[1,2],[3,4]]
    data=read_data(source,header=True,sheet='Sheet',expected_rows=2)
    assert data['rows'][-1]==[3,4] and data['column_count']==2
