"""Knowledge coverage, real numerical oracles and explicit rejection boundaries."""
import copy
import hashlib
import json
from pathlib import Path
from collections import Counter

import numpy as np
import pytest
from scipy.sparse.csgraph import NegativeCycleError
from modelcrew import algorithm_knowledge as knowledge
from modelcrew import algorithm_examples as examples
from modelcrew.package_resources import resource


def test_catalog_covers_all_source_methods_and_deduplicates_cross_categories():
    catalog=knowledge.load_catalog()
    review=json.loads((Path(__file__).resolve().parents[1]/'docs/release/algorithm-reference-review-20261114.json').read_text(encoding='utf-8'))
    assert len(catalog['algorithms'])==113
    assert len(catalog['source_coverage'])==123
    assert [len(x['algorithm_ids']) for x in catalog['categories']]==[17,15,14,15,21,13,28]
    assert Counter(x['example']['scope'] for x in catalog['algorithms'])=={'small_complete_solution':65,'single_update':23,'core_equation_check':24,'stochastic_estimate':1}
    for category,source in zip(catalog['categories'],review['categories']):
        actual=[r for r in catalog['source_coverage'] if r['category']==category['id']]
        assert len(actual)==len(source['methods'])
    assert next(a for a in catalog['algorithms'] if a['id']=='linear-regression')['categories']==['prediction','statistics','machine-learning']
    assert not catalog['limits']['general_business_solvers_registered']


def test_every_section_reads_only_requested_algorithm_and_preserves_evidence():
    catalog=knowledge.load_catalog()
    for category in catalog['categories']:
        for algorithm in category['algorithm_ids']:
            read=knowledge.read_algorithm(algorithm,category['id'])
            assert read['text'].count('<a id=')==1
            assert read['algorithm']['formula'] in read['text']
            assert read['algorithm']['counterexample'] in read['text']
            assert read['source_sha256']==hashlib.sha256(resource(read['source']).read_bytes()).hexdigest()
            assert not read['formal_approval']
            assert not read['general_business_solver_registered']


@pytest.mark.parametrize('call',[
    lambda:knowledge.list_algorithms('unknown'),
    lambda:knowledge.read_algorithm('unknown'),
    lambda:knowledge.read_algorithm('lp','prediction'),
    lambda:knowledge.run_examples([]),
    lambda:knowledge.run_examples(['lp','lp']),
    lambda:knowledge.run_examples(['lp'],'prediction'),
])
def test_unknown_mismatched_or_ambiguous_selection_rejected(call):
    with pytest.raises(ValueError):call()


def test_all_fixed_numerical_cases_match_declared_oracles():
    result=knowledge.run_examples()
    assert result['cases']==113
    assert result['status']=='passed', [r for r in result['results'] if r['status']!='passed']
    assert result['independent_review']=='NOT_RUN'
    assert not result['general_business_solvers_registered']


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),42.0,[1.0,2.0]])
def test_failed_or_nonfinite_or_shape_mismatch_never_passes(monkeypatch,bad):
    monkeypatch.setitem(examples.EXAMPLES,'lp',lambda:bad)
    result=knowledge.run_examples(['lp'])
    assert result['status']=='failed'


def test_stochastic_case_repeats_but_is_not_a_confidence_guarantee():
    a=examples.case_monte_carlo();b=examples.case_monte_carlo()
    assert a==b
    assert abs(a-.5)<.006
    assert knowledge.run_examples(['monte-carlo'])['results'][0]['scope']=='stochastic_estimate'


def test_closed_form_constraints_and_optima_independent_of_fixture_expected_values():
    x,y,obj=examples.case_lp()
    assert 0<=x<=1 and 0<=y<=1 and x+y<=2+1e-12
    assert obj==pytest.approx(x+2*y)
    assert obj==3 # x<=1 and y<=1 give matching feasible upper bound
    # For each feasible integer x, continuous y is chosen minimally for x+y>=2.5.
    candidates=[x+.2*max(0,2.5-x) for x in range(4) if max(0,2.5-x)<=2]
    assert examples.case_milp()==pytest.approx(min(candidates))
    q=np.asarray(examples.case_qp());assert np.allclose(2*q-[2,4],0)
    assert examples.case_ode()==pytest.approx(np.exp(-1),rel=1e-8)
    assert examples.case_ttest()[0] == pytest.approx(-1/np.sqrt(2/3))
    assert examples.case_tsne()==pytest.approx((2/3)*np.log(.8)+(1/3)*np.log(2))


# These are the actual executed negative boundaries, not all 113 textual counterexamples.
NEGATIVE_BOUNDARIES=[
 ('constant-minmax',lambda:examples.scale_minmax([2],2,2),ValueError),
 ('nonfinite-minmax',lambda:examples.scale_minmax([np.nan],0,1),ValueError),
 ('zero-entropy-mass',lambda:examples.entropy_weights([[0,1],[0,2]]),ValueError),
 ('constant-entropy',lambda:examples.entropy_weights([[1,1],[1,1]]),ValueError),
 ('negative-entropy',lambda:examples.entropy_weights([[1,-1],[2,1]]),ValueError),
 ('unstable-mm1',lambda:examples.mm1(3,3),ValueError),
 ('negative-arrival',lambda:examples.mm1(-1,3),ValueError),
 ('invalid-markov-sum',lambda:examples.markov_step([1,0],[[.5,.6],[.2,.8]]),ValueError),
 ('invalid-markov-negative',lambda:examples.markov_step([1,0],[[1.2,-.2],[.2,.8]]),ValueError),
 ('invalid-markov-shape',lambda:examples.markov_step([1,0],[[1.0]]),ValueError),
 ('negative-dijkstra',lambda:examples.shortest([[0,-1],[0,0]],'D'),ValueError),
 ('reachable-negative-cycle',lambda:examples.shortest([[0,1,0],[0,0,-3],[0,1,0]],'BF'),NegativeCycleError),
 ('disconnected-prim',lambda:examples.prim_weight([[0,0],[0,0]]),ValueError),
 ('directed-prim',lambda:examples.prim_weight([[0,1],[0,0]]),ValueError),
 ('duplicate-lof',lambda:examples.lof_1d([0,0,0],1),ValueError),
 ('out-of-range-lof-k',lambda:examples.lof_1d([0,1],2),ValueError),
 ('zero-dbscan-eps',lambda:examples.dbscan_1d([0,1],0,1),ValueError),
 ('zero-dbscan-min-samples',lambda:examples.dbscan_1d([0,1],1,0),ValueError),
 ('unordered-events',lambda:examples.fcfs_wait([1,0],[1,1]),ValueError),
 ('negative-service',lambda:examples.fcfs_wait([0],[-1]),ValueError),
]

@pytest.mark.parametrize('name,call,error',NEGATIVE_BOUNDARIES,ids=[r[0] for r in NEGATIVE_BOUNDARIES])
def test_numerical_failure_boundaries(name,call,error):
    with pytest.raises(error):call()


def test_reference_integrity_rejects_changed_catalog(monkeypatch):
    original=knowledge.resource
    class Changed:
        def read_bytes(self):return b'changed'
        def read_text(self,**kwargs):return '{}'
    # The shared manifest is verified before any topic content is read.
    from modelcrew import package_resources
    monkeypatch.setattr(package_resources,'resource',lambda name: Changed() if name==knowledge.CATALOG else original(name))
    with pytest.raises(ValueError):knowledge.load_catalog()
