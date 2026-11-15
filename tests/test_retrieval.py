"""Real Qdrant local engine with synthetic vectors: protocol tests, not semantic evaluation."""
import copy
import json

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from modelcrew.api import create_app
from modelcrew.contracts import digest
from modelcrew.corpus import split_text
from modelcrew.retrieval import META_ID, Retriever, RetrievalUnavailable, ingest


class SyntheticEmbedder:
    dimension = 2
    signature = 'TEST_ONLY_synthetic_vectors'

    def encode(self, texts, *, query=False):
        return [[1., 0.] if 'alpha' in text else [0., 1.] for text in texts]


@pytest.fixture
def indexed():
    client = QdrantClient(':memory:')
    model = SyntheticEmbedder()
    chunks = []
    for i, (kind, text, same) in enumerate([
        ('problem_statement', 'alpha statement', False),
        ('paper', 'alpha general paper', False),
        ('algorithm', 'beta algorithm', False),
    ]):
        chunks.append({'record_type': 'chunk', 'chunk_id': str(i), 'doc_id': 'doc-' + str(i),
                       'kind': kind, 'text': text, 'same_problem_reference': same,
                       'year': 2024, 'case_id': 'TEST', 'locator': {'page': i+1, 'char_start': 0, 'char_end': len(text)}})
    corpus = {'documents': [], 'chunks': chunks}
    corpus['corpus_sha256'] = digest(corpus)
    collection = ingest(client, model, corpus)
    yield Retriever(client, model, collection, corpus['corpus_sha256']), corpus
    client.close()


def test_split_offsets_cover_source_without_truncation():
    text = '板凳龙几何距离与弧长' * 100
    pieces = list(split_text(text))
    covered = set()
    for start, end, chunk in pieces:
        assert chunk == text[start:end] and len(chunk) <= 360
        covered.update(range(start, end))
    assert covered == set(range(len(text)))
    with pytest.raises(ValueError): list(split_text(text, 10, 10))


def test_search_filters_and_same_problem_policy(indexed):
    service, _ = indexed
    result = service.search('alpha')
    assert result['status'] == 'ok'
    assert all(h['same_problem_reference'] is False for h in result['hits'])
    assert service.search('alpha', filters={'kind': 'paper'}, include_same_problem=True)['include_same_problem'] is True
    paper = service.search('alpha', filters={'kind': 'paper'})
    assert len(paper['hits']) == 1 and paper['hits'][0]['locator']['page'] == 2
    assert service.search('alpha', filters={'year': 1999})['hits'] == []
    assert service.search('alpha', filters={'doc_id': 'missing'})['status'] == 'ok'
    assert [h['doc_id'] for h in service.search('alpha', filters={'case_id': 'TEST'}, score_threshold=.99)['hits']] == ['doc-0', 'doc-1']


def test_ingestion_is_idempotent_and_rejects_tampering(indexed):
    service, corpus = indexed
    before = service.client.count(service.collection, exact=True).count
    assert ingest(service.client, service.embedder, corpus) == service.collection
    assert service.client.count(service.collection, exact=True).count == before
    changed = copy.deepcopy(corpus)
    changed['chunks'][0]['text'] = 'tampered'
    with pytest.raises(ValueError, match='hash mismatch'):
        ingest(service.client, service.embedder, changed)


def test_wrong_embedding_or_incomplete_index_never_becomes_empty_success(indexed):
    service, _ = indexed
    wrong = SyntheticEmbedder()
    wrong.signature = 'different model with same dimension'
    with pytest.raises(RetrievalUnavailable, match='identity differ'):
        Retriever(service.client, wrong, service.collection, service.corpus_sha256).search('alpha')
    service.client.delete(service.collection, [META_ID], wait=True)
    with pytest.raises(RetrievalUnavailable, match='not ready'): service.search('alpha')


def test_search_api_no_database_and_explicit_empty_results(indexed):
    service, _ = indexed
    def forbidden_db(): raise AssertionError('Search must not open workflow database')
    with TestClient(create_app(forbidden_db, lambda: service)) as client:
        response = client.post('/search', json={'query': 'alpha', 'filters': {'year': 1999}})
        assert response.status_code == 200 and response.json()['hits'] == []
        response = client.post('/search', json={'query': 'alpha', 'filters': {'kind': 'paper'}, 'include_same_problem': True})
        assert response.status_code == 200
        assert client.post('/search', json={'query': 'alpha', 'filters': {'arbitrary': 'x'}}).status_code == 422
        assert client.post('/search', json={'query': '   '}).status_code == 422
        assert client.post('/search', json={'query': 'alpha', 'limit': 1000}).status_code == 422
        assert client.post('/search', json={'query': 'alpha', 'include_same_problem': 'yes'}).status_code == 422


def test_search_api_fault_is_not_empty_evidence():
    def unavailable(): raise RetrievalUnavailable('sensitive local connection details')
    with TestClient(create_app(retrieval_factory=unavailable)) as client:
        response = client.post('/search', json={'query': '板凳龙'})
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'retrieval_unavailable'
        assert 'sensitive' not in response.text and 'hits' not in response.json()


def test_same_problem_ingestion_is_allowed_with_classification(indexed):
    service, corpus = indexed
    changed = copy.deepcopy(corpus)
    changed['chunks'][0]['same_problem_reference'] = True
    changed['corpus_sha256'] = digest({'documents': changed['documents'], 'chunks': changed['chunks']})
    name = ingest(service.client, service.embedder, changed)
    retriever=Retriever(service.client, service.embedder, name, changed['corpus_sha256'])
    assert any(h['same_problem_reference'] for h in retriever.search('alpha')['hits'])
    assert all(h['same_problem_reference'] is False for h in retriever.search('alpha',include_same_problem=False)['hits'])


def test_unclassified_source_rejected_before_reading(tmp_path):
    from modelcrew.corpus import prepare_corpus
    manifest = tmp_path/'sources.json'
    manifest.write_text(json.dumps({'documents':[{'id':'blocked','same_problem_reference':None}]}), encoding='utf-8')
    with pytest.raises(ValueError, match='explicit same-problem classification'):
        prepare_corpus(manifest,tmp_path/'output')


def test_requested_limit_and_unrelated_query_do_not_invent_bibliographic_metadata(indexed):
    service, _ = indexed
    limited = service.search('alpha', limit=1)
    assert len(limited['hits']) == 1
    assert 'doi' not in limited['hits'][0] and 'authors' not in limited['hits'][0]
    assert service.search('beta', filters={'kind': 'paper'}, score_threshold=.99)['hits'] == []
