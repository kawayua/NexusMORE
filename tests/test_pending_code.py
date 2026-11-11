"""Pending Q2 execution cannot silently use historical results."""
import pytest
from modelcrew.executors import backends,prepare_config,ExecutionRequest

def test_pending_code_cannot_fall_back_to_fixture():
    backend=backends()['pending-code']
    request=ExecutionRequest('TEST_ONLY_Q2',1,'0'*64,'TEST_ONLY','pending-code',{}, {})
    with pytest.raises(ValueError,match='Code is not registered'):backend.execute(request)

def test_pending_code_rejects_execution_config():
    assert prepare_config('pending-code',{})=={}
    with pytest.raises(ValueError,match='takes no config'):prepare_config('pending-code',{'fixture':'NOT_ALLOWED'})
