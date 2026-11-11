# C6：故障恢复与清理演练

C6对工作流、独立MCP子进程、真实Docker和PostgreSQL/checkpointer开展了故障演练。最终24项检查通过，完整回归151项通过。原始证据为 `stage-c/runs/c6-failures-20261106a/verification.json`，对应案例dossier保存在同目录；[机器可读摘要](../stage-c/c6-failure-verification-summary.json)保留真实故障与注入故障的区别。

测试只创建test-c6-*任务，确认actor均为TEST_SIMULATED_USER；没有调用LLM、运行正式赛题、修改dragon-q1，也没有接入OCR或视觉模型。测试数据库故障只终止本次测试连接，不重启共享数据库服务。

## 验证结果与处理方式

| 故障 | 实测恢复/阻断行为 | 后续处理 |
| --- | --- | --- |
| 本地索引配置缺失 | 工具明确返回retrieval_unavailable，不伪装为空结果；另一条新请求可正常读取公开原文 | 恢复服务/配置后用新request_id查询；失败记录保留 |
| 执行镜像不存在 | 记录基础设施失败，无容器和成功结果；之后只查询status，不自动派发 | 宿主修复镜像；若旧操作无法恢复，以新版本、新任务包重新确认，不能清空审计重跑 |
| 真实执行已完成但客户端丢弃响应 | 工作流保持SOLVING，恢复以code_execution_status找回同一回执 | resume查询状态；不重复code_execute |
| MCP进程在容器Running时真实退出 | 独立测试服务在inspect确认Running后os._exit；新服务接管原容器，代码只派发一次 | resume，直到执行结束再进入结果确认 |
| Docker清理命令失败 | 注入rm传输失败，保留真实pending-result和容器，不发布业务结果 | 修复清理能力后resume，核对身份、产物，再清理并发布同一回执 |
| 监控退出且容器监督器停止运行 | 测试代码在自身容器内SIGSTOP其PID1；新状态查询到截止时间后终止并清理 | 记录timeout/code失败，不发布成功结果，不自动重跑 |
| 已有容器消失 | 核对身份后移除本次专用测试容器，恢复返回outcome_unknown | 人工排查；保留SOLVING和日志，禁止从未知状态重新派发 |
| 求解代码语法错误 | failure_domain=code，清理容器，不创建结果，不越过结果关卡 | 修订代码须新任务包/新方案版本并重新确认；Coder自动修订策略属于D |
| 业务内容快照损坏 | 即使提供结果确认理由，也被哈希检查拒绝 | 恢复经验证的原字节或重新产生独立版本证据；不能伪造新哈希 |
| 执行器原始归档损坏 | status拒绝返回成功，不重新执行 | 先修复证据完整性，保留损坏事实 |
| 测试数据库连接终止 | 模拟确认已提交但checkpoint未推进，终止自己的真实连接；新Workflow恢复已提交状态 | 重新连接后resume；不能重造用户确认 |
| 测试checkpoint删除 | 只删除测试thread，按业务持久记录重建，不重复执行 | resume；业务表仍为权威 |
| pending回执被改成另一任务包哈希 | 在清理/发布前拒绝，不能挂接错误结果 | 核对并恢复本案例原始待发布字节后，status恢复同一执行 |

测试中的两次文件损坏均针对本次专用案例，原字节已恢复；业务快照含唯一测试nonce，避免影响其他任务复用的内容寻址文件。故障审计和原始运行记录保留，不删除数据库记录。

## 本次修复

原有status恢复在容器Running时只返回running，未接管原监控截止时间。现按claim.started_at和原任务timeout_s+15秒额外预算执行截止检查，过期后终止、归档并清理；因此监督器停止或原MCP监控退出不会使该恢复流程无限返回running。需要宿主继续调用status/resume才能触发接管，当前没有后台常驻孤儿扫描器。

pending-result发布新增job_sha256、run_id、code_sha256和authorization完整绑定检查，防止恢复时发布错任务回执。两项均有回归测试和真实容器演练。

## 操作入口与清理原则

优先读 `python -m modelcrew show TASK` 和 `python -m modelcrew tool-evidence TASK --version N`，核对当前版本、attempt的error_code/failure_domain和MCP记录。恢复使用 `python -m modelcrew resume TASK`；执行已有attempt时仅查询已知run状态。running不是新的代码失败，也不是可确认的结果。看到outcome_unknown、authorization_error、哈希错误或cleanup失败，先解决对应问题，不删除claim、不换job字节、不重新发送code_execute。

只有与登记job_sha256标签相符的容器才允许本执行器清理；不会全局docker prune或删除其他容器。最后逐个核对本轮全部claim，未遗留本轮容器，未动PostgreSQL/Qdrant容器。缺失镜像、消失容器、已确认代码失败案例保留在SOLVING供排查，没有为了“测试完成”而伪造成功或确认。

可复验命令：`python -m scripts.verify_stage_c_failures --output stage-c/runs/c6-failures-new`。输出目录必须未使用；脚本只对本轮创建并核对哈希的任务/容器实施故障。测试专用server为scripts.c6_fault_server，不是生产MCP入口，生产接口没有故障开关。

## 验收边界

本轮确实中断了真实MCP进程并接管真实容器，但不是整机断电或所有进程崩溃窗口的穷尽证明。清理命令错误和已完成响应丢失采用受控注入；数据库为单连接终止，不是完整数据库停机。C4已覆盖内存、输出上限等容器约束，本轮没有重复运行所有C4用例。服务恢复需要显式resume/status；未新增自动告警、调度器、用户认证或无人值守清理服务。

C1至C6工程检查已完成，可按[阶段C验收报告](../stage-c/stage-c-acceptance-report-20261106.md)审阅；用户验收尚未记录，未自动进入D。用户已取消强制新任务和空白建模上下文，后续可继续现有上下文，默认采用带出处的外部参考辅助建模。图片OCR按用户要求暂缓，多模态识图是已记录但未实现的方向；真实Modeler协作、论文引用位置与多角色修订在D实现和评估。
