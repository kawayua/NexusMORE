"""Verify the real local BGE + remote Qdrant loop and save transparent evidence."""
from modelcrew.project_assets import asset_path
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modelcrew.config import ROOT
from modelcrew.retrieval import Retriever, RetrievalUnavailable, from_config, ingest


def main():
    started = time.monotonic()
    service = from_config()
    queries = json.loads((asset_path(ROOT,'stage-c/corpus/queries.json')).read_text(encoding='utf-8-sig'))
    checks = []
    for query in queries:
        result = service.search(query['query'], limit=3, filters=query['filters'],
                                include_same_problem=query.get('include_same_problem', False))
        rank = next((i for i, hit in enumerate(result['hits'], 1)
                     if hit['doc_id'] == query['expected_doc_id'] and
                     ('expected_page' not in query or hit['locator'].get('page') == query['expected_page']) and
                     any(term.lower() in hit['text'].lower() for term in query['expected_text_any'])), None)
        checks.append({'id': query['id'], 'passed': rank is not None, 'expected_rank': rank,
                       'expected_doc_id': query['expected_doc_id'], 'expected_text_any': query['expected_text_any'], 'result': result})
    result = service.search('相邻把手距离约束', filters={'kind': 'paper'})
    checks.append({'id': 'same_problem_absent', 'passed': result['hits'] == [], 'result': result})
    allowed=service.search('相邻把手', include_same_problem=True)
    checks.append({'id':'same_problem_reference_mode_allowed','passed':allowed['include_same_problem'] is True})
    result = service.search('板凳龙', filters={'case_id': 'nonexistent-case'})
    checks.append({'id': 'empty_filter_is_success', 'passed': result['status'] == 'ok' and result['hits'] == [], 'result': result})
    result = service.search('板凳龙', filters={'year': 1999})
    checks.append({'id': 'year_filter_empty', 'passed': result['hits'] == [], 'result': result})
    wrong = Retriever(service.client, service.embedder, service.collection, 'wrong-corpus')
    try:
        wrong.search('板凳龙')
        mismatch = False
    except RetrievalUnavailable:
        mismatch = True
    checks.append({'id': 'index_identity_mismatch_rejected', 'passed': mismatch})
    from qdrant_client import QdrantClient
    offline = QdrantClient(url='http://127.0.0.1:1', timeout=1, check_compatibility=False)
    try:
        Retriever(offline, service.embedder, service.collection, service.corpus_sha256).search('板凳龙')
        fault_is_error = False
    except RetrievalUnavailable:
        fault_is_error = True
    finally:
        offline.close()
    checks.append({'id': 'unreachable_server_is_error_not_empty', 'passed': fault_is_error})
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    with TestClient(create_app(retrieval_factory=lambda: service)) as client:
        response = client.post('/search', json={'query': 'brentq 连续函数区间异号求根',
                               'filters': {'kind': 'algorithm'}})
        payload = response.json()
        api_ok = response.status_code == 200 and bool(payload.get('hits')) and payload['hits'][0]['kind'] == 'algorithm'
    checks.append({'id': 'http_real_embedding_and_server', 'passed': api_ok, 'result': payload})
    # Reuse the already-created index without re-embedding or adding duplicate points.
    corpus_path = asset_path(ROOT,'stage-c/runs/corpus-independent-20261106/corpus.json')
    corpus = json.loads(corpus_path.read_text(encoding='utf-8-sig'))
    before = service.client.count(service.collection, exact=True).count
    repeated = ingest(service.client, service.embedder, corpus)
    after = service.client.count(service.collection, exact=True).count
    checks.append({'id': 'idempotent_ingestion', 'passed': repeated == service.collection and before == after == len(corpus['chunks'])+1,
                   'point_count_before': before, 'point_count_after': after})
    checks.append({'id': 'active_corpus_excludes_same_problem', 'passed': all(c.get('same_problem_reference') is False for c in corpus['chunks']) and not any(d['id'] == 'cumcm2024a-a163' for d in corpus['documents'])})
    # Check every hit's stored text against the immutable prepared corpus.
    originals = {chunk['chunk_id']: chunk for chunk in corpus['chunks']}
    provenance_ok = all(all(originals[h['chunk_id']][key] == h[key] for key in
                        ['text', 'source_sha256', 'locator', 'source_url', 'parser'])
                        for check in checks if 'result' in check for h in check['result']['hits'])
    checks.append({'id': 'hit_text_and_locators_match_ingestion', 'passed': provenance_ok})
    report = {'date': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'status': 'passed' if all(c['passed'] for c in checks) else 'failed',
              'model': service.embedder.identity['name'], 'model_path': str(service.embedder.path),
              'embedding_signature': service.embedder.signature, 'dimension': service.embedder.dimension,
              'collection': service.collection, 'corpus_sha256': service.corpus_sha256,
              'document_count': len(corpus['documents']), 'chunk_count': len(corpus['chunks']),
              'checks': checks, 'seconds': round(time.monotonic()-started, 2),
              'new_llm_api_calls': 0, 'new_solve_executions': 0,
              'scope': 'Reference-assisted retrieval smoke test against the unchanged 3-source index. Not an independent modeling evaluation.'}
    target = asset_path(ROOT,'stage-c/runs')/('c2-reference-retrieval-'+datetime.now().strftime('%Y%m%dT%H%M%S%f')+'.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'checks'}, ensure_ascii=True))
    print(json.dumps([{'id':c['id'],'passed':c['passed'],'rank':c.get('expected_rank')} for c in checks]))
    service.client.close()
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
