"""Explicit, complete plotting data reads. No guessed headers or silent dropna."""
from __future__ import annotations

import csv
import math
from pathlib import Path
from .pdf_checks import sha


def read_data(source, *, header, sheet=None, expected_rows=None, max_cells=1_000_000):
    """header=True/False is mandatory. Excel requires an explicit sheet name.

    Rows include blanks and original first/last records. Formula expressions stay
    expressions and are rejected by numeric profiling until genuinely calculated.
    """
    if type(header) is not bool:
        raise ValueError('Choose header=True or header=False explicitly')
    if type(max_cells) is not int or max_cells < 1:
        raise ValueError('max_cells must be a positive integer')
    if expected_rows is not None and (type(expected_rows) is not int or expected_rows < 0):
        raise ValueError('expected_rows must be nonnegative')
    source = Path(source).resolve(strict=True)
    before = sha(source)
    if source.suffix.lower() in {'.csv', '.tsv'}:
        if sheet is not None:
            raise ValueError('CSV/TSV has no sheet')
        rows = []
        cells = 0
        with source.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.reader(stream, delimiter='\t' if source.suffix.lower()=='.tsv' else ','):
                rows.append(row)
                cells += max(1, len(row))
                if cells > max_cells:
                    raise ValueError('Data exceeds max_cells; no complete result returned')
    elif source.suffix.lower() == '.xlsx':
        if not isinstance(sheet, str) or not sheet:
            raise ValueError('XLSX requires an explicit worksheet name')
        from .document_tools import read_spreadsheet
        book = read_spreadsheet(source, max_cells=max_cells)
        matches = [s for s in book['sheets'] if s['name'] == sheet]
        if not matches:
            raise ValueError('Requested worksheet missing')
        rows = matches[0]['rows']
    else:
        raise ValueError('Supported data formats: CSV, TSV, XLSX')
    if sha(source) != before:
        raise ValueError('Data changed while reading')
    columns = rows[0] if header and rows else None
    records = rows[1:] if header else rows
    width = len(columns) if columns is not None else max((len(r) for r in rows), default=0)
    if columns is not None and (any(v is None or str(v).strip()=='' for v in columns) or len(set(map(str, columns))) != len(columns)):
        raise ValueError('Headers must be nonempty and unique')
    if any(len(row) not in {0, width} for row in records):
        raise ValueError('Ragged data records require an explicit correction')
    if expected_rows is not None and len(records) != expected_rows:
        raise ValueError('Data row count differs from expected_rows')
    return {'source_sha256': before, 'sheet': sheet, 'header': header, 'columns': columns,
            'rows': records, 'row_count': len(records), 'source_row_count': len(rows),
            'column_count': width, 'complete': True, 'transformations': [],
            'formula_values_recalculated': False}


def profile_numeric(data, columns, *, units):
    """Return missing counts and pairwise retained N; never mutate/drop raw rows."""
    if not columns or len(set(columns)) != len(columns):
        raise ValueError('Numeric columns must be nonempty and unique')
    values = {}
    for column in columns:
        if type(column) is not int or not 0 <= column < data['column_count'] or column not in units or not isinstance(units[column], str) or not units[column].strip():
            raise ValueError('Every numeric column requires a valid index and explicit unit')
        items = []
        for row in data['rows']:
            value = row[column] if row else None
            if value is None or isinstance(value, str) and not value.strip():
                items.append(None)
                continue
            if isinstance(value, bool) or isinstance(value, str) and value.startswith('='):
                raise ValueError('Boolean or unresolved formula is not verified numeric data')
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError('Nonfinite numeric data')
            items.append(numeric)
        values[column] = items
    pairs = []
    for i, left in enumerate(columns):
        for right in columns[i:]:
            kept = [(a,b) for a,b in zip(values[left], values[right]) if a is not None and b is not None]
            n = len(kept)
            correlation = None
            if n >= 2:
                xs, ys = zip(*kept)
                ax, ay = sum(xs)/n, sum(ys)/n
                xx, yy = sum((x-ax)**2 for x in xs), sum((y-ay)**2 for y in ys)
                if xx and yy:
                    correlation = sum((x-ax)*(y-ay) for x,y in kept)/math.sqrt(xx*yy)
            pairs.append({'columns': [left,right], 'retained_n': n,
                          'missing_pair_rows': data['row_count']-n, 'pearson_r': correlation,
                          'undefined_reason': None if correlation is not None else 'insufficient_or_constant_data'})
    return {'source_sha256': data['source_sha256'], 'row_count': data['row_count'],
            'columns': [{'index': c, 'unit': units[c], 'observed_n': sum(v is not None for v in values[c]),
                         'missing_n': sum(v is None for v in values[c])} for c in columns],
            'pairwise': pairs, 'transformations': [], 'correlation_policy': 'pairwise_observed_with_explicit_N'}
