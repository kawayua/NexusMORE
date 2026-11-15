"""Read-only local database path inventory; never dump payloads or credentials."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import psycopg
from psycopg import sql
from modelcrew.config import ROOT, database_url

TOKEN = re.compile(r"stage-[a-z][a-z0-9+-]*(?:/[^\s\"'`<>)}\],;]*)?")


def tokens(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from tokens(key)
            yield from tokens(child)
    elif isinstance(value, list):
        for child in value:
            yield from tokens(child)
    elif isinstance(value, str):
        yield from (m.group() for m in TOKEN.finditer(value.replace('\\', '/')))


def audit():
    rows, references = [], Counter()
    # No Workflow() initialization, migrations, checkpoint writes or live task advancement.
    with psycopg.connect(database_url(), connect_timeout=5,
                         options='-c default_transaction_read_only=on -c statement_timeout=30000') as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        columns = db.execute("SELECT table_name, column_name FROM information_schema.columns "
                             "WHERE table_schema='public' AND starts_with(table_name, 'mc_') "
                             "AND data_type IN ('jsonb','json','text','character varying') "
                             "ORDER BY table_name, ordinal_position").fetchall()
        tables = sorted({table for table, _ in columns})
        for table in tables:
            count = db.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
            rows.append({'table': table, 'rows': count})
        for table, column in columns:
            query = sql.SQL("SELECT {} FROM {} WHERE {}::text LIKE %s").format(
                sql.Identifier(column), sql.Identifier(table), sql.Identifier(column))
            count, digest = 0, hashlib.sha256()
            values = []
            with db.cursor(name='path_scan') as cursor:
                cursor.execute(query, ('%stage-%',))
                for (value,) in cursor:
                    count += 1
                    # Hash evidence only; do not include source strings or record bodies.
                    values.append(hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                                           ensure_ascii=False).encode()).hexdigest())
                    for token in tokens(value):
                        references[token] += 1
            for value in sorted(values):
                digest.update(value.encode())
            if count:
                rows.append({'table': table, 'column': column, 'matching_values': count,
                             'matching_values_sha256': digest.hexdigest()})
    return {'schema_version': '1.0.0', 'read_only': True, 'coverage': 'public.mc_* text/json columns',
            'limitations': ['Checkpoint bytea and external services are not inspected.',
                            'Path tokens may include prose; no automatic migration is authorized.'],
            'tables_and_columns': rows,
            'references': [{'path': path, 'occurrences': count} for path, count in sorted(references.items())]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'tmp'):
        parser.error('Database inventory must stay under workspace tmp/')
    if output.exists():
        raise FileExistsError(output)
    try:
        report = audit()
    except (psycopg.Error, RuntimeError) as exc:
        # Exception strings may contain DSNs, passwords or server details.
        report = {'schema_version': '1.0.0', 'read_only': True, 'status': 'unavailable',
                  'error_type': type(exc).__name__, 'database_audited': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report.get('status', 'passed'),
                      'distinct_stage_paths': len(report.get('references', []))}))


if __name__ == '__main__':
    main()
