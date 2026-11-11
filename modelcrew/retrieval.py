"""Local BGE embeddings and versioned Qdrant retrieval, independent of workflow state."""
import argparse
import json
import logging
import os
import uuid
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

from .config import ROOT
from .contracts import digest
from .corpus import sha_file

logger = logging.getLogger(__name__)

META_ID = '00000000-0000-0000-0000-000000000000'
QUERY_PREFIX = '为这个句子生成表示以用于检索相关文章：'


class RetrievalUnavailable(RuntimeError):
    pass


class LocalBge:
    def __init__(self, path, *, device='cpu'):
        self.path = Path(path).resolve()
        if not self.path.is_dir():
            raise RetrievalUnavailable('Local embedding model directory missing')
        # Fingerprint actual weights/configs. Different embeddings never share an index.
        files = sorted(p for p in self.path.rglob('*') if p.is_file() and
                       (p.suffix in ('.json', '.safetensors', '.bin') or p.name == 'vocab.txt'))
        if not any(p.suffix in ('.safetensors', '.bin') for p in files):
            raise RetrievalUnavailable('Local model weights missing')
        self.identity = {'name': 'BAAI/bge-base-zh-v1.5', 'query_prefix': QUERY_PREFIX,
                         'normalize': True, 'max_seq_length': 512,
                         'files': {str(p.relative_to(self.path)): sha_file(p) for p in files}}
        self.signature = digest(self.identity)
        logger.info('Model fingerprint ready; importing PyTorch')
        import torch
        logger.info('PyTorch imported; importing sentence-transformers')
        from sentence_transformers import SentenceTransformer
        logger.info('Embedding libraries imported; loading local weights')
        torch.set_num_threads(4)
        self.model = SentenceTransformer(str(self.path), device=device, local_files_only=True, trust_remote_code=False)
        logger.info('Local embedding weights loaded')
        self.model.max_seq_length = 512
        self.dimension = self.model.get_embedding_dimension()

    def encode(self, texts, *, query=False):
        values = [QUERY_PREFIX + t if query else t for t in texts]
        lengths = [len(self.model.tokenizer.encode(t, add_special_tokens=True)) for t in values]
        if max(lengths, default=0) > self.model.max_seq_length:
            raise ValueError('Embedding input exceeds token limit; split text before indexing')
        vectors = self.model.encode(values, normalize_embeddings=True, batch_size=8, show_progress_bar=False)
        if not np.isfinite(vectors).all():
            raise RetrievalUnavailable('Embedding produced nonfinite values')
        return vectors.tolist()


def ingest(client, embedder, corpus):
    chunks = corpus['chunks']
    if not chunks:
        raise ValueError('Cannot index empty corpus')
    if digest({'documents': corpus['documents'], 'chunks': chunks}) != corpus['corpus_sha256']:
        raise ValueError('Corpus content hash mismatch')
    if any(type(c.get('same_problem_reference')) is not bool for c in chunks):
        raise ValueError('Corpus requires explicit same-problem classification')
    identity = {'corpus_sha256': corpus['corpus_sha256'], 'embedding_signature': embedder.signature,
                'dimension': embedder.dimension, 'chunk_count': len(chunks)}
    collection = 'mc_c2_' + digest(identity)[:24]
    if client.collection_exists(collection):
        meta = client.retrieve(collection, [META_ID])
        if meta and meta[0].payload != {**identity, 'record_type': 'index_ready'}:
            raise RetrievalUnavailable('Existing index identity mismatch')
        if meta:
            if client.count(collection, exact=True).count != len(chunks) + 1:
                raise RetrievalUnavailable('Existing index point count mismatch')
            return collection
    else:
        client.create_collection(collection, vectors_config=models.VectorParams(size=embedder.dimension, distance=models.Distance.COSINE))
    vectors = embedder.encode([chunk['text'] for chunk in chunks])
    points = [models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, c['chunk_id'])), vector=v, payload=c)
              for c, v in zip(chunks, vectors, strict=True)]
    for start in range(0, len(points), 64):
        client.upsert(collection, points[start:start + 64], wait=True)
    if client.count(collection, exact=True).count != len(chunks):
        raise RetrievalUnavailable('Incomplete index; no readiness marker published')
    client.upsert(collection, [models.PointStruct(id=META_ID, vector=[0.] * embedder.dimension,
                  payload={**identity, 'record_type': 'index_ready'})], wait=True)
    return collection


class Retriever:
    def __init__(self, client, embedder, collection, corpus_sha256):
        self.client, self.embedder = client, embedder
        self.collection, self.corpus_sha256 = collection, corpus_sha256

    def search(self, query, *, limit=5, filters=None, score_threshold=0.0, include_same_problem=True):
        if not isinstance(query, str) or not query.strip() or len(query) > 400:
            raise ValueError('Query requires 1 to 400 characters')
        if not 1 <= limit <= 20 or not 0 <= score_threshold <= 1:
            raise ValueError('Invalid retrieval limit or score threshold')
        filters = filters or {}
        if set(filters) - {'doc_id', 'case_id', 'kind', 'year'}:
            raise ValueError('Unsupported retrieval filter')
        try:
            markers = self.client.retrieve(self.collection, [META_ID])
            if not markers:
                raise RetrievalUnavailable('Index not ready')
            meta = markers[0].payload
            if (meta.get('embedding_signature') != self.embedder.signature or
                meta.get('corpus_sha256') != self.corpus_sha256 or meta.get('dimension') != self.embedder.dimension):
                raise RetrievalUnavailable('Query model and index identity differ')
            conditions = [models.FieldCondition(key='record_type', match=models.MatchValue(value='chunk'))]
            conditions += [models.FieldCondition(key=key, match=models.MatchValue(value=value)) for key, value in filters.items()]
            if not include_same_problem:
                conditions.append(models.FieldCondition(key='same_problem_reference', match=models.MatchValue(value=False)))
            vector = self.embedder.encode([query.strip()], query=True)[0]
            hits = self.client.query_points(self.collection, query=vector, limit=limit,
                    query_filter=models.Filter(must=conditions), score_threshold=score_threshold,
                    with_payload=True, with_vectors=False).points
        except (ValueError, RetrievalUnavailable):
            raise
        except Exception as exc:
            raise RetrievalUnavailable('Vector retrieval service unavailable') from exc
        return {'status': 'ok', 'query': query.strip(), 'collection': self.collection,
                'corpus_sha256': self.corpus_sha256, 'embedding_signature': self.embedder.signature,
                'include_same_problem': include_same_problem,
                'hits': [{**hit.payload, 'score': hit.score} for hit in hits]}


def from_config(path=None):
    path = Path(path or os.environ.get('MODELCREW_RETRIEVAL_CONFIG', ROOT/'stage-c/runs/retrieval-index.json'))
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig'))
        embedder = LocalBge(config['model_path'])
        if embedder.signature != config['embedding_signature']:
            raise RetrievalUnavailable('Configured model changed; reindex required')
        client = QdrantClient(url=config['qdrant_url'], timeout=15)
        return Retriever(client, embedder, config['collection'], config['corpus_sha256'])
    except RetrievalUnavailable:
        raise
    except Exception as exc:
        raise RetrievalUnavailable('Retrieval configuration unavailable') from exc


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--manifest', type=Path, default=ROOT/'stage-c/corpus/sources.json')
    prepare.add_argument('--output', type=Path, required=True)
    index = sub.add_parser('index')
    index.add_argument('corpus', type=Path)
    index.add_argument('--model', type=Path, required=True)
    index.add_argument('--url', default='http://127.0.0.1:56333')
    index.add_argument('--config', type=Path, default=ROOT/'stage-c/runs/retrieval-index.json')
    query = sub.add_parser('search')
    query.add_argument('query')
    query.add_argument('--config', type=Path)
    query.add_argument('--independent', action='store_true', help='Exclude classified same-problem sources')
    query.add_argument('--kind', choices=['paper', 'algorithm', 'problem_statement'])
    args = parser.parse_args()
    if args.command == 'prepare':
        from .corpus import prepare_corpus
        result = {'corpus': str(prepare_corpus(args.manifest, args.output))}
    elif args.command == 'index':
        corpus = json.loads(args.corpus.read_text(encoding='utf-8-sig'))
        model = LocalBge(args.model)
        client = QdrantClient(url=args.url, timeout=30)
        try:
            name = ingest(client, model, corpus)
        finally:
            client.close()
        result = {'collection': name, 'qdrant_url': args.url, 'model_path': str(args.model.resolve()),
                  'embedding_signature': model.signature, 'embedding_identity': model.identity,
                  'corpus_sha256': corpus['corpus_sha256'], 'chunk_count': len(corpus['chunks'])}
        # Exclusive creation prevents silently switching an active retrieval configuration.
        with args.config.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    else:
        result = from_config(args.config).search(args.query, filters={'kind': args.kind} if args.kind else {},
                                               include_same_problem=not args.independent)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()


