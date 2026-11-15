"""Installed algorithm references by default; explicit legacy catalogs retain strict guards."""
from .project_assets import asset_path
import json
from pathlib import Path

from .algorithm_retrieval import AlgorithmRequest, assess, verify_sources
from .config import ROOT
from .retrieval_paths import algorithm_catalog_path
from .contracts import digest
from .collaboration import sha_file

CATEGORIES = {'optimization', 'prediction', 'evaluation', 'graph', 'statistics',
              'simulation', 'machine-learning', 'geometry'}


def legacy_algorithm_context(category, *, facts=None, card_ids=None, available_dependencies=None,
                      variable_count=None, catalog_path=None):
    if category not in CATEGORIES:
        raise ValueError('Unknown algorithm category')
    index_path = asset_path(ROOT,'resources/algorithms/index.md')
    index_text = index_path.read_text(encoding='utf-8-sig')  # always read before catalog sections
    catalog_path = algorithm_catalog_path(ROOT,catalog_path)
    if not catalog_path.is_relative_to(ROOT):
        raise ValueError('Catalog must be within workspace')
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    verify_sources(catalog)
    profiles_path = asset_path(ROOT,'resources/algorithms/hand-card-profiles-1.0.0.json')
    profile_set = json.loads(profiles_path.read_text(encoding='utf-8'))
    profiles = {p['card_id']: p for p in profile_set['profiles']}
    if profile_set['catalog_sha256'] != catalog['catalog_sha256'] or len(profiles) != len(profile_set['profiles']):
        raise ValueError('Card profile catalog binding mismatch')
    selected = [c for c in catalog['cards'] if c['category'] == category]
    if card_ids is not None:
        if not card_ids or len(card_ids) != len(set(card_ids)) or not set(card_ids) <= {c['id'] for c in selected}:
            raise ValueError('Unknown, empty or duplicate card selection')
        selected = [c for c in selected if c['id'] in card_ids]
    # Category filtering above permits an explicit uncovered response for all seven navigation categories.
    request = AlgorithmRequest(query='D1 explicit category/card selection', facts=facts or {},
                               available_dependencies=available_dependencies, variable_count=variable_count)
    sources = {s['id']: s for s in catalog['sources']}
    cards = []; excluded = []
    for card in selected:
        profile = profiles.get(card['id'])
        if not profile or profile['base_card_sha256'] != digest(card):
            raise ValueError('Card profile missing or stale')
        applicability = assess(card, request)
        if applicability['status'] == 'excluded':
            excluded.append({'card_id': card['id'], **applicability})
            continue
        sections = [sources[s] for s in card['source_ids']]
        # Actual per-request reads, using the verified source's declared range.
        for source in sections:
            lines = (asset_path(ROOT,source['path'])).read_text(encoding='utf-8-sig').splitlines()
            excerpt = '\n'.join(lines[source['line_start'] - 1:source['line_end']]) + '\n'
            if excerpt != source['text']:
                raise ValueError('Source changed during context assembly')
        cards.append({'card': card, 'card_sha256': digest(card), 'profile': profile,
                      'profile_sha256': digest(profile), 'applicability': applicability,
                      'source_sections': sections, 'origin': 'external_reference',
                      'citation_id': 'algorithm:' + card['id'] + ':' + digest(card)[:12],
                      'adoption': 'pending_modeling_hand_decision'})
    return {'status': 'uncovered' if not selected else ('no_applicable_cards' if not cards else 'ok'),
            'selection_mode': 'explicit_category_and_card_ids_not_semantic_ranking',
            'category': category, 'index': {**catalog['index'], 'read_sha256': sha_file(index_path), 'text': index_text},
            'catalog_path': str(catalog_path.relative_to(ROOT)), 'catalog_sha256': catalog['catalog_sha256'],
            'profiles_path': str(profiles_path.relative_to(ROOT)), 'profiles_sha256': sha_file(profiles_path),
            'cards': cards, 'excluded': excluded,
            'limits': 'Premises are caller declarations; unknown conditions require review. Source excerpts are not executed code or an approved model.'}


def algorithm_context(category, *, facts=None, card_ids=None, available_dependencies=None,
                      variable_count=None, catalog_path=None):
    """Default to installed knowledge; an explicit old catalog stays fail-closed."""
    if catalog_path is not None:
        return legacy_algorithm_context(category, facts=facts, card_ids=card_ids,
            available_dependencies=available_dependencies, variable_count=variable_count, catalog_path=catalog_path)
    from .algorithm_lookup import builtin_context
    return builtin_context(category, facts=facts, card_ids=card_ids,
        available_dependencies=available_dependencies, variable_count=variable_count)
