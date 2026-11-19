"""Synthetic structured documents/audits; never a real modeling conclusion."""
from modelcrew.modeling_proposal import CRITERIA


def document(source_id='statement'):
    text='这是测试专用的合成方案说明，用于核对结构、来源与审查路由，不代表真实建模结论。需要核对原始条件、数学前提和实际证据，不能据此确认任何业务结果。'
    return dict(problem_analysis=text,assumptions=[dict(statement='仅用于合成测试的限定条件假设。',basis='来源为测试生成的人工标记输入。',impact='只检验工程边界，不推广到真实题目。')],
        symbols=[dict(symbol='x',meaning='合成变量',unit='1',scope='测试问题')],
        model_derivation=text+" $x=a$ ",solution_plan=text,verification_plan=text,limitations=text,
        sources=[dict(source_id=source_id,use='用于核对合成题目输入和预期工程行为。')],
        applicability={key:dict(status='not_applicable',reason='该测试仅核对工程路由，不运行对应数值计算。') for key in ('discretization','nonlinear_solver','stability','convergence','boundary_conditions')})


def audit():
    return [dict(criterion=key,status='PASS',evidence=[dict(artifact_id='proposal',selector='/review_document/'+info[1]),dict(artifact_id='contract',selector='/method')],
        explanation='合成审查响应，仅用于结构与路由测试，不代表真实数学审查。') for key,info in CRITERIA.items()]
