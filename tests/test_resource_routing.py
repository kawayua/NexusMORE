"""F6 routing tests exercise boundaries, real adapters, recovery and frozen inputs."""
import json
from pathlib import Path

import pytest
from modelcrew import resource_routing as routing


def request(**updates):
    result={'task_id':'routing-fixture','question_id':'q1','version':1,'role':'modeling','stage':'planning',
        'request_id':'request-1','contract_sha256':'a'*64,'query':'请分析线性规划的单位与最小二乘推导','inputs':[]}
    result.update(updates)
    return result


def test_index_first_and_only_matching_sections_are_frozen(tmp_path):
    state=routing.route(tmp_path/'routes',request(),tmp_path)
    assert state['status']=='completed'
    docs=state['plan']['documents']
    assert docs[0]['path']=='algorithms/index.md'
    assert 'lp' in state['plan']['selection']['algorithm_ids']
    assert 'least-squares' in state['plan']['selection']['math_ids']
    assert all('machine-learning.md' not in row['path'] for row in docs)
    assert state['plan']['selection']['premises_status']=='unknown_requires_model_review'
    assert not state['formal_approval']
    frozen=routing.freeze(tmp_path,state)
    assert routing.frozen_context(tmp_path,frozen)['selection']==state['plan']['selection']
    data=json.loads((tmp_path/routing.SNAPSHOT).read_text(encoding='utf-8'))
    data['plan']['documents'][0]['text']+='modified'
    (tmp_path/routing.SNAPSHOT).write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(routing.RoutingError,match='Frozen'):
        routing.frozen_context(tmp_path,frozen)


def test_no_matching_method_is_explicit_and_never_adopted(tmp_path):
    state=routing.route(tmp_path/'routes',request(query='请先了解这个未知问题'),tmp_path)
    assert not state['plan']['selection']['algorithm_ids']
    assert any(g['code']=='no_matching_algorithm' for g in state['plan']['gaps'])
    with pytest.raises(routing.RoutingError) as error:
        routing.route(tmp_path/'unknown',request(algorithm_ids=['unregistered-solver']),tmp_path)
    assert error.value.code=='no_matching_method'


@pytest.mark.parametrize('override',[{'role':'coding','stage':'M1'}, {'role':'quality','stage':'planning'}, {'user_approval':True}])
def test_role_and_approval_claims_do_not_expand_scope(tmp_path,override):
    with pytest.raises(routing.RoutingError):
        routing.route(tmp_path/'routes',request(**override),tmp_path)


def test_independent_gate_context_has_no_author_history_or_execution(tmp_path):
    state=routing.route(tmp_path/'routes',request(role='quality',stage='M1',query='只读审查'),tmp_path)
    assert state['plan']['independent_context']
    assert not state['operations']
    assert not any('modeling-hand.md' in doc['path'] for doc in state['plan']['documents'])
    with pytest.raises(routing.RoutingError) as error:
        routing.route(tmp_path/'denied',request(role='quality',stage='M1',inputs=['secret.pdf']),tmp_path)
    assert error.value.code=='permission_denied'


def test_changed_request_or_question_cannot_reuse_old_result(tmp_path):
    initial=routing.route(tmp_path/'routes',request(),tmp_path)
    with pytest.raises(routing.RoutingError) as error:
        routing.route(tmp_path/'routes',request(query='changed'),tmp_path)
    assert error.value.code=='request_conflict'
    other=routing.route(tmp_path/'routes',request(question_id='q2'),tmp_path)
    assert other['route_path']!=initial['route_path']
    assert other['snapshot_sha256']!=initial['snapshot_sha256']


def test_plan_only_and_completed_receipt_recovery_never_dispatch_again(tmp_path,monkeypatch):
    planned=routing.route(tmp_path/'routes',request(),tmp_path,execute=False)
    assert planned['status']=='planned'
    completed=routing.route(tmp_path/'routes',request(),tmp_path)
    path=Path(completed['route_path']);record=routing.read(path);record['status']='claimed';routing.atomic(path,record)
    monkeypatch.setattr(routing,'execute_tool',lambda *args:pytest.fail('recovery must not execute'))
    recovered=routing.route(tmp_path/'routes',request(),tmp_path)
    assert recovered['status']=='completed' and recovered['recovered_from_saved_receipts']


def test_unknown_dispatch_queries_saved_status_without_retry(tmp_path,monkeypatch):
    source=tmp_path/'sample.xlsx';source.write_bytes(b'fixture')
    req=request(inputs=[source.name])
    state=routing.route(tmp_path/'routes',req,tmp_path,execute=False)
    path=Path(state['route_path']);state['status']='claimed';routing.atomic(path,state)
    monkeypatch.setattr(routing,'execute_tool',lambda *args:pytest.fail('unknown outcome cannot resend'))
    assert routing.route(tmp_path/'routes',req,tmp_path)['status']=='outcome_unknown'


def test_unsupported_format_missing_dependencies_and_input_boundary(tmp_path,monkeypatch):
    (tmp_path/'sample.pptx').write_bytes(b'fixture')
    assert routing.route(tmp_path/'unsupported',request(inputs=['sample.pptx']),tmp_path)['code']=='unsupported_format'
    (tmp_path/'sample.xlsx').write_bytes(b'fixture')
    monkeypatch.setattr(routing.importlib.util,'find_spec',lambda name:None)
    assert routing.route(tmp_path/'missing',request(inputs=['sample.xlsx']),tmp_path)['code']=='missing_dependencies'
    with pytest.raises(routing.RoutingError) as error:
        routing.route(tmp_path/'escape',request(inputs=['../outside.xlsx']),tmp_path)
    assert error.value.code=='unsafe_path'


def test_real_spreadsheet_route_preserves_formula_and_rejects_changed_artifact(tmp_path):
    from openpyxl import Workbook
    source=tmp_path/'dataset.xlsx';book=Workbook();book.active.append([2,3,'=SUM(A1:B1)']);book.save(source)
    original=routing.sha(source)
    state=routing.route(tmp_path/'routes',request(inputs=[source.name]),tmp_path)
    assert state['status']=='completed',state
    assert state['operations'][0]['returncode']==0
    assert state['operations'][0]['executor']['kind']=='installed_python_subprocess'
    frozen=routing.freeze(tmp_path,state)
    context=routing.frozen_context(tmp_path,frozen)
    data=context['observed_inputs'][0]['content']
    assert data['complete'] and not data['formula_values_recalculated']
    assert data['sheets'][0]['rows'][0]==[2,3,'=SUM(A1:B1)']
    assert routing.sha(source)==original
    replay=routing.route(tmp_path/'routes',request(inputs=[source.name]),tmp_path)
    assert replay==state
    tool=Path(state['route_path']).parent/'tool-0/tool-output/rows.json'
    tool.write_bytes(b'changed')
    with pytest.raises(routing.RoutingError) as error:
        routing.route(tmp_path/'routes',request(inputs=[source.name]),tmp_path)
    assert error.value.code=='artifact_changed'


def test_failed_pdf_parser_is_not_reported_as_success(tmp_path):
    (tmp_path/'broken.pdf').write_bytes(b'not a valid PDF')
    result=routing.route(tmp_path/'routes',request(inputs=['broken.pdf']),tmp_path)
    assert result['status']=='failed' and not result['formal_approval']
    assert result['operations'][0]['returncode']!=0
    assert not (Path(result['route_path']).parent/'tool-0/tool-output/pages.json').exists()


def test_selected_resource_mutation_and_absence_have_distinct_failures(tmp_path,monkeypatch):
    monkeypatch.setattr(routing,'verify_resources',lambda:(_ for _ in ()).throw(ValueError('changed')))
    with pytest.raises(routing.RoutingError) as error:
        routing.registry()
    assert error.value.code=='resource_changed'
    monkeypatch.setattr(routing,'verify_resources',lambda:(_ for _ in ()).throw(FileNotFoundError('missing')))
    with pytest.raises(routing.RoutingError) as error:
        routing.registry()
    assert error.value.code=='resource_missing'


def test_new_runtime_uses_routed_resources_but_quality_calls_receive_no_author_packet(tmp_path,monkeypatch):
    from modelcrew import hand_runtime as runtime
    state=routing.route(tmp_path/'routes',request(role='coding',stage='GENERATE_MINIMAL'),tmp_path)
    expected=routing.freeze(tmp_path,state)
    monkeypatch.setattr(runtime,'run_folder',lambda row:tmp_path)
    monkeypatch.setattr(runtime,'save',lambda *args,**kwargs:None)
    row={'task_id':'routing-fixture','version':1,'hand':'coding','phase':'GENERATE_MINIMAL',
         'payload':{'ops':{},'resource_routing_sha256':expected}}
    class Model:
        def __init__(self): self.calls=[]
        def call(self,folder,stage,system,data,**kwargs):
            self.calls.append(data)
            if stage=='Coder':
                assert data['nexusmore_resources']['use_binding']['phase']=='GENERATE_MINIMAL'
                assert data['nexusmore_resources']['documents'][0]['path']=='algorithms/index.md'
            else:
                assert 'nexusmore_resources' not in data
            return {'fixture':True},{'status':'completed'}
    model=Model()
    runtime.provider(None,row,'coder-1','Coder',{'fixture':True},model=model)
    runtime.provider(None,row,'coder-1','Coder',{'fixture':True},model=model)
    assert len(model.calls)==1
    row['phase']='REVIEW_P1'
    runtime.provider(None,row,'review-1','P1',{'fixture':True},model=model)
    assert len(model.calls)==2


def test_adapter_change_and_missing_original_input_cannot_replay(tmp_path,monkeypatch):
    state=routing.route(tmp_path/'routes',request(),tmp_path)
    monkeypatch.setattr(routing,'implementation_identity',lambda:'changed')
    with pytest.raises(routing.RoutingError) as error:
        routing.route(tmp_path/'routes',request(),tmp_path)
    assert error.value.code=='resource_changed'


def test_new_algorithm_context_uses_installed_catalog_and_keeps_false_geometry_excluded():
    references=routing.installed_algorithm_context('optimization',card_ids=['lp'])
    assert not references['legacy_runtime_catalog_used']
    assert references['cards'][0]['card']['id']=='lp'
    assert references['cards'][0]['applicability']['status']=='needs_review'
    rejected=routing.installed_algorithm_context('geometry',card_ids=['bracketed-root'],facts={'continuous_on_bracket':False})
    assert not rejected['cards'] and rejected['excluded'][0]['status']=='excluded'
