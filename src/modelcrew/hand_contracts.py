"""Dependency-free hand capabilities and independent review check names."""

RESPONSIBILITIES = {'modeling': ['Planner', 'Researcher', 'Modeler'],
                    'coding': ['Coder'], 'writing': ['Writer']}
TOOLS = {
    'modeling': {'algorithm_search', 'paper_search', 'propose_contract', 'request_M1'},
    'coding': {'algorithm_search', 'register_code', 'code_execute', 'code_execution_status', 'request_P1', 'request_P2'},
    'writing': {'load_writing_context', 'draft_markdown', 'request_W1', 'request_W2'},
    'quality': {'read_snapshot', 'submit_review'},
}
OUTPUTS = {
    'modeling': {'task_graph', 'source', 'method_selection', 'contract', 'mathematics'},
    'coding': {'code', 'execution', 'result', 'figure', 'reproduction'},
    'writing': {'outline', 'manuscript', 'figure_selection', 'render'},
}
GATE_HAND = {'M1': 'modeling', 'P1': 'coding', 'P2': 'coding', 'W1': 'writing', 'W2': 'writing'}
REQUIRED_CHECKS = {
    'M1': ['model', 'assumptions', 'units', 'constraints', 'algorithm_premises', 'validation_plan'],
    'P1': ['execution', 'input_output', 'constraints', 'numerics', 'units'],
    'P2': ['execution', 'contract_implementation', 'error', 'reproduction', 'figure_meaning'],
    'W1': ['claims', 'evidence', 'citations', 'outline'],
    'W2': ['claims', 'figures', 'citations', 'layout', 'snapshot_consistency'],
}
