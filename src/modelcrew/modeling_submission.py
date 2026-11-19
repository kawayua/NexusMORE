"""Bounded, provenance-preserving prepared proposals; no approval or review bypass."""
from pathlib import Path
import json
from pydantic import Field
from .collaboration import Record, Text
from .business_artifacts import read_verified
from .business_contract import BusinessContractError
from .contracts import digest

LIMIT = 2 * 1024 * 1024


class ProposalFile(Record):
    path: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def prepare(w, task, version, files, *, root):
    """Read exact file bytes, validate current binding and native source decisions."""
    from .modeling_hand import Plan, Proposal, graph_check, validate_decisions
    from .algorithm_lookup import builtin_context
    from .mathematics import latest
    from .modeling_proposal import validate_document
    ref = ProposalFile.model_validate(files)
    raw, size = read_verified(root, ref.path, ref.sha256, limit=LIMIT)
    if not 0 < size <= LIMIT:
        raise BusinessContractError('invalid_request', 'Prepared proposal exceeds 2 MiB')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate prepared proposal JSON key')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON constant')
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=reject)
        if not isinstance(value, dict) or set(value) != {'binding', 'plan', 'proposal', 'authorship'}:
            raise ValueError('Expected binding, plan, proposal and authorship')
        binding = value['binding']
        current = w.task(task)
        contract = w.db.execute('SELECT sha256,content FROM mc_contracts WHERE task_id=%s AND version=%s',
                               (task, version)).fetchone()
        math = latest(w, task, version)
        expected = {'task_id': task, 'version': version, 'contract_sha256': contract['sha256'] if contract else None,
                    'math_package_sha256': digest(math['content']) if math else None}
        if current['current_version'] != version or binding != expected:
            raise BusinessContractError('stale_binding', 'Prepared proposal no longer matches current model and mathematics')
        if current['model_approved'] or current['phase'] != 'WAITING_MODEL_APPROVAL':
            raise BusinessContractError('workflow_conflict', 'Prepared proposals require an unapproved current model')
        author = value['authorship']
        if not isinstance(author, dict) or set(author) != {'kind', 'statement'} or author['kind'] != 'prepared_file' or not isinstance(author['statement'], str) or not 1 <= len(author['statement']) <= 4000:
            raise ValueError('Prepared file requires explicit authorship provenance')
        plan = Plan.model_validate(value['plan']); graph_check(plan.task_graph)
        references = builtin_context(plan.category, facts=plan.facts, card_ids=plan.card_ids or None)
        proposal = Proposal.model_validate(value['proposal'])
        if proposal.edits:
            raise ValueError('Prepared proposal may not mutate model baselines; revise them explicitly first')
        validate_decisions(proposal, references)
        validate_document(proposal.review_document, contract['content'], references)
    except BusinessContractError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise BusinessContractError('invalid_request', 'Invalid prepared proposal: ' + str(exc)[:1500]) from exc
    return {'file': ref.model_dump(mode='json'), 'content': value, 'plan': plan, 'proposal': proposal,
            'references': references, 'raw': raw}
