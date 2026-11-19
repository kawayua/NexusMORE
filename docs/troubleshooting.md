# 排错指南

先确认正在使用同一Python、工作区和DSH profile，再读取当前状态；保留原失败与回执。以下命令使用PowerShell，`$python`是README中虚拟环境Python的绝对路径，`MODELCREW_WORKSPACE`是注册时的业务工作区。新终端需重新设置，不能复制他人的本机路径。

```powershell
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:MODELCREW_WORKSPACE = Join-Path $env:LOCALAPPDATA "NexusMORE\workspace"
& $python -m modelcrew --version
& $python -m modelcrew config-show
& $python -m modelcrew doctor --profile workflow --services
```

## 安装与配置

| 现象 | 排查与处理 |
|---|---|
| 找不到`py`或Python版本不符 | 选择实际安装的CPython 3.13；用其完整`python.exe`路径创建venv，不使用DSH附带3.12 |
| 缺`modelcrew`或科学依赖 | 核对`$python`；在项目源码目录用该解释器安装`.[paper,dsh]`，随后执行`-m pip check`；不要混用系统pip |
| 仅`doctor core`通过但业务失败 | core只查基础项；运行workflow服务诊断，核对模型配置、数据库及Docker；文档/论文检索依赖另按对应指南配置 |
| 配置错误、显式路径缺失 | 检查自己的`settings.json`及环境覆盖；显式无效项会拒绝，不会偷偷回退。用`config-show`核对脱敏摘要 |
| 只在终端有密钥，DSH中缺失 | 宿主可能清理继承变量；按`model.api_key_env`将密钥保存到该工作区`configs/local/secrets.env`并重启相关进程 |
| API拒绝参数或结构化输出 | 核对具体端点/模型，当前发送JSON及thinking扩展参数；兼容性按模型验证，保留原错误，不自动切供应商 |

所有报错、截图和日志公开前检查是否含密钥、连接串、题面、个人路径或宿主消息。`config-show`脱敏不代表其他日志都已脱敏。

## Docker、数据库与镜像

先运行 `& $python -m modelcrew environment status`。Docker Desktop必须启用Linux引擎；WSL2、引擎状态、命名管道权限和当前进程权限分别核对。终端能访问Docker不保证每个受限宿主进程也能访问。

首次准备可按[环境说明](environment-preparation.md)执行setup。已有工作区若被识别为自定义数据库/服务，准备器会拒绝自动接管；先核对配置及服务归属。不要删除数据卷、重置数据库、清空配置或运行全局prune来“修复”状态。缺业务迁移时，由操作者在确认工作区后执行 `& $python -m modelcrew.workflow_mcp migrate`。

缺执行依赖/中文字体时，核对实际任务镜像和导出工具。默认镜像不自动具有任意后续新增依赖；图形任务按[绘图工具](figure-tools.md)和自己的镜像配置准备。任务容器禁网，不能依赖求解中临时安装包。新增镜像/代码须按原业务规则绑定，不能直接篡改已登记执行包。

## DSH连接或注册问题

| 现象 | 排查与处理 |
|---|---|
| `/nexusmore`未出现 | 确认正在使用的profile；`nexusmore-workflow`与连接插件应active；完整退出DSH而非仅关闭到托盘，然后重开 |
| 能发现工具但不能读项目 | 检查后端工作区和数据库；使用相同Python执行只读诊断，核对迁移 |
| 注册器拒绝覆盖或回退 | 比较管理块、备份与原回执；同名冲突、锁或宿主修改需人工核对，不能删管理块后盲重装 |
| 迁移源码/venv后插件失效 | 原配置中的Python和文件URL可能已变；先保留旧配置与回执，再按实际新路径核对注册 |
| 读工具成功但模型任务失败 | `/nexusmore`仅检查连接和有限读取，不检查所有模型/执行器能力；继续看失败所属阶段 |

现有本机G5记录中，管理块曾含额外原生UI设置而触发安装器保守拒绝，但实际枢模条目一致且可用；拒绝覆盖不自动意味着必须破坏性重装。回退仅在当前配置仍匹配原安装后哈希时可自动进行，见[注册与回退说明](dsh-local-connection.md)。

## 审阅、确认与恢复

没有待审文件、文件发布失败或用户回复和通知处于同批输入时，旧文字不能批准新稿。请求系统重新定位当前任务并展示完整待审稿，打开后再明确确认。修改意见、疑问或“通过但还要改”应作为讨论，不强制解释成批准。

如果原小题已无待办，但当前汇编仍待审，应只读查找确实引用该题的唯一有效汇编，并展示其当前合并稿；不要把小题`no_pending`解释成整个项目结束。多对象/多版本时先确定目标，不能一次批准不相干稿件。

遇到`outcome_unknown`或断连，先查询原请求`operation_status`及原回执，再决定恢复。业务执行成功而回复丢失时，不得换请求键重新运行。已收到但JSON结构/Pointer引用无效，属于响应内容/证据问题；不能套用仅适用于证实未送达的delivery恢复。保留原响应、元数据、证据哈希和异常。

每个attempt最多一次独立复核；作者重试、质检复核与人工修复是不同额度。修复前先定位具体缺失证据，再按现有恢复入口生成新证据并冻结，不能修改回执为PASS。历史故障资料可参考[恢复记录](failure-recovery.md)，其旧路径/命令按历史语义保留，不能直接套用到当前活跃任务。

## 导出或审图失败

正式导出先核对当前结果、正文/配图批准和内容身份。当前支持Tectonic 0.17.0、Pandoc 3.6.4；Word到PDF的原生渲染需已授权Microsoft Word、字体和进程访问权限。工具存在、编译返回0或生成预览不等于正式稿通过。

所有候选/正式PDF都要核对完整页数、生成并检查每页、保留文件和预览哈希；实际读图、独立P2/W2和用户成品审阅分别记录。不要删最后一页、隐藏字体/越界警告或用理由字符串绕过。纯导出修复若数值及全部检查字节未变，可核验后沿用原限定误差接受；其他受影响内容重新审阅。

仍需协助时，使用[缺陷模板](../.github/ISSUE_TEMPLATE/bug_report.md)提交版本、实际系统/宿主、脱敏复现、预期/实际结果、错误代码与发生阶段。公开附件先做许可与秘密检查；完整证据在本机保留，不必贴整份业务数据库。
