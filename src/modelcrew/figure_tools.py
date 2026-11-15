"""Project-authored Python figure export and whole-catalog PDF admission."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import warnings
import xml.etree.ElementTree as ET

from .pdf_checks import inspect_pdf, verify_pdf_report, sha


BINDING_FIELDS = {'task_id', 'contract_version', 'contract_sha256', 'execution_id', 'result_revision'}


def _write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def _asset(root, item):
    path = (root/item['path']).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file() or sha(path) != item['sha256']:
        raise ValueError('Figure file missing, changed or outside catalog')
    return path


def _svg(path):
    raw = Path(path).read_bytes()
    # Matplotlib includes the standard SVG 1.1 declaration. ElementTree does
    # not fetch that DTD; reject custom declarations and entity definitions.
    safe = re.sub(br'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1\.1//EN"\s+"http://www\.w3\.org/Graphics/SVG/1\.1/DTD/svg11\.dtd">', b'', raw)
    if b'<!DOCTYPE' in safe.upper() or b'<!ENTITY' in safe.upper():
        raise ValueError('SVG declarations are not accepted')
    tree = ET.ElementTree(ET.fromstring(raw))
    if tree.getroot().tag != '{http://www.w3.org/2000/svg}svg':
        raise ValueError('Invalid SVG document')
    for element in tree.iter():
        if element.tag.split('}')[-1] in {'script', 'foreignObject'}:
            raise ValueError('Active SVG content is not an accepted figure')
        for key, value in element.attrib.items():
            if key.split('}')[-1].startswith('on') or key.split('}')[-1] == 'href' and not value.startswith(('#', 'data:image/png;base64,')):
                raise ValueError('External or active SVG reference')


def export_figure(figure, output_dir, *, figure_id, binding, inputs, code, parameters,
                  dpi=300):
    """New directory, PNG/PDF/SVG, grayscale copy, all-page QA and last success marker.

    Executing a plotting program belongs to the controlled executor. This helper
    exports an already-created matplotlib Figure; it never execs a supplied script.
    """
    import matplotlib as mpl
    from matplotlib.text import Text
    from PIL import Image
    if not isinstance(figure_id, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', figure_id):
        raise ValueError('Figure id must use lowercase hyphen naming')
    if not BINDING_FIELDS <= set(binding) or any(not binding[k] for k in BINDING_FIELDS):
        raise ValueError('Complete task/contract/execution/revision binding required')
    if not re.fullmatch(r'[0-9a-f]{64}', binding['contract_sha256']):
        raise ValueError('Invalid contract hash')
    if any(type(binding[k]) is not int or binding[k] < 1 for k in ['contract_version', 'result_revision']):
        raise ValueError('Contract version and result revision must be positive integers')
    if type(dpi) is not int or not 300 <= dpi <= 1200:
        raise ValueError('Figure PNG requires 300–1200 DPI')
    if not inputs:
        raise ValueError('Verified input data required')
    sources = [*inputs, code]
    for item in sources:
        if sha(item['path']) != item['sha256']:
            raise ValueError('Figure data or code changed')
    # Validate metadata before touching output, including NaN and non-JSON values.
    json.dumps({'binding': binding, 'parameters': parameters, 'inputs': inputs, 'code': code}, allow_nan=False)
    output = Path(output_dir).resolve()
    if any(Path(item['path']).resolve().is_relative_to(output) for item in sources):
        raise ValueError('Figure sources must be outside new export directory')
    size = tuple(float(x) for x in figure.get_size_inches())
    if any(not math.isfinite(x) or not 0 < x <= 40 for x in size):
        raise ValueError('Invalid figure physical dimensions')
    if math.ceil(size[0]*dpi)*math.ceil(size[1]*dpi) > 40_000_000:
        raise ValueError('Figure exceeds complete raster check limit')
    output.mkdir(parents=True, exist_ok=False)
    stage = output/'.incomplete'
    stage.mkdir()
    try:
        with mpl.rc_context({'pdf.fonttype': 42, 'ps.fonttype': 42,
                             'svg.fonttype': 'none', 'svg.hashsalt': figure_id,
                             'savefig.bbox': None, 'savefig.transparent': False}):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                figure.canvas.draw()
                renderer = figure.canvas.get_renderer()
                for text in figure.findobj(Text):
                    if not text.get_visible() or not text.get_text().strip():
                        continue
                    if text.get_fontsize() < 5:
                        raise ValueError('Figure text below 5 pt')
                box = figure.get_tightbbox(renderer)
                if box.x0 < -1/72 or box.y0 < -1/72 or box.x1 > size[0]+1/72 or box.y1 > size[1]+1/72:
                    raise ValueError('Figure text outside physical canvas')
                for fmt in ['png', 'pdf', 'svg']:
                    metadata = {'CreationDate': None, 'ModDate': None} if fmt=='pdf' else {'Date': None} if fmt=='svg' else {}
                    figure.savefig(stage/f'{figure_id}.{fmt}', format=fmt, dpi=dpi,
                                   bbox_inches=None, facecolor='white', metadata=metadata)
                if any('glyph' in str(item.message).lower() and 'missing' in str(item.message).lower() for item in caught):
                    raise ValueError('Missing figure glyph; install an appropriate font')
        _svg(stage/f'{figure_id}.svg')
        with Image.open(stage/f'{figure_id}.png') as image:
            image.load()
            if min(image.info.get('dpi', (0, 0))) < dpi-1 or any(abs(a-b*dpi)>1 for a,b in zip(image.size,size)):
                raise ValueError('PNG dimensions or DPI differ from requested physical size')
            image.convert('L').save(stage/f'{figure_id}-grayscale.png', dpi=(dpi,dpi))
        pdf_report = inspect_pdf(stage/f'{figure_id}.pdf', stage/'pdf-preview')
        verify_pdf_report(stage/f'{figure_id}.pdf', stage/'pdf-preview', pdf_report)
        if pdf_report['page_count'] != 1 or any(abs(a-b*72)>0.1 for a,b in zip(
                [pdf_report['pages'][0]['width_pt'], pdf_report['pages'][0]['height_pt']], size)):
            raise ValueError('Exported PDF physical dimensions changed')
        for item in sources:
            if sha(item['path']) != item['sha256']:
                raise ValueError('Figure data or code changed during export')
        files = {fmt: {'path': f'{figure_id}.{fmt}', 'sha256': sha(stage/f'{figure_id}.{fmt}')}
                 for fmt in ['png','pdf','svg']}
        result = {'schema_version': '1.0.0', 'backend': 'python', 'figure_id': figure_id,
                  'binding': binding, 'inputs': inputs, 'code': code, 'parameters': parameters,
                  'size_inches': size, 'png_dpi': dpi, 'files': files,
                  'grayscale': {'path': f'{figure_id}-grayscale.png', 'sha256': sha(stage/f'{figure_id}-grayscale.png')},
                  'pdf_check': {'path': 'pdf-preview/pdf-check.json', 'sha256': sha(stage/'pdf-preview/pdf-check.json')},
                  'status': 'passed', 'visual_review': 'PENDING', 'independent_review': 'NOT_RUN'}
        # Everything is checked before promotion. No success marker on interruption.
        for path in list(stage.iterdir()):
            path.rename(output/path.name)
        stage.rmdir()
        _write(output/'figure-export.json', result)
        return result
    except Exception as exc:
        _write(output/'figure-export-failed.json', {'status': 'failed', 'error': str(exc)})
        raise


def audit_catalog(catalog_path, output_dir):
    """Check ALL candidates, ALL formats, and EVERY PDF page before P2 admission."""
    from PIL import Image
    catalog_path = Path(catalog_path).resolve(strict=True)
    original = sha(catalog_path)
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    figures = catalog['figures']
    ids = [f['id'] for f in figures]
    if not figures or len(ids) != len(set(ids)):
        raise ValueError('Empty or duplicate figure catalog')
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    checked = []
    for index, figure in enumerate(figures, 1):
        paths = {fmt: _asset(catalog_path.parent, figure['files'][fmt]) for fmt in ['png','pdf','svg']}
        with Image.open(paths['png']) as image:
            image.load()
            if image.format != 'PNG' or min(image.info.get('dpi', (0,0))) < 299:
                raise ValueError('Invalid or low DPI PNG: '+figure['id'])
        _svg(paths['svg'])
        preview = output/f'figure-{index:04}'
        pdf = inspect_pdf(paths['pdf'], preview)
        verify_pdf_report(paths['pdf'], preview, pdf)
        for fmt in paths:
            _asset(catalog_path.parent, figure['files'][fmt])
        checked.append({'figure_id': figure['id'], 'pdf': preview.name+'/pdf-check.json',
                        'pdf_report_sha256': sha(preview/'pdf-check.json'), 'page_count': pdf['page_count']})
    if sha(catalog_path) != original:
        raise ValueError('Figure catalog changed during audit')
    result = {'schema_version': '1.0.0', 'status': 'passed', 'catalog_sha256': original,
              'figures': checked, 'visual_review': 'PENDING', 'independent_review': 'NOT_RUN'}
    _write(output/'catalog-check.json', result)
    return result


def verify_catalog_report(catalog_path, output_dir, report):
    """Check a cached mechanical report without rerendering or accepting omissions."""
    catalog_path = Path(catalog_path).resolve(strict=True)
    output = Path(output_dir).resolve()
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    if report.get('status') != 'passed' or report.get('catalog_sha256') != sha(catalog_path):
        raise ValueError('Catalog check failed or catalog changed')
    if [f['id'] for f in catalog['figures']] != [f['figure_id'] for f in report.get('figures', [])]:
        raise ValueError('Catalog check figure coverage incomplete')
    for figure, item in zip(catalog['figures'], report['figures']):
        for fmt in ['png','pdf','svg']:
            _asset(catalog_path.parent, figure['files'][fmt])
        path = _asset(output, {'path': item['pdf'], 'sha256': item['pdf_report_sha256']})
        pdf = json.loads(path.read_text(encoding='utf-8'))
        if item['page_count'] != pdf['page_count']:
            raise ValueError('Catalog PDF count differs')
        verify_pdf_report(_asset(catalog_path.parent, figure['files']['pdf']), path.parent, pdf)
    return True
