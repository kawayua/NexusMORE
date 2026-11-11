import copy,json
import pytest
from jsonschema import Draft202012Validator
from modelcrew.config import ROOT
from modelcrew.contracts import digest,validate
from modelcrew.mathematics import validate_package,classify_change,render,semantic_hash,MathematicsError

@pytest.fixture
def contract():return json.loads((ROOT/'stage-b-plus/examples/contract-v2-snapshot.json').read_text(encoding='utf-8'))
@pytest.fixture
def package():return json.loads((ROOT/'stage-b-plus/examples/valid-bench-dragon.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('name',['bench-dragon','resource'])
def test_valid_formal_examples(contract,name):
    p=json.loads((ROOT/f'stage-b-plus/examples/valid-{name}.json').read_text(encoding='utf-8'))
    if name=='resource':contract=json.loads((ROOT/'stage-b-plus/examples/resource-contract.json').read_text(encoding='utf-8'))
    validate(contract)
    assert validate_package(p,contract)==p
    for key,stem in [('method_selection','method-selection'),('dossier','mathematical-dossier')]:
        schema=json.loads((ROOT/f'contracts/{stem}-1.0.0.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(p[key])

@pytest.mark.parametrize('name',['symbol','dimension','proof-premise','contract-link'])
def test_invalid_examples(contract,name):
    p=json.loads((ROOT/f'stage-b-plus/examples/invalid-{name}.json').read_text(encoding='utf-8'))
    with pytest.raises(MathematicsError):validate_package(p,contract)

@pytest.mark.parametrize('mutation',[
    lambda p:p['dossier']['symbols'][0].update(domain='different domain'),
    lambda p:p['dossier']['symbols'][0].update(latex='renamed'),
    lambda p:p['dossier']['assumptions'][0].update(statement='new assumption'),
    lambda p:p['dossier']['equations'][0].update(latex='1=2'),
    lambda p:p['method_selection'].update(solver='different solver'),
    lambda p:p['validation_plan'][0].update(threshold=1e-5),
    lambda p:p['figures'][0].update(specification='different aggregation'),
    lambda p:p['dossier']['propositions'][0]['steps'].append('additional mathematical assertion'),
])
def test_semantic_changes_never_masquerade_as_layout(package,mutation):
    new=copy.deepcopy(package);mutation(new);c=classify_change(package,new)
    assert c['kind']=='mathematical' and c['requires_model_approval'] and c['invalidates_execution']

@pytest.mark.parametrize('spacing',['normal','relaxed'])
def test_layout_semantics_and_binding(package,spacing):
    p=copy.deepcopy(package);p['presentation']['equation_spacing']=spacing
    assert semantic_hash('task',1,'c'*64,p)==semantic_hash('task',1,'c'*64,package)
    assert semantic_hash('task',2,'c'*64,p)!=semantic_hash('task',1,'c'*64,p)
    assert semantic_hash('other',1,'c'*64,p)!=semantic_hash('task',1,'c'*64,p)
    assert semantic_hash('task',1,'d'*64,p)!=semantic_hash('task',1,'c'*64,p)

def test_closed_layout_fields_reject_hidden_math(package,contract):
    package['presentation']['latex_override']='1=2'
    with pytest.raises(MathematicsError):validate_package(package,contract)

def test_same_source_render_contains_conditions_not_only_equations(package):
    md,tex=render(package)
    for eq in package['dossier']['equations']:
        assert eq['latex'] in md and eq['latex'] in tex and '\\label{'+eq['id']+'}' in tex
    for x in package['dossier']['assumptions']:
        assert x['statement'] in md
    for x in package['dossier']['propositions']:
        assert all(condition in md for condition in x['conditions'])
    assert json.loads(md.split('```json\n')[1].split('\n```')[0])['dossier']==package['dossier']

def test_no_general_equation_truth_claim(package,contract):
    package['dossier']['equations'][0]['latex']='1=2'
    validate_package(package,contract) # Structure is valid, mathematical correctness still needs review.
    assert '结构通过不等于已证明' in render(package)[0]

def test_old_contract_hash_unchanged(contract):
    validate(contract)
    assert digest(contract)=='44e23c6a10b7581d82a2b2697159e7aaee1625d8486cb177bd541a9a36d2e61e'
    for version in ['1.0.0','1.1.0']:
        original=json.loads((ROOT/f'contracts/model-contract-{version}.schema.json').read_text(encoding='utf-8'))
        assert 'mathematical_package' not in original.get('properties',{})

@pytest.mark.parametrize('mutation',[
    lambda p:p['method_selection'].update(selected_candidate_id='missing'),
    lambda p:p['dossier']['equations'].append(copy.deepcopy(p['dossier']['equations'][0])),
    lambda p:p['contract_links'].pop(),
    lambda p:p['dossier']['propositions'][0].update(open_gaps=['missing proof']),
    lambda p:p['dossier']['symbols'][0].update(unit='s'),
])
def test_bad_cross_references_and_claims_rejected(package,contract,mutation):
    mutation(package)
    with pytest.raises(MathematicsError):validate_package(package,contract)
