> 2026-11-06最新复审结论：阶段B功能通过、整体验收有条件通过。完整结论以[本次验收报告](stage-b-acceptance-report-20261106.md)为准；v2原确认Excel已找到并归档，旧固定样例原字节与历史档案补录仍有遗留。下文保留各次历史记录。

> 阶段B整体验收（2026-11-04）：26项回归通过，实际用户v2结果已确认；但原计划仍有三处缺口，阶段B暂不完整收尾。详见[验收报告](acceptance-audit.md)。下方较早状态按历史保留。

> 当前状态：v2真实求解已完成，12项契约检查及24项独立检查通过，26项测试通过。任务等待v2结果revision 2确认。[真实求解报告](v2-solver-result.md)。下文只联调/未执行为历史说明。

> 最新状态（2026-11-04）：专用PostgreSQL已启动，18项测试和两次真实数据库重启验证通过。实际任务dragon-q1 v1等待你的方案确认。请先看[契约摘要](contract-review.md)与[集成验证记录](integration-verification.md)。下文“未运行/阻断”属于此前开发记录。

# 阶段 B：当前实现与运行方式

当前已实现契约结构与引用校验、版本化业务表迁移、最小CLI，以及带PostgreSQL checkpointer的LangGraph两个interrupt关卡。真实数据库集成测试尚未运行，不代表阶段B已验收。

2026-11-03，7项契约测试通过。Docker Desktop再次被临时套接字路径错误阻断，未创建阶段B数据库。修复尝试保留了Docker/run临时目录备份，Secrets Engine临时路径访问被拒；未重置Docker、未删除容器/卷。随后提出的便携PostgreSQL下载请求未获批准，未执行下载。旧阶段A成功记录仍有效，不代表当前Docker可用。

## 安装与启动

```powershell
python -m pip install -r requirements-stage-b.txt
python scripts/start_stage_b_db.py
python -m modelcrew init-db
python -m pytest tests --integration -q
```

启动脚本仅为阶段B创建独立PostgreSQL16，使用modelcrew-stage-b-postgres容器、持久卷和127.0.0.1:55432。凭据生成到Git忽略的stage-b/.env，不覆盖LLM配置。已存在实例会沿用原凭据；修改密码字符串不等于更新数据库角色密码。可用MODELCREW_DATABASE_URL指定你自己的PostgreSQL。

所有集成测试用test-前缀任务和TEST_SIMULATED_USER模拟用户，不代表你的真实确认。它们在独立automated-tests项目保留审计记录，不清理数据库。`python -m pytest tests -q`仅实测无数据库测试，数据库用例会明确skip；使用--integration后数据库不可用会失败，不会伪装通过。

## 第一次人工演示

以下是数据库就绪后由你实际触发的命令，目前没有代你执行确认：

```powershell
python -m modelcrew validate contracts/examples/valid-2024-a-q1.json
python -m modelcrew create dragon-q1 contracts/examples/valid-2024-a-q1.json
python -m modelcrew show dragon-q1
python -m modelcrew resume dragon-q1
```

create后应停在WAITING_MODEL_APPROVAL，没有执行记录。审阅契约后再确认：

```powershell
python -m modelcrew act dragon-q1 --kind model --version 1 --actor local-user --request-id model-approve-1 --decision approve
```

随后导入历史固定工件，停在WAITING_RESULT_APPROVAL。它是流程联调，不会调用LLM、不会执行代码，也不证明新契约下的数值结果正确，review保留unknown。查看结果、revision及来源后再确认：

```powershell
python -m modelcrew act dragon-q1 --kind result --version 1 --result-revision 1 --actor local-user --request-id result-approve-1 --decision approve
```

两个确认都存在才产生confirmed_fixture_summary，明确不是小论文，不实现D阶段Writer。结果拒绝用--decision reject并填写--reason，保持待处理。

修改模型：复制契约JSON，修改内容，再调用--kind revise_model --contract 新文件 --version 当前版本 --reason 用户指导 --request-id 新键。会分配新版本、清除当前确认和下游引用，并切换新thread；旧契约、执行、结果、checkpoint不覆盖。

仅改解释：--kind revise_interpretation --version 当前版本 --result-revision 当前结果revision --reason 新解释 --request-id 新键；复用execution_id，新revision的结果确认清零。不接受把模型变化伪装为解释修改，CLI用户需正确选择；自动语义分类尚未实现。

actor是本机可信CLI的审计标签，不是身份认证；request_id是每个动作的幂等键，同键同请求不会重复推进，同键不同请求报错。过期契约版本、过期结果revision、未到达关卡的确认均拒绝。

## 崩溃恢复与一致性设计

PostgreSQL业务表是事实来源，LangGraph checkpoint是可重建流程状态。所有正常业务命令及图执行持有每任务数据库会话锁，契约修改后新thread隔离旧图；图节点检查thread是否仍是当前版本。锁串行化同题推进，不追求分布式高并发。

业务动作与幂等记录同一事务提交，再推进图/checkpoint，不能声称两者天然原子。确认后若在checkpoint前崩溃，`resume`根据持久化确认恢复；执行节点用task_id+version唯一键复用已有联调执行；摘要同样有唯一键。即使丢失当前thread checkpoint，也可从业务版本、执行和确认重建待确认节点。图resume消息只是唤醒，不作为授权来源。

migrations/001_stage_b.sql为初始迁移，使用版本表及只增历史表触发器防止业务历史update/delete；当前CLI只提供一次初始化迁移，不具备自动回滚或通用迁移框架。后续结构变化需追加新编号迁移。

## 验证边界与未完成工作

tests/test_workflow.py已准备真实PostgreSQL测试：新进程恢复两个等待点、重复/冲突请求、拒绝与新版本、旧版本确认、解释修改复用、模型变更失效、确认事务提交后崩溃、丢失checkpoint、并发确认和越过关卡。当前均未实测，不据此声明可靠性。

需要数据库恢复后运行这些用例，补测真实数据库服务重启，再创建dragon-q1交由你实际审阅两个关卡，才能验收B。当前只联调A固定工件，尚未接自动提案/代码/审核节点、真实任务执行、API或前端。

契约中新增的数学检查不是自动证明；校验器只对该题派生孔距做有限核验。固定联调时修改螺距等输入，仍然导入A历史工件并明确标记unknown，不会把它当作新计算结果。

2026-11-04：用户指导已使模型生成并保存dragon-q1契约v2，新版本待确认，v1历史完整保留。详见[v2审阅](v2-review.md)。

## 真实求解接入（新增）

migrations/002_real_solver.sql区分fixture和solver，允许每份契约保存多个明确run_id的真实运行，但不覆盖历史。执行、结果登记和确认是不同动作。

本轮代码生成脚本为scripts/generate_stage_b_solver.py；失败修订脚本scripts/repair_stage_b_solver.py。API会产生费用。代码审阅后用已有受限Docker执行器运行，独立核验由modelcrew/solver_validation.py实现，最后执行：

```powershell
python -m modelcrew attach-solver dragon-q1 --version 2 --run-dir stage-b/runs/solver-v2-20261104T131332959555Z
```

登记是幂等的且不自动确认结果。首次登记建立新结果revision和thread，清除结果确认，旧结果保留。`resume`从业务记录恢复solver关卡，确认后摘要种类为confirmed_solver_summary。当前模型物理参数以人工参考支持的本题输入为限；输入变化不能绕过独立核验直接套用旧参考。

受限执行器会拒绝覆盖已有output；重跑应创建新run_id。此轮生成、审阅、容器、登记为显式步骤，而非自动节点链。故障探针在另一个禁网容器/输出目录执行，不会污染正常数据。

## 2026-11-06最新实现与验证

输入结构模板/草稿、版本档案与回退功能见[操作说明](../docs/input-contract-and-version-cli.md)。数据库与版本功能完整回归54项通过，三次真实数据库重启演练通过，证据见`version-feature-verification.json`和`version-recovery-verification.json`。真实模型草稿本轮尚未调用，测试使用模拟接口。

实际已确认v2/revision 2未改变。历史求解容器重启后两个Excel文件哈希变化，当前数值回读通过，但原登记哈希保留并显示完整性异常；详见`acceptance-audit.md`末尾。本次不把功能测试通过等同于历史证据包完整恢复。

## 执行与解释审核专项更新

可配置、按版本绑定的执行后端及回执恢复，和结构化结论证据审核已补齐；使用说明见[专项文档](../docs/execution-and-interpretation-review.md)。最新回归76项通过，专项CLI演练两次数据库重启通过，证据为`executor-review-verification.json`。旧版本未保存执行配置时，恢复需要显式选择后端。历史Excel哈希异常、自由文字人工审核边界和真实模型草稿尚未验证的状态仍按前文记录。
