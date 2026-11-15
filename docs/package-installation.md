# 统一安装包与安装验证

2026-11-14：F4 新增私有 Windows 准备包与 bootstrap.ps1：可自动准备隔离 CPython 3.13.5、全部生产 extra、独立 PostgreSQL/Qdrant、迁移、执行器与固定版本文档工具。核心 wheel 的最小依赖约定不变，准备包组合使用全部所需组。详见[服务与环境准备](environment-preparation.md)；Docker/WSL2、Harness、Word授权及全新机器验收边界仍照实保留。

2026-11-14 F3：新增统一用户配置、`modelcrew init`、脱敏 `config-show` 与分级 `doctor`。安装包默认写入 %LOCALAPPDATA%/NexusMORE/workspace，支持 MODELCREW_WORKSPACE 或全局 --workspace；数据目录留在工作区内，历史开发根和批准记录保持兼容。首次使用先 `modelcrew init`，明确填写模型端点、模型名和 key 后按所需依赖组诊断。详见[用户配置与初始化](user-configuration.md)。该入口不安装原生工具、不启动 Docker 服务、不发模型请求，F4及后续业务/宿主验收仍需分别完成。

2026-11-14 F2收口：本版私有开发安装包以219项资源、七组生产安装依赖（含核心）及A/B/C声明知识基线完成最终汇总验收。冻结候选位于tmp/package-closure-validation-20261114/frozen-build，见[收口汇总](release/package-closure-summary.md)与[验收回执](release/package-closure-20261114.json)。以下分批“尚未完成”描述为当时状态。F3配置/初始化、F4环境与服务、F5公开发行许可、F6路由以及G/H另行验收；本次没有公开上传或批准正式论文。

2026-11-13：F1 已收口，按用户要求进入 F2。本页记录私有开发安装包范围；整体 F2、完整知识内置和公开发布尚未验收。历史批准、来源文件和 F1 冻结证据保持原样。

## 安装与 CLI

当前 F2 开发安装包的实测平台为 Windows x86_64、CPython 3.13。发行名 `nexusmore`，导入包及命令名 `modelcrew`，开发版本 `0.1.0.dev0`。这是实际构建并安装验证过的第一批安装包，不是模拟尝试，也不是最终完整产品的依赖承诺。核心安装仅声明 JSON Schema 验证所需依赖，可启动 CLI、检查资源并验证部分契约；完整业务需要后续补齐对应依赖和初始化。当前 Python 包不会自动安装数据库、Docker、模型服务、Node 或原生文档工具，并不表示完整流程不需要它们，也不表示最终都要用户手动安装。

2026-11-14：用户明确“ok 那就明确这版 同意安装包的审核”，当时的私有开发安装包（`tmp/package-installation-20261113/verified-build`）审核通过；当时已验证核心和 `workflow` 组及资源读取，整体 F2、完整知识和完整业务流程仍未验收。批准绑定已构建产物及原实测回执，见[本版审核记录](release/package-installation-approval-20261114.json)。本页后续说明不改变原产物或历史实测回执的字节与哈希。

后续交付按本次确认执行：PostgreSQL 和 Qdrant 统一通过 Docker 部署，由枢模逐步提供初始化、启动、健康检查和恢复入口，减少手动操作；当前模板已携带，但统一自动部署尚未实现。沿用当前方案时 Docker Desktop/WSL2 是用户机器的运行前提，不能声称枢模已自动安装。Harness 的下载与安装由用户自行负责，不纳入枢模安装包；真实宿主接入仍须后续验证。Python 及项目依赖以随包携带或自动准备为最终目标，不能将 CPython 3.13 的后端版本要求等同于永久要求用户手装 Python。在线模型调用只需配置 Key、接口地址和模型，无需安装本地模型服务；Node 按真实宿主方案决定是否需要，原生导出工具则按许可与支持范围继续补齐准备方式。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install path/to/nexusmore-0.1.0.dev0-py3-none-any.whl
.venv/Scripts/modelcrew.exe --version
.venv/Scripts/modelcrew.exe --help
.venv/Scripts/modelcrew.exe resources-check
```

`resources-check` 核对资源清单的字节数与 SHA-256，不连接数据库或模型；通过仅表示已声明资源完整，不表示算法全文齐备、第三方授权通过、实际工具已接通或用户已经批准论文。

| 可选组 | 用途 | 额外前提 |
|---|---|---|
| `workflow` | 持久化编排、三手模块、执行器客户端及算法卡片接口所需 Python 依赖 | 用户配置 PostgreSQL、模型与 Docker；不自动部署服务 |
| `retrieval` | 检索服务与向量嵌入 | Qdrant、模型权重与索引另行初始化；可能下载较大依赖 |
| `documents` | 文档解析、只读画像和工程检查 | 本批独立安装、DOCX 结构/成员保全、XLSX 完整读取和 PDF 全页检查通过；原生 Word 渲染另验 |
| `figures` | Python 绘图及 PDF 读取 | 本批独立安装及三格式/全页 PDF 工程检查通过；独立质检与用户确认继续按契约执行 |
| `paper` | 既有登记导出链的 Python 依赖集合，含检索 | Tectonic 0.17.0、Pandoc 3.6.4 和受支持 Word 环境另行配置；仍须原审批流程 |
| `evidence` | 数值与统计核验 | 本批独立安装、已知解析值数值/符号核对通过；不自带旧题结果或历史批准 |
| `dev` | 测试与构建 | 开发用，不属于运行依赖 |

例如以已安装版本添加编排依赖：`python -m pip install "nexusmore[workflow]==0.1.0.dev0" --find-links path/to/wheel-directory --no-index` 仅适用于已备齐依赖的本地 wheelhouse；首次联网安装应去掉 `--no-index` 并使用受控索引。也可直接给本地 wheel 路径附上 `[workflow]`。2026-11-14已在两个全新虚拟环境分别安装并验证 `retrieval` 和 `paper` 的Python依赖；实际服务部署、生产模型语义质量、完整论文资料及正式审批是另外的验收范围。

## 包布局与受控内容

资源经 `modelcrew.package_resources.resource()` 或 `project_assets` 访问，不靠工作目录寻找运行资源。清单枚举 contracts、12 项迁移、执行器沙箱、项目自编规范、算法索引与现有章节、论文政策、LaTeX 资源，以及 126 项固定版本官方文档工具和原许可证。F2 新增受控携带自编 JS 模块及 package.json、运行镜像 Dockerfile、PostgreSQL/Qdrant 部署模板、Word 渲染脚本和第三方声明。资源数量以当次清单及构建回执为准；F1 的 193 项快照不重写。

JS 是包内 `resources/harness/nexusmore-workflow.js` 的 ESM 资源，`package.json` 保持 private。它只有既有 API 的业务映射和注入式传输边界，不是可直接安装到 DeepSeek Harness 的完整插件，也不另行发布 npm 包；G 阶段实现并验证真实宿主注册与传输。复制版与自主源文件逐字核对。

正式登记导出改为调用包内 `modelcrew.paper_export` 与 `modelcrew.paper_render`；Word 适配脚本也从资源 API 定位。原 `scripts` 入口保留供历史记录追溯。本次不改变正文、选图、W2、导出审批或工具警告准入。部署模板保留既有卷名用于恢复核对，F4 再建立新用户初始化与部署验证，不在 F2 更名或自动启动数据库。

不打包原上游待授权资料、外部技能目录、`.env` 密钥、用户运行数据、向量索引、历史冻结材料、模型权重、原生工具缓存或虚拟环境。整体项目仍为 `Private :: Do Not Upload`，本次未选择或授予整个项目的开源许可证。

## 构建与证据

```powershell
python -m scripts.build_distribution --output tmp/package-installation-20261113/build
```

命令使用已安装的 setuptools 构建 wheel/sdist，不声称使用隔离构建环境；输出目录必须新建。校验 wheel 与源码白名单逐字一致、清单资源的哈希与数量、Private 元数据，并从安全解包的 sdist 再构建 wheel，重复检查。日志、两个 wheel、sdist 与 `build-audit.json` 写入本次证据目录，不上传任何包。依赖解析与安装另外在不继承系统 site-packages 的虚拟环境中实际执行，结果另记。

## 后续边界

完整七类算法说明、完整数学论证和中文论文资料尚待 F5 授权或独立编写后补入 F2；现有索引、规范、卡片和模板不冒充完整知识。`paper_layout` 对尚未授权内置的旧论文参考资料仍可能报告缺失，不能据此绕开。F6 负责自动选择、实际读取与执行路由。

F3 仍须统一用户工作区/数据目录；当前安装态 `config.ROOT` 是安装位置，核心只读检查可运行，但持久化业务写路径尚不能当作新用户 Quickstart。F4 验证服务与干净机器完整运行、暂停恢复，G 验证 DeepSeek Harness，H2 验证最终端到端业务。包能安装、模块能导入与完整业务准入分别留证。

## 文档、绘图与数值核验批次（2026-11-14）

`documents`、`figures`、`evidence` 已分别在三个不继承系统依赖的 Python 3.13 虚拟环境中安装，并从源码目录外运行真实工程探针。修复 `documents` 缺少 python-docx/PyMuPDF、`evidence` 缺少 openpyxl/pydantic 的声明，三份安装依赖清单同步更新；运行代码、200 项资源及原始工具字节未改动。新候选位于 `tmp/optional-dependencies-20261114/verified-build`，不覆盖或继承此前通过审核的安装包批准；[本批实测回执](release/optional-dependency-validation-20261114.json)保存独立环境、日志、来源与产物哈希。

文档实际验证了已注册 DOCX 结构校验、只读样式画像、DOCX/XLSX 成员逐字不变重打包、36 行表格完整读取、PDF 表单及结构读取和三页 PDF 完整检查；编辑过的工作区和缺最后页的报告被拒绝。绘图验证完整 CSV 数据、PNG/PDF/SVG、300 dpi、独立灰度图、重复导出字节一致及全页 PDF 检查，错误源哈希与过小文字被拒绝。数值探针核对积分 1/3、平方根残差、线性方程已知解、一个样本 t 检验的对称恒等场景及符号化简；非有限输入被拒绝。这些是固定合成输入的工程验证，不是用户题目求解、统计前提判断、自动证明或独立质检通过。

本批最终输出 5 份 PDF 共 11 物理页，均完整检查、预览并保存哈希；实际核看了 4 张不同内容的页图，字节相同的复制 PDF/重复导出按源与预览哈希核对。探针保留 `visual_review=PENDING`、`independent_review=NOT_RUN` 和 `formal_approval=false`，实际工程页图观察不代论文审图或 W2。首轮发现 python-docx 默认模板缺少 schema 要求的 zoom percent，正式校验正确拒绝；仅修正合成探针输入，不放宽校验或修复用户原件。

复现某一组时，先将该组安装到独立虚拟环境，再在源码目录外用该环境的 Python 执行：

```powershell
<venv>/Scripts/python.exe -I <repo>/scripts/probe_optional_dependencies.py --group documents --wheel <candidate.whl> --output <new-output-directory>
```

替换 group 为 `figures` 或 `evidence`；必须使用新输出目录。检索和论文组仍未整组验收；OCR、公式重算、修订合并、原生 Word 渲染、中文字体覆盖及完整正式导出不在本批通过范围。F3 用户数据目录、F4 Docker 服务初始化/恢复、F5 完整知识授权或独立编写、F6 自动路由和 G/H2 宿主与端到端仍按原边界继续完成。

## 检索与论文组补充验证（2026-11-14）

两个全新Windows x86_64/CPython 3.13虚拟环境从私有wheel安装，关闭用户/全局包与源码路径；包内模块、200项资源逐字节核对并执行pip check。检索实际通过本地随机小型BERT、项目嵌入适配器、Qdrant持久化/重开、重复入库、过滤、同题排除、模型指纹拒绝、MCP核心返回及引用档案。测试权重自行生成且禁联网，不代表真实BGE权重的语义质量或Docker服务部署通过。

论文Python组导入、Tectonic 0.17.0真实缓存编译、两页PDF完整检查、Pandoc 3.6.4生成原生OMML公式的Word和AST通过。Word COM渲染被沙箱拒绝（E_ACCESSDENIED），提权重试又受本次产物读取权限限制，因此原生Word到PDF仍标记受阻，不能称为完整导出通过。所有成功生成的PDF均全页预览、检查并保存哈希；工程观察不替代独立W2或用户批准。

前一批验证时缺少五份必读论文参考文件，当时完整writing_context与正式论文导出被阻断；依赖安装本身不能解除资料或审批要求。当前资料补齐情况见下一节。完整知识的15项补充包见[针对性清单](knowledge-supplement-checklist.md)，本批仅盘点，不复制未授权原文或代用户确认内容。结果见[验证回执](release/retrieval-paper-validation-20261114.json)。新候选位于 `tmp/retrieval-paper-validation-20261114/verified-build`；此前批准仍只绑定原基线。

## 中文论文资料补齐（2026-11-14后续批次）

已独立编写四份中文章节/写作/论文格式/LaTeX规范及一个完整中文研究模板，资源从200增至205。当前workflow 1.3.0实际读取五份1.0.0资料；写作上下文和版式契约不再因这五份文件缺失而阻断。新文件使用英文用途名，新模板位于paper/templates/chinese-research/main.tex，旧中文参考名与旧reference/main.tex继续历史映射。原始受限来源和此前通过包/回执保持字节。

本批仅完成自编论文资料及工程接入，见[资料与验证](paper-knowledge.md)。前一批记录的缺资料是当时状态；当前仍待原生Word渲染环境验收、实际任务正文/选图批准与独立W2，以及后续完整业务验收。完整知识还缺七类算法和三类数学资料。新私有候选为tmp/paper-knowledge-validation-20261114/validated-build，未代用户批准或公开上传。

## 2026-11-14 算法资料候选更新

新增七类独立算法资料、规范目录和组合交接说明，资源205→214，规范算法113个，对应来源方法123条。只读资料支持核心安装；固定数值案例使用已有evidence组，65个小问题完整解与其余组件/更新/随机估计明确区分。当前候选为tmp/algorithm-knowledge-validation-20261114/validated-build，旧论文资料候选和最初用户批准保持原字节。当前完整知识剩B1—B3，先前章节的七类缺口描述为当时状态；F6路由/生产后端和其他阶段仍另验。见[算法资料与验证](algorithm-knowledge.md)。

## 2026-11-14 数学资料候选更新

新增B1—B3独立数学资料及目录/索引，资源214→219，共39个专题和固定案例。核心安装只读；复算沿用已有evidence组（NumPy/SciPy/SymPy），没有新增Python依赖或外部技能安装。当前候选tmp/mathematical-knowledge-validation-20261114/validated-build，旧包批准和历史候选保持原字节。原15项知识清单均有声明范围基线，F2整体和F3/F4/F5/F6仍另验，不把数学核算说成自动证明、统计前提确认或独立审查通过。见[数学资料与验证](mathematical-knowledge.md)。
