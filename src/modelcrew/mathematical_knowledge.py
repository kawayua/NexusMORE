"""Read versioned B1-B3 references and run trusted, fixed educational checks.

Reading is core-only. Computations require the evidence extra, never evaluate
user expressions and never approve a theorem, statistical design or paper.
"""
import argparse
import hashlib
import json

from .package_resources import resource, verify_resources

CATALOG = 'mathematics/catalog.json'
SCOPES = {'finite_example', 'symbolic_identity_check', 'numerical_error_check', 'statistical_calculation'}


def load_catalog():
    verify_resources()
    value = json.loads(resource(CATALOG).read_text(encoding='utf-8'))
    if value.get('schema_version') != '1.0.0' or value.get('knowledge_version') != '1.0.0':
        raise ValueError('Unsupported mathematical knowledge version')
    groups = {g['id']: g for g in value['groups']}
    topics = {t['id']: t for t in value['topics']}
    if set(groups) != {'B1', 'B2', 'B3'} or len(topics) != len(value['topics']) or len(topics) != value['topic_count']:
        raise ValueError('Mathematical knowledge identity/count differs')
    assigned = []
    for key, group in groups.items():
        assigned.extend(group['topic_ids'])
        for topic_id in group['topic_ids']:
            topic = topics.get(topic_id)
            if not topic or topic['group'] != key or topic['section'] != group['path'] + '#' + topic_id:
                raise ValueError('Mathematical section differs')
            if not all(topic.get(k) for k in ['formula', 'assumptions', 'derivation', 'failure_boundary']):
                raise ValueError('Incomplete mathematical conditions')
            example = topic['example']
            if example['id'] != topic_id or example['scope'] not in SCOPES:
                raise ValueError('Missing example evidence scope')
            if not (0 < example['absolute_tolerance'] < .01 and 0 < example['relative_tolerance'] < .01):
                raise ValueError('Invalid fixed check tolerance')
    if len(assigned) != len(topics) or set(assigned) != set(topics):
        raise ValueError('Duplicate or missing mathematical assignment')
    return value


def list_topics(group=None):
    catalog = load_catalog()
    if group is not None and group not in {g['id'] for g in catalog['groups']}:
        raise ValueError('Unknown mathematical group')
    return [{'id': t['id'], 'group': t['group'], 'title': t['title'], 'case_scope': t['example']['scope']}
            for t in catalog['topics'] if group is None or t['group'] == group]


def read_topic(topic_id):
    catalog = load_catalog()
    topic = next((t for t in catalog['topics'] if t['id'] == topic_id), None)
    if topic is None:
        raise ValueError('Unknown mathematical topic')
    path, anchor = topic['section'].split('#')
    raw = resource(path).read_bytes()
    text = raw.decode('utf-8')
    marker = '<a id="' + anchor + '"></a>'
    if text.count(marker) != 1:
        raise ValueError('Missing/duplicate mathematical section')
    section = marker + text.split(marker, 1)[1].split('<a id="', 1)[0]
    return {'knowledge_version': catalog['knowledge_version'], 'topic': topic, 'source': path,
            'source_sha256': hashlib.sha256(raw).hexdigest(),
            'catalog_sha256': hashlib.sha256(resource(CATALOG).read_bytes()).hexdigest(),
            'section_sha256': hashlib.sha256(section.encode('utf-8')).hexdigest(),
            'chapter_guidance': text.split('<a id="', 1)[0], 'text': section,
            'automatic_theorem_proof': False, 'formal_approval': False, 'independent_review': 'NOT_RUN'}


def run_examples(ids=None, group=None):
    catalog = load_catalog()
    selected = {t['id']: t for t in catalog['topics']}
    if group is not None:
        selected = {t['id']: selected[t['id']] for t in list_topics(group)}
    if ids is not None:
        if not ids or len(ids) != len(set(ids)) or any(key not in selected for key in ids):
            raise ValueError('Unknown, duplicate, empty or mismatched mathematical selection')
        selected = {key: selected[key] for key in ids}
    import numpy as np
    from .mathematical_examples import EXAMPLES
    if set(EXAMPLES) != {t['id'] for t in catalog['topics']}:
        raise ValueError('Fixed code and mathematical topic coverage differs')
    results = []
    for key, topic in selected.items():
        example = topic['example']
        result = {'id': key, 'scope': example['scope']}
        try:
            actual = np.asarray(EXAMPLES[key](), dtype=float)
            expected = np.asarray(example['expected'], dtype=float)
            finite = np.isfinite(actual).all() and np.isfinite(expected).all()
            same_shape = actual.shape == expected.shape
            passed = finite and same_shape and np.allclose(actual, expected,
                        atol=example['absolute_tolerance'], rtol=example['relative_tolerance'])
            result.update(status='passed' if passed else 'failed',
                          actual=actual.tolist() if np.isfinite(actual).all() else None,
                          expected=expected.tolist() if np.isfinite(expected).all() else None,
                          finite=bool(finite), same_shape=same_shape,
                          max_absolute_error=float(np.max(abs(actual-expected))) if finite and same_shape else None,
                          absolute_tolerance=example['absolute_tolerance'], relative_tolerance=example['relative_tolerance'])
        except Exception as exc:
            result.update(status='failed', error=str(exc), error_type=type(exc).__name__)
        results.append(result)
    return {'status': 'passed' if all(r['status'] == 'passed' for r in results) else 'failed',
            'knowledge_version': catalog['knowledge_version'], 'cases': len(results), 'results': results,
            'evidence_scope': 'Fixed inputs only; written proofs, finite checks and inference assumptions remain distinct',
            'automatic_theorem_proof': False, 'statistical_design_verified': False,
            'formal_approval': False, 'independent_review': 'NOT_RUN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('list'); p.add_argument('--group', choices=['B1', 'B2', 'B3'])
    p = sub.add_parser('read'); p.add_argument('--id', required=True)
    p = sub.add_parser('check-examples'); p.add_argument('--id', action='append')
    p.add_argument('--group', choices=['B1', 'B2', 'B3']); p.add_argument('--output')
    args = parser.parse_args()
    try:
        result = list_topics(args.group) if args.command == 'list' else read_topic(args.id) if args.command == 'read' else run_examples(args.id, args.group)
    except ImportError:
        parser.error('Fixed examples require the existing evidence dependency group (NumPy/SciPy/SymPy)')
    except ValueError as exc:
        parser.error(str(exc))
    if getattr(args, 'output', None):
        with open(args.output, 'x', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if isinstance(result, dict) and result.get('status') == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
