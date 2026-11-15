from modelcrew.project_assets import local_history
"""Document-tool integration checks use only generated synthetic inputs."""
import json
import shutil
from pathlib import Path

import pytest

from modelcrew import document_tools as tools


def test_pinned_bundle_and_each_original_has_a_decision():
    assert tools.verify_bundle()['files'] == 126
    review = json.loads((local_history('resources/provenance/document-tools-review.json')).read_text(encoding='utf-8'))
    assert len(review['files']) == 84
    assert len({f['id'] for f in review['files']}) == 84
    assert all(not f['copied_from_local'] for f in review['files'])


def test_modified_vendor_is_rejected(tmp_path):
    altered = tmp_path / 'bundle'
    shutil.copytree(tools.BASE, altered)
    (altered / 'upstream/pdf/LICENSE.txt').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='Changed bundled tool'):
        tools.verify_bundle(altered)


@pytest.fixture
def pdf(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    path = tmp_path / 'form.pdf'
    canvas = Canvas(str(path))
    canvas.drawString(50, 750, 'Synthetic test input')
    canvas.acroForm.textfield(name='sample', x=50, y=700, width=120, height=20)
    canvas.showPage()
    canvas.save()
    return path


def test_real_pdf_fields_and_source_unchanged(pdf, tmp_path):
    before = tools.sha(pdf)
    output = tmp_path / 'fields'
    result = tools.run('pdf_fields', pdf, output)
    assert result['status'] == 'passed', (output / 'stderr.txt').read_text()
    fields = json.loads((output / 'fields.json').read_text())
    assert fields[0]['field_id'] == 'sample'
    assert before == tools.sha(pdf)
    with pytest.raises(FileExistsError):
        tools.run('pdf_fields', pdf, output)


def test_real_pdf_structure(pdf, tmp_path):
    output = tmp_path / 'structure'
    result = tools.run('pdf_structure', pdf, output)
    assert result['status'] == 'passed', (output / 'stderr.txt').read_text()
    assert len(json.loads((output / 'structure.json').read_text())['pages']) == 1


def test_xlsx_formulas_preserved_not_claimed_recalculated(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.append([2, 3, '=SUM(A1:B1)'])
    source = tmp_path / 'table.xlsx'
    book.save(source)
    before = tools.sha(source)
    output = tmp_path / 'preview'
    assert tools.run('xlsx_preview', source, output)['status'] == 'passed'
    result = json.loads((output / 'preview.json').read_text())
    assert result['sheets'][0]['preview'][0][:3] == [2, 3, '=SUM(A1:B1)']
    assert result['formula_values_recalculated'] is False
    assert tools.sha(source) == before


def test_real_docx_schema_check(tmp_path):
    from docx import Document
    output = tmp_path / 'word-check'
    source = tmp_path / 'document.docx'
    doc = Document()
    doc.add_paragraph('Synthetic document')
    from docx.oxml.ns import qn
    # python-docx's default template omits a required zoom attribute.
    doc.settings.element.find(qn('w:zoom')).set(qn('w:percent'), '100')
    doc.save(source)
    before = tools.sha(source)
    result = tools.run('docx_validate', source, output)
    if result['status'] == 'blocked':
        pytest.skip('Install declared document-tool dependencies for real DOCX validation')
    assert result['status'] == 'passed', (output / 'stdout.txt').read_text() + (output / 'stderr.txt').read_text()
    assert tools.sha(source) == before


def test_missing_dependency_does_not_create_output(tmp_path, monkeypatch):
    source = tmp_path / 'document.docx'
    source.write_bytes(b'test')
    output = tmp_path / 'blocked'
    monkeypatch.setattr(tools, 'available_tools', lambda: {'docx_validate': {'missing_dependencies': ['defusedxml']}})
    assert tools.run('docx_validate', source, output)['status'] == 'blocked'
    assert not output.exists()
