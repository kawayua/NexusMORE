import copy,json
import pytest
from modelcrew.contracts import ROOT,validate,bench_review,ContractError
EX=ROOT/'contracts/examples'
def load(name):return json.loads((EX/name).read_text(encoding='utf-8'))
def test_valid_contract_does_not_claim_math_approval():
    assert validate(load('valid-2024-a-q1.json'))
    assert bench_review(load('valid-2024-a-q1.json'))['status']=='unknown'
@pytest.mark.parametrize('name',['invalid-missing-checks.json','invalid-shape.json','invalid-reference.json'])
def test_invalid_contracts(name):
    with pytest.raises(ContractError):validate(load(name))
def test_schema_valid_math_wrong_is_distinct():
    c=load('schema-valid-math-wrong.json');validate(c)
    assert bench_review(c)['status']=='failed'
def test_duplicate_check_id_is_rejected():
    c=load('valid-2024-a-q1.json');c['checks'].append(copy.deepcopy(c['checks'][0]))
    with pytest.raises(ContractError):validate(c)
def test_nonfinite_rejected():
    c=load('valid-2024-a-q1.json');c['parameters'][0]['value']=float('nan')
    with pytest.raises(ValueError):validate(c)


def test_new_input_schema_examples():
    c=load('valid-2024-a-q1-input-1.1.json');validate(c)
    assert c['schema_version']=='1.1.0'
    with pytest.raises(ContractError):validate(load('invalid-input-structure-1.1.json'))
