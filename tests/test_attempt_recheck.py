import copy
import pytest
from modelcrew import hand_runtime as hr
from modelcrew.workflow import WorkflowError


def row(attempt=7):
    return {'phase':'NEEDS_HUMAN','payload':{'attempt':attempt,'recheck_used':True,'ops':{'P2-3-recheck':{'state':'completed'},f'P2-{attempt}':{'state':'completed'}},'reviews':{},'failure_domain':'review_output','last_review':{'gate':'P2','attempt':attempt,'stage_key':f'P2-{attempt}'}}}


def test_old_attempt_use_does_not_consume_new_attempt_and_history_is_unchanged():
    value=row();before=copy.deepcopy(value)
    assert hr.validate_recheck(value,'Investigate invalid original evidence pointers')=='P2'
    usage=hr.recheck_attempt_usage(value['payload']);assert not usage['used_this_attempt'] and set(usage['used_attempts'])=={'3'}
    assert value==before


def test_same_attempt_is_blocked_across_gates():
    value=row(3)
    with pytest.raises(WorkflowError,match='per attempt'):hr.validate_recheck(value,'second request')
    value['payload']['last_review']['gate']='P1'
    with pytest.raises(WorkflowError):hr.validate_recheck(value,'switch gate to evade limit')


def test_claim_before_provider_already_consumes_current_attempt():
    value=row();value['payload']['ops']['P2-7-recheck']={'state':'claimed'}
    assert hr.recheck_attempt_usage(value['payload'])['used_this_attempt']
    with pytest.raises(WorkflowError):hr.validate_recheck(value,'Do not duplicate in-flight reviewer')


def test_legacy_unattributed_boolean_is_not_silently_reset():
    value=row();value['payload']['ops'].pop('P2-3-recheck')
    assert hr.recheck_attempt_usage(value['payload'])['legacy_unattributed_use']
    with pytest.raises(WorkflowError):hr.validate_recheck(value,'Need historical evidence first')


def test_explicit_attempt_map_survives_later_attempts():
    value=row();value['payload']['recheck_attempts']={'7':{'gate':'P2','stage_key':'P2-7-recheck'}}
    assert hr.recheck_attempt_usage(value['payload'])['used_this_attempt']
    value['payload']['attempt']=8
    assert not hr.recheck_attempt_usage(value['payload'])['used_this_attempt']


def test_failed_delivery_or_incomplete_original_cannot_be_rechecked():
    value=row();value['payload']['ops']['P2-7']['state']='claimed'
    with pytest.raises(WorkflowError,match='completed original'):hr.validate_recheck(value,'Not known to have returned')
