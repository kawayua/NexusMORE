"""Database tests are opt-in; opting in makes connection failures hard failures."""
import pytest

def pytest_addoption(parser):
    parser.addoption('--integration',action='store_true',default=False,help='Run real PostgreSQL/checkpointer tests')
def pytest_collection_modifyitems(config,items):
    if not config.getoption('--integration'):
        for item in items:
            if item.path.name in ('test_workflow.py','test_api_workflow.py','test_mcp_workflow.py','test_mathematics_workflow.py','test_modeling_hand_workflow.py','test_question_references.py','test_hand_runtime.py'):item.add_marker(pytest.mark.skip(reason='requires real PostgreSQL; run with --integration'))
@pytest.fixture(scope='session',autouse=True)
def initialize_integration_database(request):
    if request.config.getoption('--integration'):
        from modelcrew.workflow import Workflow
        with Workflow() as w:w.setup()

