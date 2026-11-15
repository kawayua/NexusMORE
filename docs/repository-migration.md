# 仓库迁移与历史路径恢复

2026-11-11 收口更新：用户已确认 F0 收口并进入 F1。目录迁移、资源定位、旧引用和历史恢复按实际证据完成；下面各批记录保留其执行时状态。新增收口记录见 [迁移收口](migrations/layout-closure-20261111.json)，后续范围见 [发布范围](release-scope.md)。资料许可、完整知识内置及干净环境完整链路转入 F1/F2/F4/F5/F6/H2，不作为本次迁移未完成项。

2026-11-11，F0 已完成首批历史材料迁移、源码 `src` 布局、服务配置迁移及新运行目录解耦。完整迁移尚未完成：阶段档案、其余资源、运行数据旧路径适配、资料许可和最终安装验证仍待收口。

## 本批范围

| 原路径 | 新位置 | 处置 |
|---|---|---|
| `integrations/document_tools/` | `src/modelcrew/resources/document-tools/`（经包内中间位置迁移） | 126 个固定版本上游文件及来源清单逐字节迁移，实际入口改用包资源 API |
| `modelcrew-agent-plan.md` | `docs/history/modelcrew-agent-plan.md` | 原件不变；当前导航另生成 `docs/roadmap.md`，只修正相对链接 |
| `stage-a-preparation-checklist.md` | `docs/history/stage-a-preparation-checklist.md` | 原件字节不变 |
| `stage-a-2024-figure-check.png` | `docs/history/assets/stage-a-2024-figure-check.png` | 原件字节不变 |

`configs/repository-layout.json` 登记的四十四份 relocation 记录逐文件保存原路径、新路径、字节数、SHA-256 和用途；其他审计/执行记录不作为重定位映射加载。`runtime-paths-20261111.json` 是尚未迁移的37处源码候选引用，不是执行记录。工具迁移备份包含6个当时存在的 Python 缓存文件；缓存只记入本地备份，不作为发行资源，公开映射只记录127个实际资源文件。

迁移前的独立备份位于忽略目录 `tmp/repository-relocation-20261111/`，按 `document-tools`、`project-plan`、`preparation-checklist`、`figure-check` 分组，每组保留原路径和完整清单。源文件在移动前、备份后和新位置均核验身份。没有改写原来的第三方来源清单、批准回执或论文。

## 检查与兼容边界

```powershell
python -m scripts.verify_repository_relocations
python -m scripts.check_repository_layout
python -m scripts.check_repository_layout --final
python -m modelcrew.document_tools verify
python -m pytest -q -p no:cacheprovider
```

第一项当前核验44份记录的65666个映射项及精确旧路径解析（含文档工具两段迁移，不是65666个不同最终文件）。普通目录检查使用一次冻结的旧阶段文件路径哈希列表：允许现存文件，但拒绝新增阶段路径和根目录散落产物。`--final` 不接受历史阶段或过渡布局豁免，当前应失败；普通检查通过不能表述为F0完成。`pytest.ini` 将默认收集范围限定为当前 `tests/`，防止再次收集历史源码快照、临时依赖和权限受限的旧测试目录。`tests/conftest.py` 在未显式指定basetemp时分配全新 `tmp/pytest-<uuid>`，满足工作区路径边界并避免覆盖旧证据。

`modelcrew.repository_migration.resolve_repository_path` 只使用 `configs/repository-layout.json` 登记的精确文件映射。匹配旧路径时核验新文件原始哈希，支持多批连续迁移，但每段必须保持同一哈希；拒绝越界、链接、重复或循环映射、原路径与新映射同时存在，以及未登记版本快照的目标字节变化。两个 D 验收审计维护入口已接此解析，证据字典仍使用原逻辑路径；现存验收材料没有重跑或重签。此机制不是整个数据库或任意历史脚本的透明兼容层，未接入调用方需逐一处理。

工具目录通过 `importlib.resources.files` 定位，在需要执行配套脚本时由 `as_file` 保持完整目录可用期。已用源码树之外的隔离子进程从 ZIP 包读取并核验126个文件及三种指南/许可；这仅验证资源定位，不等于 wheel/sdist、所有系统依赖或自动路由通过。

## 中断恢复与回滚

准备入口 `python -m scripts.prepare_repository_relocation --help` 只生成清单及独立备份，不自动搬移。若准备后中断，先确认新旧位置，按记录分别验证，不能盲目重复移动。若只完成部分文件移动，逐文件核对已存在位置与原始SHA-256；同一文件两处并存、两处缺失或任一处哈希变化均转人工核查，不能用覆盖操作解决。

回滚单批时先停止会写相关文件的命令；核验新位置和备份均与清单相符，确认旧位置尚不存在。只对明确列出的源/目标使用本机 PowerShell `Move-Item -LiteralPath`，且先检查两个解析后的绝对路径均在仓库内，不整树覆盖或递归删除。恢复原文件后，同时恢复该批入口/文档路径和迁移注册；原位置重新核验全部字节。若移动后的当前入口或导航已有编辑，先另存新版本，不覆盖这些编辑。回滚动作须使用新的执行记录，不能删除旧迁移证据。

## 环境与恢复核验

数据库只读审计入口：

```powershell
python -m scripts.audit_database_paths --output tmp/repository-database-paths-new-version.json
```

该入口使用 PostgreSQL 只读、可重复读事务，不构造 Workflow、不运行迁移、不写检查点、不推进任务；仅记录表/列计数、匹配值摘要和阶段路径词元。它不涵盖检查点二进制或外部服务。2026-11-11 首批实施时，本机连接在沙箱内外均超时，未获得数据库核验结果；当时未检测到 Docker 命令或常见安装位置。该次失败证据仍保留。用户随后启动 Docker，连接已恢复，最新实测见下文；不能用连接成功代替完整迁移与暂停恢复验收。

Word结构专项检查目前缺少声明中的 `defusedxml`，按原有行为返回阻断，测试明确跳过；PDF和表格专项检查实际运行。文档工具目录迁移与完整正式论文导出仍为不同验收项。

本批验证记录：专项36通过、1跳过；完整回归564通过、141跳过。回归运行后新增的盘点资源分类用例由专项覆盖。执行回执为 `migrations/execution-20261111.json`；初次收集/临时目录失败与修复后的报告分别保留，不将失败报告覆盖为成功。


### Docker启动后的复核（2026-11-11）

用户启动Docker后，PostgreSQL连接成功，容器healthy，Qdrant运行中，Docker引擎29.6.2。只读审计覆盖24张包含文本/JSON列的业务表、67,243行，提取15,207个不同阶段词元；其中包含任务标识与正文引用，不能当作同数量的可移动文件。原失败输出未覆盖，新审计证据为 `tmp/repository-database-paths-20261111-v3.json`。

继续通过只读连接查询最新E汇编和构建，没有运行Workflow.setup、advance、求解或导出。当前返回 `STALE_INPUTS` / `STALE_BUILD`：`docs/three-hand-collaboration.md` 的F/G/H路线内容与E冻结上下文不同。该文件当前哈希与F0首轮盘点一致，差异早于首轮F0盘点；本批未修改该文件，不能把现存状态差异归因于本批目录迁移，也不能通过更改旧哈希消除。

实际核验最新构建封存文件和汇编输入快照共827项，哈希全部一致；现有文件级正文审阅与选图审阅均为approved。这个结果保护历史交付身份，不代表当前上下文的运行检查已通过。连接阻断已解除；后续迁移仍需按实际调用方接入旧路径映射，并分别验证当前上下文状态与历史冻结材料恢复，不自动重绑或代用户重新批准。新执行记录见 `migrations/database-resume-20261111.json`。


## F0继续实施：源码、运行目录与部署配置

源码和已审查的文档工具资源已从 `modelcrew/` 逐字节迁至 `src/modelcrew/`；该批182文件单独备份，生成缓存不作为迁移身份或发行资源。第一批工具清单保留原字节，通过哈希一致的精确映射链解析最终位置，未重写旧清单。代码在本批迁移前完成必要接口调整，迁移后校验通过。

新三手运行写入 `runs/hands/<uuid>`、建模运行写入 `runs/modeling/<uuid>`，新汇编输入/构建分别使用 `runs/assembly-inputs/<uuid>`、`runs/assembly-builds/<uuid>`。已有UUID目录通过集中兼容表回读原位置，不移动数据库行、不修改原绑定字符串。新旧位置并存或UUID非法时拒绝继续。`MODELCREW_DATA_DIR` 可指定工作区内的独立数据目录；当前工件准入仍以工作区为边界，暂不接受工作区外目录，也不允许指向源码、资源或历史阶段目录。允许外部数据根需要F3整体扩展准入，不能只放宽一处路径检查。

PostgreSQL/Qdrant配置已迁到 `configs/services/postgres.yaml`、`configs/services/qdrant.yaml`。本机真实数据库配置逐字节迁到已忽略的 `configs/local/database.env`，备份和清单仅存于tmp；不将密钥写入公开记录。配置优先级是数据库URL环境变量、显式配置文件、当前本机配置，最后才是尚未迁移工作区的旧配置兼容；两种默认文件并存时阻断。`python -m scripts.start_database --check-config` 仅校验配置；启动命令明确保留原Compose项目名，旧维护入口转发到新入口。

对实际运行容器执行只读核对，确认数据库与Qdrant的数据卷名称均与新配置一致，未重启服务、未建立空数据库。真实数据库上的46项三手编排测试使用显式合成模型和执行器回复，不调用收费模型、不对真实论文代签；测试任务新建并与正式任务隔离。

新增 `pyproject.toml` 仅作为本机开发安装骨架，声明Private禁止上传；未选择项目开源许可证，未冻结完整依赖组。当前Python用户环境已完成无下载、无依赖变更的可编辑安装，继续使用 `python -m modelcrew`。另构建一个实际wheel并装入隔离目录，在源码树之外核验文档工具126个原始资源全部匹配，包中无本机env、参考原文或缓存。这个检查不代表完整工作流已可独立安装：contracts/paper/algorithm/执行器等其余资源和系统依赖仍须按F1/F2/F5处理。

最新验证：非集成全量581通过、141跳过；真实数据库三手测试46通过；后续盘点分类增补由44项专项通过覆盖。所有源代码及迁移链身份检查通过。旧阶段目录尚未全部归档，最终目录检查仍应失败，不登记F0完成。

## 历史交付与当前上下文分开核验

```powershell
python -m scripts.verify_historical_assembly --project stage-e-generic-assembly --build 782dde15-590a-40a6-88f5-f7c8d7b6e4d6 --output tmp/historical-build-new-version.json
```

这个新入口使用数据库只读事务，从构建原封存清单、汇编输入快照和原始写作上下文核验旧交付，并按冻结的论文规则检查原正文/选图审阅绑定。当前E交付827项全部通过，原审阅均approved；`current_context_matches_frozen=false` 如实反映此前路线文档变更。返回 `can_export_current=false`，不创建新审批，不更改运行状态；不能将它作为新的导出准入入口。

此分离解决了“旧交付因当前路线更新而无法核验”的问题，不需要把新文档伪装成原批准输入，也不让已知上下文差异阻断仓库整理。当前任务准入继续执行原有严格规则，任何新稿或新导出仍须满足对应确认与审查要求。


## 算法检索逐批迁移（2026-11-11）

本批将 `stage-c-plus/algorithm-catalog.json` 逐字节移至 `runs/algorithm-retrieval/catalog.json`；旧索引配置逐字节保存到 `archive/research/retrieval-config/algorithm-index-20261111.json`，另建当前配置 `runs/algorithm-retrieval/index.json`。新配置仅修改 `catalog_path`，BGE位置、Qdrant地址、嵌入签名、集合和目录内容哈希全部沿用。未重建集合、下载模型或修改算法资料原文。

默认配置统一由 `modelcrew.retrieval_paths` 解析，优先级为显式路径、`MODELCREW_ALGORITHM_CONFIG`、`MODELCREW_DATA_DIR` 下的 `algorithm-retrieval/index.json`（数据根默认 `runs/`）。算法检索器、协作检索、建模手与MCP初始化均已接入；MCP子进程传递数据根配置。默认文件缺失直接报错，不静默回退阶段目录。显式指定旧配置路径时按登记映射读取归档，配置中的旧目录路径同样解析到新目录文件。

维护入口改为 `python -m scripts.index_algorithms` 和 `python -m scripts.prepare_algorithm_catalog --read-log <来源清单>`；保留旧命令转发兼容。已有目录或配置拒绝覆盖，需指定新版本输出。旧准备入口仍显式读取历史来源清单，这是追溯入口，不能视为全部来源资料已迁移。

本批需要修改此前已迁移的六个源码文件。修改前将原字节保存在 `archive/research/source-snapshots/algorithm-retrieval-20261111/`，通过独立 `revision_records` 登记原路径、哈希及快照；原源码迁移清单未改写。解析旧源码路径时按原身份返回核验后的快照，直接读取当前源码路径仍得到当前版本。未登记的内容变化、快照损坏仍拒绝。快照与本机运行数据均属本地保留材料，不能据此宣称干净克隆已携带完整历史恢复材料或取得资料发行许可。

验证结果：专项101通过；完整回归586通过、141跳过；9份重定位记录的316项身份核验通过，迁移防回退检查通过。真实本地BGE/Qdrant查询，以及无显式算法配置、无算法配置环境覆盖的stdio MCP查询均命中原集合。历史E交付827项仍通过，原正文与选图批准不变；当前上下文差异仍如实保留，未获得新的导出准入。证据索引见 `migrations/algorithm-retrieval-execution-20261111.json`。其余阶段档案、论文检索默认路径及资源迁移另批处理，F0尚未完成。


## 后续第一批：论文检索索引配置（2026-11-11）

本批将 `stage-c/runs/retrieval-index.json` 原字节迁至 `runs/paper-retrieval/index.json`，原模型位置、嵌入签名、语料哈希和Qdrant集合保持不变。迁移前完整备份位于 `tmp/repository-relocation-20261111/paper-retrieval-index/`，映射为 `migrations/paper-retrieval-index-20261111.json`。旧配置路径显式传入时按精确映射恢复；默认读取不回退阶段目录。

新增统一 `paper_config_path`，优先级为显式配置、`MODELCREW_RETRIEVAL_CONFIG`、数据根下的 `paper-retrieval/index.json`；数据根默认 `runs/`，支持现有 `MODELCREW_DATA_DIR` 工作区边界规则。直接检索、MCP预加载/查询及 `python -m modelcrew.retrieval index` 均使用同一定位方式。索引命令在加载模型或写向量前拒绝已有配置，允许缺失的用途目录自动创建；仍以独占方式保存新配置。

此前源代码迁移身份另通过 `paper-retrieval-source-revisions-20261111.json` 保留原 `retrieval.py` 快照，其他已调整模块沿用上批原身份快照；旧哈希与批准未改写。本批修改前的调用方版本还单独备份至 `tmp/repository-relocation-20261111/paper-retrieval-callers/`，供本批回滚使用。

后续批次边界：下一批核对并处理检索日志/引用档案（含旧引用编号恢复）；再处理执行器挂载和工具发现；其余阶段冻结运行、资料和历史导航逐项迁移。本批不移动这些目录，也不登记F0完成。实际检查结果与证据索引见 `migrations/paper-retrieval-batch1-execution-20261111.json`。

本批验证：专项36通过；完整回归589通过、141跳过；10份迁移记录317项及目录防回退检查通过。4条固定查询在直接检索和真实独立MCP进程中全部通过（共8项），无配置覆盖，集合仍为原81点。历史E的827项及原正文/选图批准有效，未授予当前导出。首次探针仅在查询后清理连接阶段使用了客户端不支持的上下文管理语法，保留v1日志；v2改为显式关闭连接后另目录重跑通过，无业务代码因此变更。


## 后续第二批：检索日志与引用档案（2026-11-11）

| 原位置 | 新位置 | 范围 |
|---|---|---|
| `stage-c/runs/references/` | `runs/references/` | 23份档案原字节迁移，保留原编号及调用绑定；当前新增引用继续写此用途目录 |
| `stage-c/runs/mcp/` | `archive/research/retrieval-logs/20261111/` | 82份已有日志原字节封存，后续不追加；新日志写 `runs/logs/mcp/` |

两组移动前清单及完整备份分别在 `tmp/repository-relocation-20261111/reference-archive/`、`mcp-log-archive/`。公开精确映射为 `migrations/reference-archive-20261111.json` 和 `migrations/mcp-log-archive-20261111.json`；引用内容及日志本身不因迁移取得发行许可，继续为本机数据/档案。数据库中的原引用编号、快照和批准绑定未迁写。

`reference_directory` 与 `mcp_log_directory` 统一默认定位，支持现有工作区内 `MODELCREW_DATA_DIR`。论文MCP采用新默认位置，宿主不再传入旧引用根；执行器MCP共用日志默认目录也同步修改，执行任务根和Docker挂载不在本批。`--references`/`--log` 仍可覆盖。显式旧引用根按唯一登记的目录记录解析到固定目标，并拒绝新旧目录并存；查询仍逐记录核验原内容身份。更改数据根不会自动复制旧资料；旧别名只指向原迁移目标。任意旧日志路径通过既有精确文件映射恢复，直接打开旧物理路径的未适配外部脚本并非透明兼容。

修改前调用方备份位于 `tmp/repository-relocation-20261111/reference-archive-callers/`。首次调整的 `web_references.py` 与 `code_executor_mcp.py` 原源码身份通过 `reference-archive-source-revisions-20261111.json` 保存，其余源码沿用既有原身份快照；未改旧迁移哈希。回滚沿用本文件规则，先停止相关写入、保留迁移后新增引用和日志的新版本，不能用旧备份覆盖新文件或原批准。

专项检查涵盖全部旧编号/旧文件映射、数据根配置、显式别名冲突、引用重启读取和篡改拒绝。真实MCP无引用/日志覆盖参数读取23个原编号，宿主重新启动子进程后再次读取，24次审计全部落在新日志目录；额外真实执行器MCP错误请求也写新默认日志，未派发任务或启动Docker。105份原档案/日志哈希不变，旧目录未重建。其余执行器挂载、工具发现及阶段冻结材料继续另批处理，F0未完成。完整检查及证据索引见 `migrations/reference-archive-batch2-execution-20261111.json`。

本批最终结果：专项71通过；完整回归594通过、141跳过；12份重定位记录422项及目录防回退检查通过。另逐一匹配全部23份原引用的 `reference_id` 与 `bound_call_id`：均能在封存共享日志或尚未迁移的历史运行专属日志中找到原审计记录，不将只迁移的82份共享日志误称全部历史日志。历史E的827项及原正文/选图批准仍有效，当前上下文差异保持如实记录，没有新增导出准入。


## 后续第三批：执行器挂载与工具发现（2026-11-11）

| 原位置 | 新位置 | 身份与用途 |
|---|---|---|
| `stage-c/execution/` | `runs/execution/` | 675文件原字节移动，53个已完成任务、95个产物；内部相对路径及回执不改写 |
| `stage-c-plus/tools/` | `configs/local/tools/` | 23个本机工具、来源记录及下载片段原字节移动；继续忽略，不作为发行资源 |
| `stage-c-plus/tex-cache/` | `archive/research/tex-cache/20261111/` | 412个原缓存文件封存，另复制相同字节到 `configs/local/tex-cache/` 作为当前可变缓存 |

移动前验证全部任务和产物身份、无未完成执行声明，并通过Docker只读检查12个现存容器，无旧目录挂载冲突。移动前的完整备份分别在 `tmp/repository-relocation-20261111/execution-data/`、`local-export-tools/`、`tex-cache-archive/`。三份迁移清单使用同名日期JSON登记；源码原身份由 `executor-tools-source-revisions-20261111.json` 保存，调用方/维护脚本修改前版本另存 `tmp/repository-relocation-20261111/executor-tools-callers/`，不重写历史源码哈希或批准。

`modelcrew.execution_paths.execution_directory` 统一登记、DockerExecutor、独立MCP和宿主执行根。优先级为显式执行根、`MODELCREW_EXECUTION_ROOT`、数据根下 `execution/`（默认 `runs/execution/`）。显式旧根通过唯一登记记录定位固定迁移目标，新旧根并存拒绝；更改数据根不会自动复制历史任务。现有显式外部执行根能力保留，但这不代表其他论文工件准入已扩展到工作区外。Docker挂载由实际解析后的任务目录生成，仍只读挂到 `/work/job`；原缓存结果恢复不创建新容器。

新增 `python -m modelcrew.tool_discovery` 诊断。发现优先级是显式可执行文件、`MODELCREW_PANDOC`/`MODELCREW_TECTONIC`、PATH、迁移后的本机工具文件；显式配置缺失时不回退，返回可操作错误。导出维护入口、汇编导出默认调用和相关测试不再硬编码阶段工具目录；显式旧二进制路径可按原文件哈希映射恢复。诊断只执行 `--version`，本机实际Pandoc 3.6.4、Tectonic 0.17.0与原来源清单可执行文件哈希一致。没有自动下载工具、安装依赖或取得二进制再发行许可。

当前TeX缓存默认 `configs/local/tex-cache/`，允许 `TECTONIC_CACHE_DIR` 指定；原412文件移入不可变档案，再逐字节复制当前缓存，后续编译不修改原迁移证据。本批只检查工具版本，没有正式论文排版/导出或TeX资料下载；现有根 `execution/` 中监督器/题目专用代码的包内资源整理属于后续范围。

实测：真实Docker执行一个新合成任务，确认新根只读挂载、非root、禁网、只读根和执行后清理；重复调用未再次启动容器，宿主MCP查询恢复同一回执。53个旧任务在禁止Docker调用时全部恢复，1110份本批旧文件哈希不变；原缓存412项与当前种子缓存一致，旧阶段目录未重建。检查结果及证据索引见 `migrations/executor-tools-batch3-execution-20261111.json`。其他阶段冻结材料、资源与最终目录收口尚未完成，不登记F0完成。

本批最终检查：专项44通过，完整回归599通过/141跳过；15份重定位记录1532项通过，目录防回退检查通过；历史E的827项及原正文/选图批准保持有效，当前上下文差异仍保留。工具升级须另存新版本并显式配置，不覆盖映射所保护的原可执行文件。完整安装、资料许可与最终目录验收继续按F0/F1/F2/F5边界实施。


## 资源、阶段冻结材料与最终目录收口（2026-11-11）

本批先拆分参考原文/私有fixture，再迁移运行资源。原 `contracts/` 的Schema与注册表、12份数据库迁移、监督器及项目自有算法导航/中文写作规则移入包内资源；所需两份项目文档另保留同字节包内副本，开发工作区仍读取当前docs。`resource-manifest.json` 固定167个实际资源身份，wheel另含清单本身，共168个资源文件。`pyproject.toml` 与 `MANIFEST.in` 使用明确逐文件允许清单，没有通配复制本地知识原文。

未确定再分发条件的算法原文和中文论文模板逐字节归入 `archive/research/knowledge/`；契约样例放入本地 `archive/research/contract-examples/`。运行时 `project_assets.asset_path` 将逻辑资源定位到包资源或登记本地档案，不改写原上下文文档键、来源哈希或批准。干净安装没有这些本机原文；需要它们的写作上下文仍会明确缺失，不能宣称完整知识内置、自动路由、单Agent完整工作流或F5完成。公开项目代码许可证本身也仍未选定，安装包保留Private限制。

8个旧阶段根目录逐个盘点、备份后移到 `archive/research/stages/<原阶段名>/`，共64055个普通文件，包含Git忽略的本地历史副本、生成缓存和运行证据，不只搬移Git可见材料。阶段D中一个指向开发机外部node_modules的目录联接只记录链接类型和目标、随目录保留，没有遍历/复制外部依赖；正常资源与恢复解析拒绝穿过此联接。每阶段独立公开JSON清单保存普通文件旧路径、新路径、字节数及SHA-256，联接单独登记；本机逐字节备份在 `tmp/f0-finalization-20261111/backups/`，链接恢复按登记元数据单独处理，不从外部目标重建“原件”。

旧UUID运行中605个三手、575个建模、4个汇编输入和5个构建分别复制到当前 `runs/` 用途目录，逐文件校验，共1189个工作副本。`runtime_aliases` 限定原前缀和ID，不把任意历史路径当成当前运行；业务定位读取当前副本，取证的 `resolve_repository_path` 始终按原哈希读档案，两者分开。数据库中的原路径键、任务版本、批准及检查点未批量替换。原件不因恢复写状态而改变；历史E核验入口也改为直接选择原档案，仍不授予当前导出权限。

剩余题目专用执行helper归入本地 `archive/research/model-helpers/`；两个原Dockerfile移到 `configs/executor/`，监督器由包资源定位。分阶段requirements原件在 `docs/history/dependencies/`，新维护输入用 `configs/dependencies/{workflow,retrieval,figures,documents,paper-export,evidence}.txt` 并修正相互引用。Python可选功能依赖组同步登记，未安装/升级本机依赖。历史脚本的明确源码读取已接逻辑资源解析；部分题目专用维护入口仍属历史重放，不能把它们当作当前通用写入命令。5个通用MCP复验命令改为必须显式指定全新 `--output`，防止默认向档案追加。

当前README/路线导航更新到新位置，原阶段文档和内部旧链接不追改；本机历史入口见 `docs/history/research-archive.md`。目录最终检查既检查Git可见文件，也检查物理存在的旧阶段/过渡根，防止只靠ignore掩盖旧目录。`final_layout_accepted` 与整体F0/发行验收分开返回。

本批源代码原身份通过 `finalization-source-revisions-20261111.json` 独立保留；修改前的维护源码/测试/配置与当前导航备份在 `tmp/f0-finalization-20261111/callers/`。原迁移清单哈希未改写。中断恢复依照各清单逐项检查新旧位置，不批量重命名；回滚前必须另存当前工作副本与迁移后新增文件，只移动确认未冲突的原件，不能用老备份覆盖新工作或历史批准。

源码树外检查已实际安装wheel，以独立目录和明确包路径读取167资源、126官方文档工具、Schema、12份SQL及监督器；显式加入现有用户依赖目录而未加载可编辑安装pth。这是源码树外安装定位检查，不是干净环境依赖安装或完整工作流验收。首次隔离探针因 `-I` 同时隐藏用户依赖而缺jsonschema，保留v1报告，v2明确依赖范围后通过；未下载依赖。完整执行回执见 `migrations/finalization-execution-20261111.json`，最终测试和旧文件核验结果以该回执为准。

本批最终回读：44份映射65666项及1个不遍历的链接元数据通过；64055个阶段普通文件已归档，1189个旧UUID当前副本可独立恢复。完整回归604通过/141跳过，真实数据库合成运行46通过，最新定位边界88通过、汇编专项36通过。最终wheel的59个源码模块逐字节匹配当前源文件，167项资源身份/126官方工具/12份SQL/监督器在源码树外读取通过；最终sdist也在源码树外重建并核对源码一致。实际默认算法检索、4条论文检索及真实MCP原引用恢复再验通过，原集合不重建、不下载模型。历史E的827项和原批准仍通过。目录检查与差异空白检查通过；整体F0、完整知识内置与干净环境工作流不因这些局部通过而登记完成。


## F3 原资料修订身份补登记（2026-11-14）

完整历史恢复回归发现此前知识资料更新后，算法 index.md、论文 workflow.json 与 writer-instructions.md 尚未登记F0原字节的修订恢复关系。分别从原F0导航备份及F2修改前备份按既定SHA256取回，新增 archive/research/source-snapshots/knowledge-originals-20261114 三份快照，并通过 docs/migrations/knowledge-source-revisions-20261114.json 追加 revision_records。旧44份迁移清单及原哈希不改，当前知识资料不回退；65,666项迁移文件恢复检查重新通过。该登记不重新签发旧用户批准，也不扩大归档资料发行范围。
