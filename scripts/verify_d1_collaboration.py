"""Reproducible D1 contract demo. All call identities/reviews are synthetic.

Reads real algorithm source sections; does not invoke an LLM, solver, or approve
any model/result/manuscript. Runtime primary agents start in D2 and later.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.collaboration import (Artifact, Binding, Call, Check, CollaborationStore,
    Evidence, Handoff, Issue, Receipt, Snapshot, Ticket, collaboration_policy, sha_file)
from modelcrew.collaboration_retrieval import algorithm_context


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def verify(folder):
    folder = folder.resolve()
    if not folder.is_relative_to(ROOT):
        raise ValueError('Output must be inside workspace')
    folder.mkdir(parents=True, exist_ok=False)
    store = CollaborationStore(folder / 'records')
    checks = []
    def check(name, passed):
        checks.append({'id': name, 'passed': bool(passed)})
        if not passed:
            raise AssertionError(name)
    def reject(name, action):
        try:
            action()
        except (ValueError, FileNotFoundError) as exc:
            checks.append({'id': name, 'passed': True, 'error_type': type(exc).__name__, 'reason': str(exc)})
        else:
            raise AssertionError('Expected rejection: ' + name)

    policy = collaboration_policy(); write(folder / 'policy-snapshot.json', policy)
    check('exactly_three_primary_hands', len(policy['policy']['primary_agents']) == 3)
    references = algorithm_context('geometry', card_ids=['bracketed-root'],
        facts={'scalar_equation': True, 'continuous_on_bracket': True, 'opposite_endpoint_signs': True},
        available_dependencies=['scipy'], variable_count=1)
    write(folder / 'algorithm-context.json', references)
    check('index_then_actual_source_sections', references['status'] == 'ok' and bool(references['cards'][0]['source_sections']))
    check('unknown_premises_retained', algorithm_context('geometry', card_ids=['bracketed-root'])['cards'][0]['applicability']['status'] == 'needs_review')
    check('failed_premise_excluded', algorithm_context('geometry', card_ids=['bracketed-root'], facts={'continuous_on_bracket': False})['status'] == 'no_applicable_cards')
    coverage = {category: algorithm_context(category)['status'] for category in
                ['optimization', 'prediction', 'evaluation', 'graph', 'statistics', 'simulation', 'machine-learning', 'geometry']}
    write(folder / 'category-coverage.json', coverage)
    check('installed_prediction_category_available', coverage['prediction'] == 'ok')

    binding = Binding(task_id='d1-synthetic-contract-demo', contract_version=1, contract_sha256=digest({'fixture': True}))
    for role in ['modeling', 'coding', 'writing', 'quality']:
        store.register_call(Call(call_id='fixture-'+role, context_id='fixture-context-'+role, role=role, binding=binding))
    def artifact(kind, role, data):
        path = folder / (kind+'.json'); write(path, data)
        return Artifact(artifact_id=kind, kind=kind, path=path.relative_to(ROOT).as_posix(),
                        sha256=sha_file(path), author_call_ids=['fixture-'+role])
    artifacts = [artifact('contract', 'modeling', {'fixture': True}),
                 artifact('mathematics', 'modeling', {'fixture': 'not a mathematical review'}),
                 artifact('input', 'modeling', {'fixture': True})]
    source = folder / 'algorithm-context.json'
    artifacts.append(Artifact(artifact_id='algorithm-reference', kind='source', path=source.relative_to(ROOT).as_posix(),
                              sha256=sha_file(source), author_call_ids=['fixture-modeling']))
    snapshot = Snapshot(binding=binding, hand='modeling', artifacts=artifacts, lineage_call_ids=['fixture-modeling'])
    key = store.freeze(snapshot)
    handoff = store.handoff(key, 'coding', ['contract', 'input', 'algorithm-reference'])
    context = store.context(handoff, 'fixture-coding'); write(folder / 'coding-context.json', context)
    check('minimum_explicit_handoff', {a['artifact_id'] for a in context['artifacts']} == {'contract', 'input', 'algorithm-reference'})
    ticket_key = store.dispatch_review(key, 'M1', 'fixture-quality')
    ticket = store.load(Ticket, ticket_key)
    receipt = Receipt(ticket_sha256=ticket_key, reviewer_call_id='fixture-quality', status='PASS',
        checks=[Check(check_id=c, status='PASS', explanation='Synthetic admission fixture, not semantic validation',
            evidence=[Evidence(artifact_id='contract', selector='/fixture')]) for c in ticket.required_checks])
    receipt_key = store.accept_review(receipt, key)
    check('complete_fixture_receipt_admitted', store.load(Receipt, receipt_key) == receipt)
    restart = CollaborationStore(folder / 'records')
    check('immutable_store_restart', restart.accept_review(receipt, key) == receipt_key)
    store.register_call(Call(call_id='fixture-self-review', context_id='fixture-context-modeling', role='quality', binding=binding))
    reject('same_context_new_identity_rejected', lambda: store.dispatch_review(key, 'M1', 'fixture-self-review'))
    reject('author_role_rejected', lambda: store.dispatch_review(key, 'M1', 'fixture-modeling'))
    reject('incomplete_receipt_rejected', lambda: store.accept_review(receipt.model_copy(update={'checks': receipt.checks[:-1]}), key))
    reject('stale_snapshot_rejected', lambda: store.accept_review(receipt, 'f'*64))
    failure = receipt.model_copy(update={'status': 'FAIL', 'checks': [receipt.checks[0].model_copy(update={'status': 'FAIL'}), *receipt.checks[1:]],
        'issues': [Issue(check_id=ticket.required_checks[0], severity='error', domain='model', target='modeling',
                         reason='Synthetic failure to verify routing', recheck='M1 after modeling revision')]})
    failed_key = store.accept_review(failure, key)
    check('failure_rework_target_saved', store.load(Receipt, failed_key).issues[0].target == 'modeling')
    (folder / 'contract.json').write_text('{"fixture":"changed"}', encoding='utf-8')
    reject('changed_artifact_rejected', lambda: store.accept_review(receipt, key))
    # Preserve original fixture bytes so archived snapshots remain independently re-readable.
    write(folder / 'contract.json', {'fixture': True})
    check('artifact_original_bytes_restored', store.validate_snapshot(store.load(Snapshot, key)) == snapshot)
    manifest = {p.relative_to(folder).as_posix(): sha_file(p) for p in folder.rglob('*') if p.is_file()}
    report = {'stage': 'D1', 'status': 'passed', 'timestamp': datetime.now(timezone.utc).isoformat(),
              'checks': checks, 'files': manifest, 'fixture_call_identities_and_reviews': True,
              'new_llm_calls': 0, 'new_solver_runs': 0, 'user_approvals_created': 0,
              'limits': 'Contract admission and provenance checks only; no runtime three-hand nodes or independent semantic review executed.'}
    write(folder / 'verification.json', report)
    print(json.dumps({'status': report['status'], 'checks_passed': len(checks), 'output': str(folder)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args().output)
