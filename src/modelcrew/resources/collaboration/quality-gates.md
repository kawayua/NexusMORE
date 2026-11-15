# 独立质检与用户确认

Validator/Reviewer 是 M1/P1/P2/W1/W2 的临时只读职责，不是额外常驻业务 Agent。审查上下文不得参与被审产物的编写或修正；作者换角色名、同一上下文换 call_id 均不形成独立性。质检只能读取快照、提交回执，不能写权威代码/正文、执行用户批准或修改作者产物。

| 节点 | 范围 | 下一步边界 |
|---|---|---|
| M1 | model, assumptions, units, constraints, algorithm_premises, validation_plan | 建模手修正后复验，通过后仍等待用户模型确认 |
| P1 | execution, input_output, constraints, numerics, units | 只验声明的最小纵向切片，通过后方可全量，不冒称全量完整性 |
| P2 | execution, contract_implementation, error, reproduction, figure_meaning | 验全量与复跑及图意，通过后仍等待用户结果确认 |
| W1 | claims, evidence, citations, outline | 长正文前审查论断—证据大纲，缺依据回对应手 |
| W2 | claims, figures, citations, layout, snapshot_consistency | 正文及选图批准、正式导出和真实渲染后审查；检查全部要求格式的实际页图 |

回执按已有 schema 返回 PASS/FAIL/BLOCKED、精确证据、问题领域、返工对象及复验入口。JSON 证据使用真实 artifact_id 和可解析 JSON Pointer；W2 引用协议启用时仅用已登记 E/P 引用。缺依赖、图片不可读或证据不足报 BLOCKED，不猜测通过。不得截断、猜测或修补回执以得到 PASS。

模型问题回 modeling，代码/数值实现问题回 coding，写作问题回 writing，基础设施问题回 recovery；解释问题按受影响对象路由。先运行可用机械检查，独立审查再核对语义和原始证据；必要复跑经受控执行器形成新证据，审查者不获得任意宿主执行权。

同一审查者可复验其未参与修改的产物。一旦参与修改，应换独立上下文。缺独立调用能力则明确未完成/受限，不能把作者自检登记为独立审查。模型相同不意味着错误独立，独立上下文也不构成数学证明。文档维护任务本身不触发这些业务门禁。
