# C5：MCP工作流接入与版本化引用

C5把两个独立MCP接入既有Workflow和PostgreSQL/checkpointer，不另建状态机。MCP客户端在可信宿主配置固定服务入口，调用参数不能替换启动命令、镜像、执行目录或授权。新增迁移006只增加不可变工具记录、引用和讨论表，使用 `python -m modelcrew init-db` 应用。

## 检索、讨论、确认

先建立任务与未确认方案，再调用 `Workflow.retrieve_references` 或API：

```text
POST /tasks/{task_id}/references/retrieve
{"version":1,"tool":"web_search","arguments":{"query":"A163","scope_url":"https://dxs.moe.gov.cn/zx/hd/sxjm/sxjmlw/2024qgdxssxjmjslwzs/"},"actor":"modeler","request_id":"reference-1"}
```

支持paper_search、web_search、web_read和reference_get。每次调用先提交started记录，再启动独立stdio MCP子进程；响应或传输失败均追加记录，关联task_id、version、contract_sha256和operation_key。响应片段、citation和哈希保存在数据库，不依赖后续网页仍可访问。相同request_id及参数重复调用返回原响应，不重新搜索；改变参数须新request_id。传输中断可能留下started/transport_error，读取操作可用同一请求重试，历史尝试保留。

方案讨论接口：

```text
POST /tasks/{task_id}/references/discussions
{"version":1,"kind":"proposal","text":"外部参考指出……；本方案适用条件是……，拟作如下调整……","references":[{"reference_id":"ref_实际64位哈希","decision":"adopted"}],"actor":"modeler","request_id":"proposal-1"}
```

kind为proposal或feedback；decision为adopted、rejected或considered。同一引用可经后续讨论更新决定，记录不覆盖。模型确认前，存在检索引用的版本必须有proposal讨论；明确标为considered的引用必须最终决定采纳或拒绝。未在讨论中选取的其余候选记为not_adopted。讨论与引用必须属于同任务同版本，不能引用任意旧任务的编号；可显式用reference_get导入新版本后重新讨论。

确认方案仍走原 `/actions` 的kind=model/decision=approve。该事务把来源、决定、讨论ID和哈希写入model_approve事件；确认后不再接受新检索或引用讨论。若新资料改变思路，应新建方案版本并重新确认。原版档案和确认快照保留，新版本不自动继承引用或执行任务包。

`GET /tasks/{task_id}/proposal`附带reference_evidence；`GET /tasks/{task_id}/tool-evidence?version=1`和版本dossier展示原文、引用、讨论、工具调用与执行回执。来源仍明确标为external_reference、modeler_generated=false；网页内容只是参考数据。

CLI对应命令为 `retrieve`、`discuss-references`、`tool-evidence`，各命令的 `--help` 显示参数；JSON参数和讨论文字从文件读取。actor仍是可信本地接口的审计标签，未新增用户认证，也不凭actor名称自动授予批准。

## 真实代码执行

选择 `mcp-code-executor` 后端，executor_config严格为：

```json
{"job_id":"预登记任务ID","job_sha256":"预登记任务包哈希"}
```

先在可信宿主用 `python -m modelcrew.docker_executor register`登记固定代码、全部原始输入、资源配置，以及mode=workflow/task_id/version/contract_sha256授权；可在数据库任务建立前登记，登记本身不执行。创建/修订任务时检查任务包绑定，用户确认的是该版本契约和不可变执行配置。修改代码须新任务包和新方案版本，不能在原批准下换代码。

执行根目录由宿主MODELCREW_EXECUTION_ROOT指定，默认stage-c/execution；镜像由MODELCREW_EXECUTION_IMAGE指定，默认modelcrew-reference:py311。API和模型不能提供这些路径。客户端向MCP仅传job_id；MCP在Docker执行前检查已提交的model_approved、当前版本、契约哈希、批准的任务包和完整输入哈希，不持有另一条数据库连接的任务锁，避免与等待子进程的Workflow死锁。Workflow派发与发布仍持任务锁；发布再次检查当前版本和批准状态。子进程显式继承该Workflow的数据库配置，不记录连接串。

Docker成功仅代表代码运行完成。产物经路径校验、哈希与内容寻址快照后，先保存持久后端回执，再发布执行/结果；审核状态unknown、mathematical_review=not_performed，停在结果确认关卡。结果确认需要用户明确审核理由，并重新校验归档产物。工具不会代替用户批准方案或结果。

派发结果不明或调用中断时，后续resume只调用code_execution_status，绝不再次code_execute。running保持SOLVING；代码错误、超时等记录failure_domain=code且不发布成功结果；基础设施/授权错误单独记录，不能计为Coder代码重试。新代码修订策略、Reviewer/Coder角色回路属于阶段D，当前不自动重试生成代码。

## 验收与边界

真实链路脚本为 `python -m scripts.verify_stage_c_mcp_workflow`，只运行固定的[1,2,3]平方和代码，不调用LLM。使用TEST_MODEL_STUB与TEST_SIMULATED_USER明确模拟讨论/批准，不是用户真实确认或独立建模。验证工作流→独立paper-search→BGE/Qdrant、官方目录联网定位同题资料、引用恢复、讨论/确认快照、工作流→独立code-executor→真实Docker、固定输出14、结果关卡，以及持久回执后发布中断恢复。另有模拟传输失联后仅查status的数据库集成测试，不能表述为真实杀进程或Docker运行中崩溃验收。

当前已绑定到任务、契约版本、来源、方案讨论和确认事件；论文正文的引用位置、真实modeler对话质量和Reviewer审核由阶段D实现，未声称可自动生成可靠参考文献。图片正文OCR仍未接入，C6完整故障/清理演练已完成24项检查，最新完整回归151项通过，见[恢复说明](failure-recovery.md)。工程测试通过不代表用户已验收或允许直接开始D。

查看[机器可读C5摘要](../stage-c/c5-mcp-workflow-verification-summary.json)与[阶段D前置要求](../stage-c/next-stage-entry-requirements.json)。


## 图片资料的后续处理方向（用户最新要求）

暂不使用OCR。不能直接读取文字的网页图片、扫描页可后续交给支持图像输入的多模态LLM解读，保留原图URL、所属网页、页码（已知时）、图片哈希、模型和调用记录。解读应单独标注“外部图片的LLM识读/概括”，不能冒充逐字原文或modeler原创；模糊公式、数值与无法辨认处明确标记不确定。最终是否采用仍经modeler与用户讨论。此处仅记录方向，尚未接入视觉模型，也未发起付费识图调用。

真实modeler协作的实现属于阶段D：可在现有任务/上下文中接入真实Modeler（用户已取消强制重开要求），使用已经打通的引用、讨论、版本和双确认接口。其质量需用实际对话评估，重点是对题意和假设的理解、外部参考的适配理由、对用户指导的准确修改、数值证据核对以及未确认不执行；现有固定桩和模拟确认只能证明流程可运行，不能证明模型具备这些能力。
