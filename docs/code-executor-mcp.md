# code-executor MCP 与双工具分工

独立服务入口为 `python -m modelcrew.code_executor_mcp`，使用 `mcp==1.30.0` 的stdio协议；核心是 `modelcrew/docker_executor.py`，容器内监督器为 `execution/sandbox_runner.py`。与检索MCP是两个独立进程，当前尚未自动接入LangGraph节点。

## 这两个MCP在项目中的作用

| 工具服务 | 做什么 | 关键输入 | 返回什么 |
|---|---|---|---|
| paper-search | 从允许的资料中查找可追溯的参考片段 | 查询、资料类型等过滤条件 | 片段、来源、页码/位置、哈希、相似度 |
| code-executor | 在受限Docker内执行已登记的代码和输入 | 服务端job_id；状态查询用run_id | 执行状态、退出码、日志、耗时、产物清单与哈希 |

MCP是让工作流统一发现、调用和读取工具结果的协议，两个服务本身不是建模Agent。预期链路为：Researcher调用检索工具 → Modeler形成契约 → 用户确认 → Coder生成实现 → 执行工具运行 → Reviewer核验 → 用户确认结果。代码运行成功只证明这次运行完成，不证明数学模型或数值结果正确。

检索当前仅含题面和通用算法资料，同题论文及其方法提示被排除。执行器也不会自行检索资料、选择建模方案或代替用户确认。C5将负责把上述工具接入业务工作流，并将调用记录与小题及契约版本关联；本次只完成独立执行器工具和必要的授权检查。

## 服务端登记及授权

MCP调用者不能直接传入代码、宿主机路径、Docker参数、镜像或approved=true。代码及输入先由可信本地入口登记，形成不可覆盖的任务包：

```powershell
python -m modelcrew.docker_executor register execution-001 --code path/to/solver.py --inputs path/to/input-manifest.json --task TASK_ID --version 1 --contract-sha256 CONTRACT_SHA256
```

inputs JSON是列表，每项包含name（容器内相对文件名）、path（本地来源）、sha256及input_id（契约输入ID）。正式任务必须完整匹配当前已确认契约中的输入ID与哈希。代码、输入和监督器在登记时保存副本与哈希，执行前重新核对；任务包变更会被拒绝。

正式任务派发前读取PostgreSQL事实记录，检查当前版本、model_approved和契约哈希；启动前再检查一次。未确认或版本过期拒绝执行。这里没有调用用户确认动作，也没有将执行结果写入现有业务结果表。运行期间若业务版本改变，输出仍绑定原版本；C5接入时还需检查版本与执行配置，不能将旧执行自动附到新方案。

开发验证任务通过可信登记入口的 `--verification` 标记，服务也必须由宿主明确指定 `--allow-test-jobs` 才可执行；默认服务拒绝。这是验证程序专用模式，不代表真实用户确认或独立建模实验，MCP参数不能打开它。

默认任务包和回执在本地 `stage-c/execution/`，该目录已加入Git忽略。可用宿主参数 `--root`选择独立目录，工具请求不能改变它。

## 启动与调用

复用当前已安装的 `modelcrew-reference:py311` 镜像，内含Python 3.11、numpy、scipy和openpyxl。镜像在派发时解析为固定image ID，容器内不联网安装依赖。依赖缺失应返回明确代码错误。镜像构建入口仍为：

```powershell
docker build --pull=false -f execution/Dockerfile.py311 -t modelcrew-reference:py311 execution
python -m modelcrew.code_executor_mcp
```

通用MCP客户端配置示例：

```json
{
  "mcpServers": {
    "modelcrew-code-executor": {
      "command": "python",
      "args": ["-m", "modelcrew.code_executor_mcp"],
      "cwd": "D:/big-third-up/modelcrew",
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

`tools/list`提供严格inputSchema/outputSchema以及两个工具：

```json
{"name":"code_execute","arguments":{"job_id":"execution-001"}}
{"name":"code_execution_status","arguments":{"run_id":"execution-001"}}
```

当前run_id与job_id相同。重复execute复用已保存的原回执，不重新启动容器；status不会触发求解。跨进程文件锁阻止两个服务同时推进同一任务。若另一操作正在进行，返回execution_busy，客户端稍后查询。派发结果不明时返回outcome_unknown并保留原派发记录，不自动重派。开始前已确认失败的容器会清理并保留失败记录。

执行回执包含job/code哈希、授权关联、image ID、状态、退出码、stdout/stderr、耗时、限制实测配置、产物及cleanup信息。每个工具调用有call_id，先保存开始审计再允许派发，完成时保存结果摘要。若完成后的审计失败，工具提示查询原run_id，不能推断代码未运行并换ID重试。

## 隔离与产物边界

容器使用UID/GID 10001，禁网、只读根文件系统、只读任务包、cap-drop ALL、no-new-privileges、CPU 1核、进程数32、内存与swap同额。内存默认256MiB、范围64至1024MiB；超时默认10秒、范围1至180秒。工作流和模型调用者不能通过MCP请求修改这些参数，资源配置属于登记任务包。

/tmp是16MiB临时文件系统，输出目录是32MiB临时文件系统，不挂载宿主输出目录、Docker socket或敏感目录。默认单产物1MiB、总产物4MiB、最多16个文件、stdout与stderr各256KiB；可在登记时于既定上限内调整。容器监督器检查输出与日志，Docker日志另限制为16MiB单文件。输出超限后终止代码并返回output_limit；临时文件系统容量为额外硬上界，扫描检测存在短暂超出业务阈值的窗口。

产物由容器以受限JSON/base64传回，宿主检查相对路径、重复文件名、大小和总量后写入独立归档。符号链接、目录链接和特殊文件被拒绝。归档计算独立SHA256，重复读取回执时再次核对文件大小与哈希。容器数据和状态包均视为不可信代码证据，不作为数学审核或用户授权。

容器内监督器承担超时与普通子进程组清理，宿主另有截止时间；正常和已完成的异常运行读取结果后删除容器。结果先保存待发布回执，再清理并发布最终回执，便于恢复。保留了普通工具失败、未知派发状态和人工排查分支；不声称Docker隔离绝对安全。

## 返回语义

MCP外层 `isError=false` 表示工具完成了这次执行或状态查询。内层执行status区分succeeded、code_error、timeout、memory_limit、output_limit、unsafe_artifact和running。语法错误和缺依赖归code_error，并提供error_kind。它们是求解代码的执行结果，可供后续有次数限制的Coder修订策略使用，不能直接认为建模失败。

`isError=true` 表示请求、授权、审计、Docker基础设施或恢复状态有问题，提供invalid_request、not_found、authorization_error、infrastructure_error、execution_busy、outcome_unknown等可识别错误码。此类错误不能自动计入Coder代码失败重试。执行回执中mathematical_review明确为not_performed；成功求和测试不是正式赛题成功率。

## 验证与阶段边界

真实验收命令：`python -m scripts.verify_code_executor_mcp`，默认创建新证据目录，可用 `--output`指定未使用过的目录。它启动独立MCP客户端和服务进程，运行固定测试程序；代码中没有板凳龙算法、论文方法或正式求解。

覆盖正常输入读取和产物哈希、非root/禁网/只读输入与根目录/CPU/进程数设置、语法错误、缺依赖、超时、OOM、单文件/总输出/日志/文件数量超限、文件与目录符号链接、非法输入路径、重复调用、服务重启读取回执、默认拒绝验证任务、缺失镜像，以及派发后注入监控异常后的恢复。服务重启测试读取已完成回执；监控中断恢复是注入异常后由新执行器实例接管，不能表述为已实测所有运行中进程崩溃恢复窗口。

当前两项工具封装与C5工作流MCP接入已完成，C6整体故障演练已完成24项检查，最新完整回归151项通过，见[恢复说明](failure-recovery.md)。C→D不再强制新任务和空白建模会话（用户已取消），默认采用外部参考辅助建模，见[阶段门槛](../stage-c/next-stage-entry-requirements.json)；本次工程测试不代替该要求。


最终实测：**24项真实MCP→Docker检查通过，19次MCP工具调用，12个固定验证程序执行；完整回归119 passed、0 failed、0 skipped，46.96秒。** 原始记录在 `stage-c/runs/executor-mcp-final-20261106/`，汇总见[执行器验收摘要](../stage-c/c4-executor-verification-summary.json)。首次探测遇到Docker local日志驱动单文件与默认压缩不兼容，显式禁用日志压缩后用新任务重测通过；原未启动容器已核对身份后清理，失败记录保留。


C5已增加mcp-code-executor后端，绑定任务、版本、契约、输入与代码任务包哈希；授权检查读取已提交单一数据库快照，避免等待调用者持有的任务锁。工作流发布仍持任务锁并校验版本。真实双MCP集成17项检查通过，完整回归149项通过；见[C5说明](mcp-workflow.md)。

C6修复：status在监控退出后继续执行原超时截止检查，超期终止并清理；pending-result发布前核对任务包、run、代码与授权。恢复仍需显式status/resume，没有后台常驻扫描器。
