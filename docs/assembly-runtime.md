# 通用 E 阶段：汇编输入运行

> 2026-11-10后续更新：全局汇编、双审阅、导出适配及局部更新已接线，见[通用构建接口](assembly-builds.md)。下文保留首轮E1范围说明；最新状态以阶段E入口和后续实施报告为准。

2026-11-10 首轮实现范围为 E1 的通用输入接入、不可变冻结、恢复核验与依赖影响报告，不宣称通用汇编、导出或 W2 编排全部完成。实现入口为 `modelcrew.assembly_runtime`，由 `Workflow.start_assembly/assembly_status` 及 HTTP/CLI 共用。

## 入口

- `POST /projects/{project_id}/assembly-runs`：创建冻结运行。
- `GET /projects/{project_id}/assembly-runs/{run_id}`：重新核验冻结文件、当前模型/结果/正文/图片批准及独立 W1。
- `python -m scripts.run_assembly start PROJECT --request request.json`
- `python -m scripts.run_assembly status PROJECT --run-id UUID`

请求示例：

```json
{
  "request_id": "assembly-v1",
  "actor": "operator",
  "required_questions": ["q1", "q2"],
  "chapters": [
    {"question_id": "q1", "task_id": "task-q1", "run_id": "WRITER_RUN_UUID"},
    {"question_id": "q2", "task_id": "task-q2", "run_id": "WRITER_RUN_UUID"}
  ],
  "allow_partial": false
}
```

默认源任务须属于目标项目；历史任务分属不同项目时，每题显式提供 `source_project_id`，不能静默借用其他项目。当前接口沿用项目本地可信操作约定，不新增跨租户鉴权保证。`previous_run_id` 可引用同一汇编项目的既有冻结运行，报告新旧输入差异。

## 准入、恢复与变化

程序锁定汇编项目和排序后的源任务，复用 D 的真实当前版本、M1/P2、模型/结果批准及封存文件门禁。正文和选图必须都通过，状态必须为 `READY_FOR_E_EXPORT`；W1 重新检查原票据、快照、审查者独立身份、检查项和绑定，不能只信入口文件中的 PASS 字符串。

完整源证据链、正文和选图回执复制到新运行目录；共享封存路径只复制一次，各题保留自己的引用。当前论文规范实际读取并归档。数据库迁移 011 保存不可修改的运行清单，文件仅新建，已有论文和审查记录不覆盖。同项目相同 request_id/请求返回同一运行，不同请求复用该键会拒收。中途文件复制失败不登记成功；残留未登记目录保留为失败现场，不用于恢复已完成运行。

状态查询不信缓存状态，每次核验实时上游与冻结字节。正常完整输入为 `ASSEMBLY_INPUTS_FROZEN`；只有显式 `allow_partial` 才允许缺题，状态为 `PARTIAL_INPUTS_FROZEN`。上游版本、批准或证据改变后返回 `STALE_INPUTS`、受影响题及原因。单题变化使该题章节及摘要、引言、结论、全局编号、构建和 W2 需要重建/复核，无关题输入保留；全局政策或清单变化影响全部题。这里只报告依赖影响，不自动重算、不撤销历史通过记录、不替用户批准任何新版。

## 与既有 W2 的关系

最新 Q1/Q2 已有合编 PDF/Word 和独立 W2，本轮只复核现存产物哈希，无新编译或新审查。它们仍是具体构建的有效历史证据；新冻结运行的 `new_W2_performed=false` 只说明本轮没有另做 W2，不否认历史 W2。将既有构建接入通用生命周期时，必须同时验证源清单、构建版本、渲染及审查绑定，不能复制 PASS 字段授予新运行。

## 尚未接入

本轮没有接入通用的跨题正文组织、全局符号/引用变换、合编修改审阅、编译/渲染状态推进、W2 调用或既有构建的严格复用登记，也没有声称完成真实上游修订后的自动局部重建。当前变化演示是隔离合成输入的依赖测试，不修改真实已批准模型、结果或论文。既有案例的合编修改也不因本轮启动 E 自动获得用户批准。

实施证据见 `stage-e/implementation/20261110-v1/`。首次已接通的真实输入冻结运行见该目录 `start-result.json`。

## E 规范版本重新绑定（2026-11-10）

当已确认的科学结果不变、写作和排版规范更新时，使用 `Workflow.rebind_assembly(project, previous_run_id, ...)` 或 `POST /projects/{project_id}/assembly-runs/{run_id}/rebindings`。请求必须明确携带 `request_id`、`actor`、`reason`、`expected_previous_context` 和 `expected_current_context`，两个身份均为完整 `writing_context()` 的规范化摘要；不能只凭工作流版本号迁移。

入口创建新的不可覆盖输入运行，封存原输入链与新规范全文，记录父运行和规范差异。科学输入、当前模型/结果批准、数学绑定、跨题引用和独立 M1/W1 票据仍逐项检查。历史票据在其冻结规范下只读验证；作用域以 ContextVar 隔离并在异常后恢复，普通状态和新审查仍使用当前规范。算法、审查门禁、图片数量等实质要求变化拒绝该入口；允许的规范变化限于写作指引、排版参考文件、工作流排版要求以及全局符号表政策。没有执行求解器，也不授予新的科学或论文批准。

新输入应另建汇编构建。`POST /projects/{project_id}/assembly-builds/{build_id}/review-bindings` / `Workflow.bind_assembly_reviews` 可以引用带哈希的已有正文及选图批准包；原始批准包不改写。默认要求当前正文、选图、证据及规范身份完全匹配。若旧审阅稿与程序构建只因归一化缓存编号不同，可显式提供 `original_source`：核验原批准确属该源、正文逐字节相同、整个图片目录除 `evidence.chapters[].identity` 和 `normalized_sha256` 外完全一致，再保存带原始快照及等价证据的批准作用域映射。图片语义、科学证据、正文、政策任何其他变化均拒绝复用，不能生成新的用户原话或批准。

此绑定不会登记新的正式导出或授予新构建 W2。原已验收 PDF/Word 继续属于原输出字节；通过新的版本绑定记录关联相同正文和图片，历史验收和旧构建保持不变。通用 W2 自动派发仍为后续事项。
