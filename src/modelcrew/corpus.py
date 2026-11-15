"""Deterministic, source-located corpus preparation; no model calls."""
from .project_assets import asset_path
import hashlib
import json
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import ROOT
from .contracts import digest

PARSER_VERSION = 'c2-text-1'


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else asset_path(ROOT,p)


def split_text(text, size=360, overlap=60):
    if not 0 <= overlap < size:
        raise ValueError('Require 0 <= overlap < chunk size')
    for start in range(0, len(text), size - overlap):
        end = min(start + size, len(text))
        if text[start:end].strip():
            yield start, end, text[start:end]
        if end == len(text):
            break


def prepare_corpus(manifest_path, output_dir):
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8-sig'))
    documents = manifest['documents']
    if any(type(doc.get('same_problem_reference')) is not bool for doc in documents):
        raise ValueError('Sources require explicit same-problem classification')
    ids = [doc['id'] for doc in documents]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate document IDs')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    chunks, provenance = [], []
    for doc in documents:
        source = dict(doc)
        units = []
        if doc['format'] == 'html':
            response = httpx.get(doc['source_url'], timeout=40, follow_redirects=True)
            response.raise_for_status()
            data = response.content
            path = output / (doc['id'] + '.html')
            path.write_bytes(data)
            soup = BeautifulSoup(data, 'html.parser', from_encoding='utf-8')
            main = soup.select_one('main') or soup.select_one('[role=main]')
            if main is None:
                raise ValueError('HTML has no main content: ' + doc['id'])
            for node in main.select('script,style,nav'):
                node.decompose()
            units = [({'section': 'main', 'label': 'HTML main text'}, main.get_text('\n', strip=True))]
            source.update(path=str(path.resolve()), resolved_url=str(response.url), source_sha256=sha_file(path))
        else:
            path = resolve(doc['path'])
            source['source_sha256'] = sha_file(path)
            if doc['format'] == 'pdf':
                reader = PdfReader(path)
                for page in doc['pages']:
                    text = reader.pages[page - 1].extract_text()
                    if not text or text.count('\ufffd') > max(3, len(text) // 100):
                        raise ValueError('PDF extraction needs manual review: ' + doc['id'])
                    units.append(({'page': page, 'label': 'PDF text layer'}, text))
            elif doc['format'] == 'manual_excerpt':
                excerpts = json.loads(path.read_text(encoding='utf-8-sig'))['excerpts']
                for number, excerpt in enumerate(excerpts, 1):
                    image = resolve(excerpt['image_path'])
                    units.append(({'page': excerpt['page'], 'excerpt': number, 'label': excerpt['label'],
                                   'image_path': excerpt['image_path'], 'image_sha256': sha_file(image)}, excerpt['text']))
            else:
                raise ValueError('Unsupported parser')
        source['parser'] = PARSER_VERSION + ':' + doc['format']
        source['units'] = []
        for location, text in units:
            source['units'].append({'location': location, 'text_sha256': digest(text), 'characters': len(text)})
            for start, end, value in split_text(text):
                locator = {**location, 'char_start': start, 'char_end': end}
                chunk_id = digest({'document': doc['id'], 'source': source['source_sha256'], 'locator': locator, 'text': value})
                chunks.append({
                    'record_type': 'chunk', 'doc_id': doc['id'], 'chunk_id': chunk_id, 'text': value,
                    'title': doc['title'], 'kind': doc['kind'], 'year': doc['year'], 'case_id': doc['case_id'],
                    'same_problem_reference': doc['same_problem_reference'], 'source_url': doc.get('source_url'),
                    'index_url': doc.get('index_url'), 'source_note': doc['source_note'], 'usage': doc['usage'],
                    'source_sha256': source['source_sha256'], 'parser': source['parser'], 'locator': locator})
        provenance.append(source)
    corpus = {'schema_version': '1.0.0', 'parser_version': PARSER_VERSION, 'documents': provenance, 'chunks': chunks}
    corpus['corpus_sha256'] = digest({'documents': provenance, 'chunks': chunks})
    target = output / 'corpus.json'
    target.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding='utf-8')
    return target
