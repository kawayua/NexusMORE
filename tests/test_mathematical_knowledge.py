"""B1-B3 coverage, real computations, rejection boundaries and limited claims."""
import copy
import hashlib
import json
from collections import Counter

import numpy as np
import pytest
from scipy import stats
from modelcrew import mathematical_knowledge as knowledge
from modelcrew import mathematical_examples as examples
from modelcrew.package_resources import resource


def test_declared_scope_and_group_assignment():
    catalog=knowledge.load_catalog()
    assert catalog['topic_count']==39
    assert [(g['id'],len(g['topic_ids'])) for g in catalog['groups']]==[('B1',12),('B2',13),('B3',14)]
    assert len({t['id'] for t in catalog['topics']})==39
    assert not catalog['limits']['automatic_theorem_proof']
    assert not catalog['limits']['automatic_statistical_design_approval']


def test_all_sections_preserve_formula_premises_proof_counterexample_and_hash():
    for topic in knowledge.load_catalog()['topics']:
        read=knowledge.read_topic(topic['id'])
        assert read['text'].count('<a id=')==1
        for key in ['formula','assumptions','derivation','failure_boundary']:
            assert topic[key] in read['text']
        assert read['source_sha256']==hashlib.sha256(resource(read['source']).read_bytes()).hexdigest()
        assert read['section_sha256']==hashlib.sha256(read['text'].encode()).hexdigest()
        assert '独立' in read['chapter_guidance']
        assert not read['automatic_theorem_proof'] and not read['formal_approval']


def test_all_39_fixed_cases_against_stated_numeric_targets():
    result=knowledge.run_examples()
    assert result['status']=='passed',result['results']
    assert result['cases']==39
    assert result['independent_review']=='NOT_RUN'
    assert not result['statistical_design_verified']


@pytest.mark.parametrize('call',[
    lambda:knowledge.list_topics('B4'),lambda:knowledge.read_topic('unknown'),
    lambda:knowledge.run_examples([]),lambda:knowledge.run_examples(['domains','domains']),
    lambda:knowledge.run_examples(['domains'],'B3'),lambda:knowledge.run_examples(group='B4'),
])
def test_bad_or_mismatched_selection_rejected(call):
    with pytest.raises(ValueError):call()


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),42.0,[1,2]])
def test_nonfinite_wrong_value_or_shape_is_failed_and_json_safe(monkeypatch,bad):
    monkeypatch.setitem(examples.EXAMPLES,'domains',lambda:bad)
    result=knowledge.run_examples(['domains'])
    assert result['status']=='failed'
    json.dumps(result,allow_nan=False)


def test_computation_exception_remains_failure(monkeypatch):
    def broken():raise ArithmeticError('example arithmetic failed')
    monkeypatch.setitem(examples.EXAMPLES,'domains',broken)
    result=knowledge.run_examples(['domains'])
    assert result['status']=='failed' and result['results'][0]['error_type']=='ArithmeticError'


NEGATIVE_BOUNDARIES=[
 ('zero-denominator',lambda:examples.nonzero(0)),
 ('nonfinite-denominator',lambda:examples.nonzero(np.nan)),
 ('nonpositive-log',lambda:examples.log_positive(-1)),
 ('unlike-dimensions',lambda:examples.compatible_sum_units({'L':1},{'T':1})),
 ('wrong-linear-shape',lambda:examples.solve_unique([[1,2]],[1])),
 ('rank-deficient-system',lambda:examples.solve_unique([[1,1],[2,2]],[1,2])),
 ('nonfinite-linear-system',lambda:examples.solve_unique([[np.inf]],[1])),
 ('zero-welch-se',lambda:examples.welch_summary([1,1],[2,2])),
 ('unmatched-pairs',lambda:examples.paired_summary([1,2],[2,3,4])),
 ('zero-paired-se',lambda:examples.paired_summary([1,2],[2,3])),
 ('negative-pvalue',lambda:examples.bh_adjust([-.1,.2])),
 ('missing-pvalue',lambda:examples.bh_adjust([.1,np.nan])),
 ('empty-family',lambda:examples.bonferroni([])),
 ('nonpositive-equivalence-margin',lambda:examples.tost_summary(.1,.1,9,0,.05)),
 ('zero-equivalence-se',lambda:examples.tost_summary(.1,0,9,.5,.05)),
 ('nonfinite-observation',lambda:examples.welch_summary([1,np.nan],[2,3])),
]

@pytest.mark.parametrize('name,call',NEGATIVE_BOUNDARIES,ids=[r[0] for r in NEGATIVE_BOUNDARIES])
def test_executed_failure_boundaries(name,call):
    with pytest.raises(ValueError):call()


def test_symbolic_domains_and_numerical_error_have_independent_oracles():
    assert examples.case_domains()==[3,3,2]
    grad=examples.case_differentiation()
    # Central differences independently check a symbolic gradient at (2,0).
    h=1e-5;f=lambda x,y:x*x*y+np.sin(y)
    assert grad[:2]==pytest.approx([(f(2+h,0)-f(2-h,0))/(2*h),(f(2,h)-f(2,-h))/(2*h)])
    error=examples.case_numerical_error()
    assert error[:2]==pytest.approx([1/(6*10**2),1/(6*20**2)],rel=1e-10)
    assert examples.case_least_squares()[:2]==pytest.approx([1,2])


def test_interval_targets_and_inference_directions_are_consistent():
    delta,t,p,lo,hi,d=examples.case_welch_inference()
    assert delta==-1 and t==pytest.approx(-1/np.sqrt(2/3))
    assert (lo+hi)/2==pytest.approx(delta) and lo<0<hi and p>.05
    paired=examples.case_paired_inference()
    assert paired[2]<.05 and paired[3]>0
    # Equivalence uses TWO one-sided tests and the matching 90%, not 95%, interval.
    r=examples.case_equivalence_inference()
    assert r[-1]==1 and max(r[:2])<.05 and -.5<r[2]<r[3]<.5
    assert examples.tost_summary(0,1,9,.1,.05)[-1]==0
    # Exact paired binomial result is independently derived as 2*(1+10+45)/1024.
    assert examples.case_mcnemar_inference()[0]==pytest.approx(112/1024)
    assert examples.case_rank_inference()[-1]==1 # small samples cannot give finite 95% exact shift CI


def test_bh_mapping_ties_and_monotonicity():
    p=np.array([.2,.01,.04,.03,.01]);adj=examples.bh_adjust(p)
    order=np.argsort(p);assert np.all(np.diff(adj[order])>=-1e-12)
    assert adj[1]==adj[4]
    perm=np.array([4,2,0,1,3]);assert examples.bh_adjust(p[perm])==pytest.approx(adj[perm])
    assert examples.bonferroni([0,.5,1])==pytest.approx([0,1,1])


def test_catalog_tampering_fails_before_reference_read(monkeypatch):
    from modelcrew import package_resources
    original=package_resources.resource
    class Changed:
        def read_bytes(self):return b'changed'
    monkeypatch.setattr(package_resources,'resource',lambda name:Changed() if name==knowledge.CATALOG else original(name))
    with pytest.raises(ValueError,match='identity changed'):knowledge.load_catalog()
