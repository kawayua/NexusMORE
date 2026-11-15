# Windows 服务与环境准备（F4）

本版提供私有开发准备包：一个 wheel、固定下载目录、校验锁及 bootstrap.ps1。支持 Windows x86_64、独立 CPython 3.13.5、PostgreSQL 16、Qdrant 1.19.1、Python 3.13 Docker 执行器、Pandoc 3.6.4、Tectonic 0.17.0。下载和工具存在不等于论文或独立审查通过，不支持其他 LaTeX 引擎、外置 BibTeX/Biber 和任意 TeX→Word。

## 主机需要什么

用户需要可运行 Linux amd64 容器的 Docker Desktop/WSL2，Harness 仍由用户负责下载。Windows 和所用中文字体须可用；Word 原生渲染需要已安装且获得许可的 Microsoft Word。当前准备器不静默安装 Docker/WSL2、不获取 Office 授权、不修改系统 Python、注册表或 PATH。普通模型调用还需要用户明确配置的模型端点、模型名和 key，准备环境不请求模型、不消耗推理额度。准备完成还会创建工作区 modelcrew.ps1 入口，新终端通过该脚本调用时自动选择本工作区；已有同名脚本保留，不覆盖。

Python 无需手动安装：bootstrap 从 python.org 获取固定摘要的可嵌入 Python，解压到用户工作区 configs/local/runtime/python313，并将固定 pip wheel 解压到其私有 site-packages，安装本项目全部生产 extra；使用 Python 的隔离路径，不依赖开发源码或外部技能目录。在线安装先选择 CPU torch 2.6.0+cpu，以保持当前 sympy/检索组约束；不自动选择 CUDA 或系统 Python。准备包本身不携带原生二进制、模型权重或许可证未明的资料，公开发布仍等待 F5。

## 首次准备

解压私有准备包，在其目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Workspace "D:\NexusMORE-workspace"
# 后续在工作区的私有 Python 中调用；不要求修改 PATH
$python = "D:\NexusMORE-workspace\configs\local\runtime\python313\python.exe"
$env:MODELCREW_WORKSPACE = "D:\NexusMORE-workspace"
& $python -I -m modelcrew environment status
& $python -I -m modelcrew doctor --profile workflow --services
```

首次联网涉及 Python ZIP、pip、Python 依赖（CPU torch 等较大依赖）、缺少的 Docker 镜像/构建依赖、Pandoc/Tectonic ZIP；首次真实 Tectonic 编译还下载宏包缓存。固定文件逐项验证大小与 SHA256，错误或未完成直接阻断，不回退其他版本。Tectonic 的 SHA 来自 GitHub 资产摘要、pip 来自 PyPI 摘要；Python/Pandoc 锁是从官方 HTTPS 文件建立的项目固定哈希，不冒称另有官方签名/摘要独立核验。镜像摘要沿用本机官方命名镜像 RepoDigests，镜像源/独立上游认证限制照实保留。

离线准备需预先取得目录锁列出的 Python/pip/Pandoc/Tectonic 文件、完整生产 wheelhouse、对应 Docker 镜像；如需文档离线编译还要先准备本机 Tectonic 缓存，不能把空缓存说成离线可编译：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Workspace "D:\NexusMORE-workspace" -Offline -ArchiveDirectory "D:\verified-downloads" -Wheelhouse "D:\wheelhouse"
```

只安装 Python/包可加 -SkipServices；有 Docker 后运行下方 setup。不覆盖已有 wheel/压缩包校验失败、配置或凭据以假装成功。业务配置文件和秘密保存在工作区 configs/local，不进入发行包。重复 bootstrap 保留业务数据；服务准备发现既有外部数据库或自定义 Qdrant 时拒绝自动接管，应选新工作区。准备步骤中断后保留失败文件和锁；确认原进程终止后才能处理遗留锁，不能让工具自动删除仍可能运行的操作。

## 独立服务与迁移

已有 Python 安装可先安装 wheel 的 workflow/paper 组，再使用同一入口：

```powershell
modelcrew environment setup
# 或分步
modelcrew environment prepare
modelcrew environment up
modelcrew environment migrate
modelcrew environment executor
modelcrew environment tools
modelcrew environment status
modelcrew environment restart
modelcrew environment stop
```

prepare 创建工作区哈希绑定的 Compose project、随机数据库密码、独立命名数据卷和仅监听 127.0.0.1 的端口。优先 55432/56333，端口被占用则首次选择空闲端口并冻结，更新本工作区 Qdrant 默认地址；重启不重选端口、不重置密码。并发端口抢占应明确失败后排查，不自动换库。历史 stage-b/stage-c 项目、容器和数据卷不改、不接管。配置/凭据哈希或所属工作区变化会阻断操作。stop 保留容器与数据卷，没有 down -v、删除卷、重置库或覆盖用户数据库的接口。

migrate 调用现有 Workflow.setup 与 PostgreSQL 锁，执行包内 12 项 SQL 和图检查点迁移，可重复执行，不授予业务批准。up/status 检查 Linux 引擎、真实 PostgreSQL 16 连接、Qdrant 1.19.1 健康。权限不足和引擎不可用须分别排查；Codex 沙箱访问 Docker 命名管道可能需要在沙箱外运行，本机 Docker 已启动不等于沙箱有权限。

执行器缺少默认镜像时，只用包内 Dockerfile 在新的独立构建目录构建，不把题目、密钥或整个工作区发给 Docker；离线缺镜像直接失败，自定义镜像缺失不回退默认。实际任务继续非 root、禁网、只读根和任务包、资源限制及原审批门禁。

## 本地权重与最小检索初始化

```powershell
# 固定 BAAI/bge-base-zh-v1.5 提交版本，首次约 409 MB 权重及配置，需要网络
modelcrew environment embedding
# 也可明确提供本地模型目录，复制到本工作区并记录文件身份；不冒称其上游已认证
modelcrew environment embedding --model "D:\verified-bge-model" --offline
modelcrew environment retrieval --output runs/retrieval-probe-v1
```

所有权重/配置进入用户工作区，按实际文件建立签名；缺件、下载失败、改动或签名不一致不能登记就绪。不覆盖已有模型配置。检索初始化用三段项目自编合成文字、真实本地 BGE 和本工作区 Qdrant，完成建库、身份标记和一次预期首命中查询；第一次且原 paper_config 为空时绑定新索引，否则保留原配置。这里仅为部署 smoke，不宣称生产语义质量、113 算法语义索引已建好或 F6 自动路由完成；候选来源也不等于真实性核验。

## 确认点与恢复检查

```powershell
modelcrew environment smoke --output runs/environment-smoke-v1
modelcrew environment restart
modelcrew environment recover --report runs/environment-smoke-v1/probe.json
```

smoke 使用全新合成输入与 pending-code 任务，停在 WAITING_MODEL_APPROVAL；不模拟用户批准、不运行真实模型、不求解实际赛题。另运行显式 verification 模式的受限执行器工程探针并存回执、写入独立测试向量。recover 在新进程读取同一任务/契约、向量与执行回执，核对仍待确认、无新增执行。工程运行不能替代 P1/P2、模型或结果批准。恢复范围为已有命名卷和工作区的重启/断进程持久化恢复，不是丢失卷后的灾难备份还原承诺。

## 文档真实探针与全页检查

```powershell
# 首次允许下载 Tectonic 宏包
modelcrew environment documents --output runs/documents-probe-v1
# 缓存准备后，另建输出目录检查离线编译
modelcrew environment documents --offline --output runs/documents-probe-v2
```

创建两页中文 TeX 工程探针和含原生 OMML 的 Word 探针，真实 Tectonic/Pandoc/Word 渲染后核对全部物理页数、生成每页预览、检查字体/越界/完整日志并保留哈希。所有 PDF 均须全页检查；实际逐页观察、独立 P2/W2 与用户批准仍分别执行，不把环境探针发布为论文。现有 Microsoft Word 或字体缺失明确阻断对应能力，不替换为未支持的渲染引擎。

本阶段验收应保存新工作区、隔离运行时、包/镜像/资料身份、实际平台、首次下载与离线行为、确认点及重启恢复证据。同一 Windows 主机上的全新独立 Python/工作区/数据卷不等于全新 Windows 虚拟机，也不证明没有系统组件、Docker缓存、Word或字体；全新机器及最终宿主端到端仍按实际证据另行记录。
