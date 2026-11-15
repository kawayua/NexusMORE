"""Installed, bounded literal algorithm lookup. No embeddings, solver or approval."""
import re
from .algorithm_retrieval import AlgorithmRequest, assess
from .algorithm_knowledge import load_catalog
from .contracts import digest
from .package_resources import resource
from .resource_routing import installed_algorithm_context, GEOMETRY_CARDS


def builtin_context(category, *, facts=None, card_ids=None, available_dependencies=None, variable_count=None):
    request = AlgorithmRequest(query='Installed explicit category/card selection', category=category,
        facts=facts if facts is not None else {}, available_dependencies=available_dependencies, variable_count=variable_count)
    if card_ids is not None and (not isinstance(card_ids,list) or not card_ids or
            any(not isinstance(i,str) for i in card_ids) or len(card_ids)!=len(set(card_ids))):
        raise ValueError('Nonempty unique algorithm IDs required')
    result = installed_algorithm_context(category, facts=request.facts, card_ids=card_ids)
    originals = {c['id']:c for c in load_catalog()['algorithms']}
    kept = []
    for item in result['cards']:
        card = item['card']; key=card['id']
        if key in originals:
            original=originals[key]
            card.update(layer=original['layer'], required_facts=original.get('required_facts',{}),
                        example_dependencies=original.get('example_dependencies',[]))
            # Explicit contradictions of known premises must also reject older fact spellings.
            known={'lp':{'linear_objective_constraints':True,'continuous_variables':True,'integer_variables':False},
                   'ode':{'known_rhs':True,'initial_state_available':True}}
            card['required_facts']={**card['required_facts'],**known.get(key,{})}
        else:
            card['layer']={'geometry-model':'model','bracketed-root':'numerical_algorithm','brentq-api':'api'}[key]
        assessment=assess(card,request)
        if assessment['status']=='excluded':
            result['excluded'].append({'card_id':key,**assessment});continue
        # A user-declared flag does not discharge natural-language mathematical premises.
        if key in originals:
            assessment['status']='needs_review'
            assessment['natural_language_conditions']=originals[key]['conditions']
            assessment['scale_status']='unbounded_not_certified'
            assessment['dependency_status']='reference_reading_only; example dependencies do not register business tools'
        item['applicability']=assessment
        item['card_sha256']=digest(card)
        item['citation_id']='algorithm:'+key+':'+item['card_sha256'][:12]
        for source in item['source_sections']:
            relative=source['path'].removeprefix('resources/')
            whole=resource(relative).read_bytes().decode('utf-8');text=source['text']
            if whole.count(text)!=1:raise ValueError('Missing/ambiguous installed algorithm source section')
            start=whole.index(text)
            source['line_start']=whole[:start].count('\n')+1
            source['line_end']=source['line_start']+len(text.splitlines())-1
        kept.append(item)
    result['cards']=kept
    result['status']='ok' if kept else 'no_applicable_cards'
    result['index']['read_sha256']=result['index']['sha256']
    result['request_constraints']={'variable_count':variable_count,'available_dependencies':available_dependencies,
        'scope':'Caller declarations; no business solver registration or reviewed scale promise inferred'}
    return result


def _normalize(text):
    return ' '.join(re.findall(r'[a-z0-9]+|[\u3400-\u9fff]+',text.casefold()))


def _match(query, card):
    q=_normalize(query); raw=query.casefold()
    identifiers=[card['id'],*card.get('aliases',[])]
    if any(re.search(r'(?<![a-z0-9-])'+re.escape(k.casefold())+r'(?![a-z0-9-])',raw) for k in identifiers):
        return 100,'exact_id_or_alias'
    if card['name'] in query:return 80,'literal_chinese_name'
    english=card.get('english_name','').split('(')[0].strip()
    if english and _normalize(english) in q:return 70,'literal_english_name'
    return 0,None


class BuiltinAlgorithmSearch:
    """Shared MCP backend; scores are literal match weights, never semantic probabilities."""
    client=None

    def search(self, request):
        request=AlgorithmRequest.model_validate(request)
        try:return self._search(request)
        except (ValueError,OSError) as exc:
            from .retrieval import RetrievalUnavailable
            raise RetrievalUnavailable('Installed algorithm resources unavailable; no legacy fallback') from exc

    def _search(self, request):
        resource('algorithms/index.md').read_text(encoding='utf-8')  # Index precedes catalog/section selection.
        catalog=load_catalog()
        candidates=[]
        for card in catalog['algorithms']:
            category=request.category or card['categories'][0]
            if category not in card['categories']:continue
            candidates.append((card,category))
        if request.category in (None,'geometry'):
            for key,(title,premises) in GEOMETRY_CARDS.items():
                candidates.append(({'id':key,'name':title,'categories':['geometry'],
                    'layer':{'geometry-model':'model','bracketed-root':'numerical_algorithm','brentq-api':'api'}[key]},'geometry'))
        category_names={c['id']:c['title'] for c in catalog['categories']}
        category_names['geometry']='几何'
        selected=[]
        for card,category in candidates:
            weight,basis=_match(request.query,card)
            # Category-only requests explicitly browse the category, without inventing relevance.
            if not weight and request.category and _normalize(request.query) in {
                    _normalize(request.category),_normalize(category_names[request.category])}:
                weight,basis=1,'explicit_category_browse'
            if weight:selected.append((-weight,card['id'],category,basis,card))
        selected.sort(key=lambda x:(x[0],x[1]))
        hits=[];excluded=[];index=None
        for negative_weight,key,category,basis,original in selected:
            if request.layer and request.layer!=original.get('layer'):
                excluded.append({'id':key,'status':'excluded','reasons':['layer_filter_mismatch']});continue
            if request.verification:
                # Old reviewed-baseline labels belong to the old catalog, not this edition.
                excluded.append({'id':key,'status':'excluded','reasons':['legacy_verification_label_not_certified_for_installed_edition']});continue
            context=builtin_context(category,card_ids=[key],facts=request.facts,
                available_dependencies=request.available_dependencies,variable_count=request.variable_count)
            index=context['index']
            if not context['cards']:
                excluded.extend({'id':e['card_id'],**e} for e in context['excluded']);continue
            item=context['cards'][0];sections=item['source_sections'];text='\n\n'.join(s['text'] for s in sections)
            hit={'doc_id':key,'chunk_id':digest({'card':item['card'],'sources':[s['section_sha256'] for s in sections]}),
                'title':item['card']['title'],'text':text,'source_url':None,
                'source_sha256':digest([s['sha256'] for s in sections]),'parser':'installed-algorithm-section-1',
                'locator':{'sections':[{k:s[k] for k in ('path','line_start','line_end','section_sha256')} for s in sections]},
                'score':float(-negative_weight),'score_kind':'literal_match_weight_not_semantic_probability',
                'selection_basis':basis,'same_problem_reference':False,'card':item['card'],
                'applicability':item['applicability'],'source_sections':sections,
                'reference_kind':'builtin_project_reference','origin':'builtin_project_reference','modeler_generated':False,
                'formal_approval':False,'general_business_solver_registered':False}
            hits.append(hit)
            if len(hits)>=request.limit:break
        # Even empty results record the installed index read, never a fallback catalog.
        if index is None:
            from hashlib import sha256
            raw=resource('algorithms/index.md').read_bytes()
            index={'path':'resources/algorithms/index.md','sha256':sha256(raw).hexdigest(),'read_first':True}
        from hashlib import sha256
        return {'status':'ok','query':request.query,'include_same_problem':True,'hits':hits,
            'provider':'builtin_algorithm_literal_lookup','corpus_sha256':sha256(resource('algorithms/knowledge/catalog.json').read_bytes()).hexdigest(),
            'index_read':index,'excluded':excluded,
            'interpretation':'Installed canonical references and project geometry supplement. Exact ID/name/category matching only; no vector semantic retrieval. Empty matches remain empty; declared premises are not proof; no solver or approval granted.'}
