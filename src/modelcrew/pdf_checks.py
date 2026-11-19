"""Whole-document PDF checks and previews. Mechanical results never approve content."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _fonts(resources, seen=None):
    """Walk fonts inside Form XObjects and Type0 descendants, with cycle protection."""
    seen = set() if seen is None else seen
    if resources is None:
        return []
    obj = resources.get_object()
    if id(obj) in seen:
        return []
    seen.add(id(obj))
    result = []
    for name, ref in obj.get('/Font', {}).get_object().items() if '/Font' in obj else []:
        font = ref.get_object()
        children = font.get('/DescendantFonts', [])
        members = [item.get_object() for item in children] or [font]
        embedded = all(any(key in member.get('/FontDescriptor', {}).get_object()
                           for key in ['/FontFile', '/FontFile2', '/FontFile3'])
                       if '/FontDescriptor' in member else False for member in members)
        mismatches=[]
        for member in members:
            if '/FontDescriptor' not in member:continue
            descriptor=member['/FontDescriptor'].get_object()
            # FontFile2/CIDFontType2 require TrueType outlines. Matplotlib can
            # label an OpenType-CFF subset this way; some renderers drop glyphs.
            if '/FontFile2' in descriptor:
                program=descriptor['/FontFile2'].get_object().get_data()
                if program[:4]==b'OTTO':mismatches.append('OpenType-CFF program declared as TrueType FontFile2')
        item={'name': str(name), 'base_font': str(font.get('/BaseFont', '')),
              'type': str(font.get('/Subtype', '')), 'embedded': embedded}
        if mismatches:item['program_type_mismatches']=mismatches
        result.append(item)
    if '/XObject' in obj:
        for ref in obj['/XObject'].get_object().values():
            result += _fonts(ref.get_object().get('/Resources'), seen)
    return result


def inspect_pdf(source, output_dir, *, dpi=144, minimum_font_pt=5, max_pages=1000,
                max_page_pixels=40_000_000):
    """Render every physical page into a NEW directory or fail without a PASS.

    Resource bounds reject the document, never silently truncate. Font embedding
    warnings and raster-only pages require visual review, not an invented PASS.
    """
    import fitz
    from pypdf import PdfReader
    source = Path(source).resolve(strict=True)
    output = Path(output_dir).resolve()
    if source.is_relative_to(output):
        raise ValueError('PDF source must be outside preview directory')
    if not math.isfinite(dpi) or not 72 <= dpi <= 600:
        raise ValueError('Preview DPI must be between 72 and 600')
    if not math.isfinite(minimum_font_pt) or minimum_font_pt < 5:
        raise ValueError('Minimum font size cannot be below 5 pt')
    if type(max_pages) is not int or max_pages < 1 or type(max_page_pixels) is not int or max_page_pixels < 1:
        raise ValueError('PDF resource limits must be positive integers')
    original = sha(source)
    reader = PdfReader(source, strict=True)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF cannot be audited')
    with fitz.open(source) as document:
        count = len(document)
        if not count or count > max_pages or count != len(reader.pages):
            raise ValueError('PDF page count invalid or exceeds complete audit limit')
        for page in document:
            if math.ceil(page.rect.width*dpi/72)*math.ceil(page.rect.height*dpi/72) > max_page_pixels:
                raise ValueError('PDF page exceeds complete preview pixel limit')
        output.mkdir(parents=True, exist_ok=False)
        pages = []
        for index, page in enumerate(document, 1):
            preview = output / f'page-{index:04}.png'
            page.get_pixmap(dpi=int(dpi), alpha=False).save(preview)
            spans = [span for block in page.get_text('dict', clip=fitz.INFINITE_RECT())['blocks']
                     if 'lines' in block for line in block['lines'] for span in line['spans']
                     if span['text'].strip()]
            findings = []
            for span in spans:
                if span['size'] < minimum_font_pt - 0.01:
                    findings.append('font_below_minimum')
                if '\ufffd' in span['text'] or '\x00' in span['text']:
                    findings.append('unmapped_glyph')
                x0, y0, x1, y1 = fitz.Rect(span['bbox']) * page.rotation_matrix
                if x0 < -1 or y0 < -1 or x1 > page.rect.width+1 or y1 > page.rect.height+1:
                    findings.append('text_outside_page')
            fonts = _fonts(reader.pages[index-1].get('/Resources'))
            if any(f['type'] == '/Type3' for f in fonts):
                findings.append('type3_font')
            warnings = []
            if any(not f['embedded'] for f in fonts):
                warnings.append('unembedded_font_requires_review')
            if any(f.get('program_type_mismatches') for f in fonts):
                warnings.append('embedded_font_program_type_mismatch_requires_visual_review')
            if not spans:
                warnings.append('no_extractable_text_requires_visual_review')
            pages.append({'page': index, 'width_pt': page.rect.width, 'height_pt': page.rect.height,
                          'preview': preview.name, 'preview_sha256': sha(preview),
                          'minimum_font_pt': min((s['size'] for s in spans), default=None),
                          'fonts': fonts, 'findings': sorted(set(findings)), 'warnings': warnings})
    if sha(source) != original:
        raise ValueError('PDF changed during audit')
    report = {'schema_version': '1.0.0', 'source_sha256': original, 'page_count': count,
              'pages': pages, 'preview_dpi': int(dpi),
              'status': 'failed' if any(p['findings'] for p in pages) else 'passed',
              'visual_review': 'PENDING', 'independent_review': 'NOT_RUN',
              'scope': 'All-page rendering, text bounds, minimum font and recursive font inventory; '
                       'not a collision detector, scientific validation or visual approval'}
    with (output/'pdf-check.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return report


def verify_pdf_report(source, output_dir, report):
    """Admission check against actual PDF and EVERY preview, including last page."""
    import fitz
    output = Path(output_dir).resolve()
    actual_sha=sha(source)
    if report.get('source_sha256') != actual_sha:
        raise ValueError('PDF source changed: '+Path(source).name+'; report/source SHA256 differ')
    if report.get('status') != 'passed':
        details=[]
        for page in report.get('pages',[]):
            if page.get('findings'):
                details.append('page '+str(page.get('page'))+': '+', '.join(page['findings']))
        raise ValueError('PDF check failed: '+Path(source).name+'; '+('; '.join(details) or 'report status='+str(report.get('status'))))
    with fitz.open(source) as document:
        count = len(document)
    pages = report.get('pages', [])
    if not count or report.get('page_count') != count or [p['page'] for p in pages] != list(range(1, count+1)):
        raise ValueError('PDF preview page coverage incomplete')
    for page in pages:
        if page['preview'] != f'page-{page["page"]:04}.png':
            raise ValueError('PDF preview page identity differs')
        preview = (output / page['preview']).resolve(strict=True)
        if not preview.is_relative_to(output) or sha(preview) != page['preview_sha256'] or page.get('findings'):
            raise ValueError('PDF preview changed or failed')
    return True


def audit_pdf_tree(source, output_dir):
    """Audit every PDF under an explicitly selected bundle, retaining every failure."""
    source = Path(source).resolve(strict=True)
    output = Path(output_dir).resolve()
    if source.is_dir() and output.is_relative_to(source):
        raise ValueError('Audit output must be outside the selected PDF source tree')
    paths = [source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower()=='.pdf')
    if not paths or any(p.suffix.lower()!='.pdf' for p in paths):
        raise ValueError('No PDF documents found')
    output.mkdir(parents=True,exist_ok=False)
    results=[]
    for index,path in enumerate(paths,1):
        try:
            folder=output/f'pdf-{index:04}'
            report=inspect_pdf(path,folder)
            verify_pdf_report(path,folder,report)
            results.append({'source':str(path),'status':'passed','page_count':report['page_count'],
                            'report':folder.name+'/pdf-check.json','report_sha256':sha(folder/'pdf-check.json')})
        except ImportError as exc:
            results.append({'source':str(path),'status':'blocked','error':str(exc)})
        except Exception as exc:
            results.append({'source':str(path),'status':'failed','error':str(exc)})
    status='failed' if any(r['status']=='failed' for r in results) else 'blocked' if any(r['status']=='blocked' for r in results) else 'passed'
    summary={'status':status,'documents':results,'visual_review':'PENDING','independent_review':'NOT_RUN'}
    with (output/'pdf-tree-check.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(summary,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    return summary


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Render and mechanically check EVERY PDF page in a selected bundle')
    parser.add_argument('source')
    parser.add_argument('output_dir')
    args=parser.parse_args()
    try:
        result=audit_pdf_tree(args.source,args.output_dir)
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)},ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['status']=='passed' else 1)
