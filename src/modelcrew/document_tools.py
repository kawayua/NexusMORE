"""Pinned document tools for NexusMORE; no external skill installation.

This entry point runs a small tested subset, not the full paper export pipeline.
Upstream guides are reference data and cannot override project approval rules.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from importlib.metadata import distribution
from importlib.resources import as_file
from .package_resources import resource
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE = resource('document-tools')
TOOLS = {
    'pdf_read': {'script': None, 'suffix': '.pdf',
                 'dependencies': ['pypdf'], 'output': 'pages.json'},
    'pdf_fields': {'script': 'pdf/scripts/extract_form_field_info.py', 'suffix': '.pdf',
                   'dependencies': ['pypdf'], 'output': 'fields.json'},
    'pdf_structure': {'script': 'pdf/scripts/extract_form_structure.py', 'suffix': '.pdf',
                      'dependencies': ['pdfplumber'], 'output': 'structure.json'},
    'docx_validate': {'script': 'docx/scripts/office/validate.py', 'suffix': '.docx',
                      'dependencies': ['lxml', 'defusedxml'], 'output': None},
    'xlsx_read': {'script': None, 'suffix': '.xlsx',
                  'dependencies': ['openpyxl'], 'output': 'rows.json'},
    'xlsx_preview': {'script': None, 'suffix': '.xlsx',
                     'dependencies': ['openpyxl'], 'output': 'preview.json'},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_bundle(base=None):
    with as_file(base if base is not None else BASE) as directory:
        return _verify_bundle(directory)


def _verify_bundle(base):
    base = Path(base)
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['license'] != 'Apache-2.0':
        raise ValueError('Unrecognized tool license')
    root = (base / 'upstream').resolve()
    seen = set()
    for entry in manifest['files']:
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root) or entry['path'] in seen:
            raise ValueError('Unsafe or duplicate bundle path')
        seen.add(entry['path'])
        if sha(path) != entry['sha256']:
            raise ValueError('Changed bundled tool: ' + entry['path'])
    return {'status': 'passed', 'commit': manifest['commit'], 'files': len(seen),
            'manifest_sha256': sha(base / 'manifest.json')}


def available_tools():
    return {name: {**spec, 'missing_dependencies': [dep for dep in spec['dependencies']
                  if importlib.util.find_spec(dep) is None]} for name, spec in TOOLS.items()}


def read_spreadsheet(source, *, expected_rows=None, max_cells=1_000_000):
    """Read all declared worksheet rows without guessing a header or recalculating.

    Size limits and expected counts fail explicitly; this is never a preview.
    Formula strings remain formulas. Empty cells and the first row are retained.
    """
    from datetime import date, datetime, time, timedelta
    import math
    from openpyxl import load_workbook
    if type(max_cells) is not int or max_cells < 1:
        raise ValueError('max_cells must be a positive integer')
    if expected_rows is not None and (not isinstance(expected_rows, dict) or
            any(not isinstance(k, str) or type(v) is not int or v < 0 for k, v in expected_rows.items())):
        raise ValueError('expected_rows must map worksheet names to nonnegative row counts')
    def value(item):
        if isinstance(item, (datetime, date, time)):
            return item.isoformat()
        if isinstance(item, timedelta):
            return item.total_seconds()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError('Nonfinite spreadsheet cell')
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        raise ValueError('Unsupported spreadsheet cell type')
    book = load_workbook(source, read_only=True, data_only=False, keep_links=False)
    try:
        if expected_rows and set(expected_rows) - set(book.sheetnames):
            raise ValueError('Expected worksheet is missing')
        # Count streamed cells too: worksheet dimension metadata may be missing.
        count = 0
        sheets = []
        for sheet in book.worksheets:
            if sheet.max_row and sheet.max_column and count + sheet.max_row * sheet.max_column > max_cells:
                raise ValueError('Spreadsheet exceeds max_cells; no complete result returned')
            # Read to the actual end of worksheet XML; a stale/small dimension
            # must not truncate rows or columns in a plotting input.
            sheet.reset_dimensions()
            initial_count = count
            rows = []
            for row in sheet.iter_rows(values_only=True):
                count += max(1, len(row))
                if count > max_cells:
                    raise ValueError('Spreadsheet exceeds max_cells; no complete result returned')
                rows.append([value(cell) for cell in row])
            width = max((len(row) for row in rows), default=0)
            count = initial_count + len(rows) * max(1, width)
            if count > max_cells:
                raise ValueError('Spreadsheet exceeds max_cells; no complete result returned')
            rows = [row + [None] * (width-len(row)) for row in rows]
            if expected_rows is not None and sheet.title in expected_rows and len(rows) != expected_rows[sheet.title]:
                raise ValueError('Worksheet row count differs from expected_rows: ' + sheet.title)
            sheets.append({'name': sheet.title, 'rows': rows, 'row_count': len(rows),
                           'column_count': max((len(row) for row in rows), default=0)})
        return {'sheets': sheets, 'formula_values_recalculated': False,
                'complete': True, 'header_handling': 'preserved_as_data', 'cells_read': count}
    finally:
        book.close()


def run(tool, source, output_dir, *, timeout=60):
    with as_file(BASE) as directory:
        return _run(tool, source, output_dir, timeout=timeout, base=directory)


def _run(tool, source, output_dir, *, timeout, base):
    """Run on an input copy in a new output directory; never modify source.

    DOCX schema validation is structural only. XLSX preview reports formulas,
    not calculated values. Formal paper export and user approval stay separate.
    """
    if tool not in TOOLS:
        raise ValueError('Unknown document tool')
    spec = TOOLS[tool]
    source, output = Path(source).resolve(strict=True), Path(output_dir).resolve()
    if not source.is_file() or source.suffix.lower() != spec['suffix']:
        raise ValueError('Wrong input format')
    verified = verify_bundle(base)
    missing = available_tools()[tool]['missing_dependencies']
    if missing:
        return {'status': 'blocked', 'missing_dependencies': missing,
                'reason': 'Install the documents dependency group; see configs/dependencies/documents.txt', 'bundle': verified}
    original_hash = sha(source)
    output.mkdir(parents=True, exist_ok=False)
    staged = output / ('input' + source.suffix.lower())
    shutil.copyfile(source, staged)
    result = {'tool': tool, 'input_sha256': original_hash, 'bundle': verified,
              'output_dir': str(output), 'scope': 'document_tool_check_not_scientific_or_visual_approval'}
    if tool == 'pdf_read':
        from pypdf import PdfReader
        reader = PdfReader(staged)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF is not supported by this read-only route')
        if not 0 < len(reader.pages) <= 2000:
            raise ValueError('PDF page count exceeds bounded read scope')
        pages = []; total = 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ''
            total += len(text.encode('utf-8'))
            if total > 4*1024*1024:
                raise ValueError('PDF text exceeds complete-read limit; no truncated success')
            pages.append({'page':number, 'text':text})
        data = {'page_count':len(reader.pages), 'pages_read':len(pages), 'pages':pages,
                'complete':True, 'visual_review':'NOT_RUN', 'ocr_performed':False}
        (output / spec['output']).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        result.update(status='passed',returncode=0)
    elif tool == 'xlsx_read':
        data = read_spreadsheet(staged)
        (output / spec['output']).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        result.update(status='passed', returncode=0)
    elif tool == 'xlsx_preview':
        from openpyxl import load_workbook
        book = load_workbook(staged, read_only=True, data_only=False, keep_links=False)
        try:
            sheets = []
            for sheet in book.worksheets:
                rows = [[v if v is None or isinstance(v, (str, int, float, bool)) else str(v)
                         for v in row] for row in sheet.iter_rows(max_row=10, max_col=12, values_only=True)]
                sheets.append({'name': sheet.title, 'rows_reported': sheet.max_row,
                               'columns_reported': sheet.max_column, 'preview': rows})
            (output / spec['output']).write_text(json.dumps({'sheets': sheets,
                'formula_values_recalculated': False, 'preview_limit': {'rows': 10, 'columns': 12}},
                ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        finally:
            book.close()
        result.update(status='passed', returncode=0)
    else:
        script = Path(base / 'upstream' / spec['script']).resolve()
        dependency_roots = [str(Path(distribution(dep).locate_file('')).resolve()) for dep in spec['dependencies']]
        bootstrap = ('import sys,json,runpy;from pathlib import Path;'
                     'script=sys.argv.pop(1);roots=json.loads(sys.argv.pop(1));'
                     'sys.path[:0]=[str(Path(script).parent),*roots];sys.argv[0]=script;'
                     'runpy.run_path(script,run_name="__main__")')
        # Embeddable Windows Python's ._pth does not add the script directory.
        # Resolve only verified bundled siblings and declared installed deps.
        command = [sys.executable, '-I', '-X', 'utf8', '-c', bootstrap,
                   str(script), json.dumps(dependency_roots), str(staged)]
        if spec['output']:
            command.append(str(output / spec['output']))
        try:
            completed = subprocess.run(command, cwd=output, capture_output=True,
                                       timeout=timeout, shell=False,
                                       env={**os.environ, "PYTHONUTF8": "1"})
            (output / 'stdout.txt').write_bytes(completed.stdout)
            (output / 'stderr.txt').write_bytes(completed.stderr)
            result.update(status='passed' if completed.returncode == 0 else 'failed',
                          returncode=completed.returncode)
            if completed.returncode == 0 and spec['output'] and not (output / spec['output']).is_file():
                result.update(status='failed', reason='Tool exited without required output')
            elif completed.returncode == 0 and spec['output']:
                try:
                    value = json.loads((output / spec['output']).read_text(encoding='utf-8'))
                    if not isinstance(value, (dict, list)):
                        raise ValueError('Expected structured tool output')
                except (ValueError, UnicodeError):
                    result.update(status='failed', reason='Tool returned invalid structured output')
        except subprocess.TimeoutExpired as exc:
            (output / 'stdout.txt').write_bytes(exc.stdout or b'')
            (output / 'stderr.txt').write_bytes(exc.stderr or b'')
            result.update(status='timeout', returncode=None)
    if sha(source) != original_hash or sha(staged) != original_hash:
        result.update(status='failed', reason='Input bytes changed')
    (output / 'receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify', 'list', *TOOLS])
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        result = verify_bundle()
    elif args.action == 'list':
        result = available_tools()
    else:
        if not args.input or not args.output:
            parser.error('--input and --output are required for a tool run')
        result = run(args.action, args.input, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('status') in {'failed', 'blocked', 'timeout'}:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
