# 枢模 · NexusMORE

面向中文数学建模研究的本地工作流工具：从题目与附件出发，讨论建模方案，执行 Python 求解，审阅结果和中文稿，再生成正式论文。建模手、代码手和论文手共享版本化资料；独立质检和真实用户确认贯穿流程。

**当前状态（2026-11-19）**：`0.1.0.dev0` 开发线，现有 Windows / DSH 本地业务已按 [G 验收范围](docs/validation/g5-acceptance-20261119.md)通过。按用户决定，本轮先完善使用与贡献文档；干净环境和新设备由用户在开源后补测，目前未验证。其他宿主与系统的兼容性尚无通过结论。当前没有公开包下载承诺，整体公开发行核对仍单独进行，详见[兼容与限制](docs/compatibility.md)。

## 开始前

准备 Windows x86_64、CPython 3.13、可运行 Linux amd64 容器的 Docker Desktop/WSL2，以及 DSH Desktop 0.2.2-rc.1。DSH 自带 Python 3.12 不适合作为本项目后端。模型服务的端点、具体模型名和密钥由使用者配置；图像质检另需相应模型支持图片输入。Word 原生渲染需要本机已安装并获许可的 Microsoft Word。

下面以取得的本项目源码目录为起点，在 PowerShell 中执行。命令已与当前代码入口核对；新设备完整安装尚待实测。

## 安装与初始化

```powershell
py -3.13 -m venv .venv
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python -m pip install ".[paper,dsh]"
$env:MODELCREW_WORKSPACE = Join-Path $env:LOCALAPPDATA "NexusMORE\workspace"
& $python -m modelcrew init
& $python -m modelcrew resources-check
```

`nexusmore` 是发行名，`modelcrew` 是 Python 包名和命令。没有 `py` 启动器时，用实际 CPython 3.13 的 `python.exe` 路径创建虚拟环境。安装依赖需要联网，`paper` 组包含论文与检索所需的较大依赖。若已有受审核的本地 wheel 或准备包，使用[安装包说明](docs/package-installation.md)或[环境准备说明](docs/environment-preparation.md)中的对应入口；不要求从未发布的 PyPI 包安装。

在工作区的 `configs/local/settings.json` 中填写 `model.provider`、`model.base_url` 和 `model.name`；密钥写入同目录的 `secrets.env`，变量名对应 `model.api_key_env`（默认为 `MODELCREW_LLM_API_KEY`）。不要把密钥、数据库口令或私有题目提交到仓库。更多配置及优先级见[用户配置](docs/user-configuration.md)。

```powershell
& $python -m modelcrew environment setup
& $python -m modelcrew.workflow_mcp migrate
& $python -m modelcrew doctor --profile workflow --services
```

`environment setup` 会准备工作区独立的 PostgreSQL/Qdrant 服务、迁移、执行镜像及文档工具，可能下载较大镜像和工具；首次使用前先启动 Docker。它不安装 Docker、DSH、Word 或模型密钥。默认内置算法查询不需要向量模型；论文向量检索需另按[环境准备说明](docs/environment-preparation.md)配置权重及索引。诊断通过不等于已经完成建模或论文审查。

## 接入 DSH 并开始任务

继续使用上面的 `$python` 和工作区；新开终端时重新指定这两项。

```powershell
& $python -m modelcrew.dsh_integration render --python $python --workspace $env:MODELCREW_WORKSPACE
& $python -m modelcrew.dsh_integration install --python $python --workspace $env:MODELCREW_WORKSPACE --profile "$env:USERPROFILE\.dsh\profiles\desktop"
```

`--profile` 应指向自己正在使用的 DSH profile；已有注册且配置未变时可直接打开原会话。安装器遇到同名冲突或被修改的管理块会拒绝覆盖，处理方法见[排错指南](docs/troubleshooting.md)。完整退出并重启 DSH，在输入框运行 `/nexusmore` 检查连接。

连接后附上自己的题面和全部所需附件，说明本次研究范围，例如：

> 请使用枢模处理附件中的问题一。先列出输入缺项、建模方案和检验口径，等我确认方案后再进入求解。

审阅时打开回复所附的文件。确认当前方案或结果后，在原会话明确回复“通过”；需要调整则直接提出修改意见。正文与配图同时待审时，合并审阅页展示完整正文和全部候选图，标明暂列入文图与备选图；一次确认同时绑定当前正文与暂列配图。正式导出及独立 W2 仍在后续执行，详见[日常使用与恢复](docs/user-guide.md)。

## 文档与贡献

| 入口 | 内容 |
|---|---|
| [使用指南](docs/user-guide.md) | 配置、任务流程、审阅、产物位置与恢复 |
| [兼容与已知限制](docs/compatibility.md) | 本地实测范围、待验证环境、工具与模型边界 |
| [排错指南](docs/troubleshooting.md) | 安装、服务、DSH、确认、恢复和导出问题 |
| [架构说明](docs/architecture.md) | 三手、独立质检、共享业务状态与宿主边界 |
| [贡献指南](docs/contributing.md) | 开发环境、无需私有数据的检查、提交与问题报告 |
| [首发候选准备](docs/release-preparation.md) | 本地构建、包清单、扫描结果及发行待办 |
| [更新记录](docs/changelog.md) / [历史导航](docs/history/project-progress.md) | 当前变化、阶段报告和保留的旧首页 |

## 许可与使用边界

当前组合发行（含 PyMuPDF）采用 [AGPL-3.0-only](LICENSE)，第三方与既有授权按[第三方声明](THIRD_PARTY_NOTICES.md)及[组合发行说明](docs/combined-distribution-license.md)保留。软件按许可证提供且不作担保。私有输入、模型密钥、研究档案及历史成品不属于默认发行内容。开源准备、实际公开发布与新设备测试是分别记录的事项。
