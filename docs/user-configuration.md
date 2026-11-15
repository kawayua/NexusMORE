# 用户配置与初始化（F3）

2026-11-14：后续 F4 已新增 environment setup、独立服务及原生工具准备，见[服务与环境准备](environment-preparation.md)。下文 init/doctor 的只初始化/诊断语义不变，F3 当时的 F4 待办描述保留历史含义。

首发仍为 Windows x86_64、CPython 3.13，发行名 `nexusmore`、导入和命令 `modelcrew`。本阶段统一用户配置与数据位置，不下载 Python、Docker、权重或原生工具，不启动服务，不发送模型请求。PostgreSQL/Qdrant 的 Docker 部署、迁移、健康和恢复由 F4 完成；Harness 下载由用户负责。

## 新用户入口

```powershell
# 默认工作区：%LOCALAPPDATA%\NexusMORE\workspace
modelcrew init
modelcrew config-show
modelcrew doctor

# 全部用户资料也可以放到另一块磁盘；全局选项写在子命令之前
$env:MODELCREW_WORKSPACE = "D:\NexusMORE-workspace"
modelcrew init
modelcrew doctor --profile workflow
modelcrew doctor --profile full
# 明确请求只读的 Docker Linux / PostgreSQL SELECT 1 / Qdrant healthz 检查
modelcrew doctor --profile full --services
```

也可逐次使用 `modelcrew --workspace "D:\NexusMORE-workspace" init`。环境变量必须在启动 Python/宿主/MCP 子进程前设置；Python 业务模块的 ROOT 在导入时冻结，不支持同一个已导入业务模块的 Python 进程内切换工作区。`--version`、`--help`、`resources-check` 不要求初始化。源码检出保留项目根目录作为开发默认工作区，安装包默认使用用户目录，两者用 MODELCREW_WORKSPACE 统一显式覆盖。

初始化创建 `configs/local/settings.json`、`settings.schema.json`、`secrets.env`、工作区 `.gitignore` 以及数据/产物目录。重复执行保留已有文件，不复制开发者密钥、不改历史回执。已有 .gitignore 不覆盖，用户应将自定义 data_dir 及私密路径加入自己的忽略规则。POSIX 新文件使用 0600；Windows 沿用用户目录 ACL，不能把 .gitignore 当作权限隔离或加密，应自行限制共享目录访问。

## 统一配置与秘密

初始化生成的 JSON 是完整版本 1.0.0 示例；Schema 由包内 Python 定义生成，无须复制仓库配置。未知字段、重复 JSON 字段、错误版本/类型、空的显式环境设置会拒绝，显式文件缺失不回落默认。用 `MODELCREW_CONFIG` 或全局 `--config` 指定其他 settings.json，文件中的相对路径仍相对于工作区。

| 配置 | 对应环境覆盖 | 用途 |
|---|---|---|
| paths.data_dir | MODELCREW_DATA_DIR | 默认 runs，必须位于工作区内，拒绝代码/资源/历史目录及链接 |
| model.provider / base_url / name | MODELCREW_LLM_PROVIDER / MODELCREW_LLM_BASE_URL / MODELCREW_LLM_MODEL | 明确指定 OpenAI 兼容服务，不默认选择供应商或模型 |
| model.api_key_env | 自定义变量名，默认 MODELCREW_LLM_API_KEY | JSON 保存变量名，实际 key 放环境或 secrets.env |
| model.m1_model / w2_model / w2_response_format | MODELCREW_M1_MODEL / MODELCREW_W2_MODEL / MODELCREW_W2_RESPONSE_FORMAT | 保留现有节点配置语义；未另设节点模型时明确沿用主模型，不做失败切换 |
| database.url_env | 自定义变量名，默认 MODELCREW_DATABASE_URL | 连接串放环境或秘密文件；数据库不随 init 创建 |
| retrieval.paper_config | MODELCREW_RETRIEVAL_CONFIG | 论文向量检索默认 runs/paper-retrieval/index.json |
| retrieval.algorithm_config | MODELCREW_ALGORITHM_CONFIG | 留空默认内置算法字面查询；非空为显式旧向量配置，不自动回退 |
| retrieval.qdrant_url / model_path | MODELCREW_QDRANT_URL / MODELCREW_EMBEDDING_MODEL | 新建论文索引的服务/本地权重默认值，显式 --url/--model 优先 |
| execution.root / image | MODELCREW_EXECUTION_ROOT / MODELCREW_EXECUTION_IMAGE | 默认 runs/execution、modelcrew-reference:py313；保留显式历史镜像 |
| export.pandoc / tectonic / tex_cache / cjk_font | MODELCREW_PANDOC / MODELCREW_TECTONIC / TECTONIC_CACHE_DIR / MODELCREW_CJK_FONT | 本地原生工具/缓存/字体路径；init 不安装、不编译 |

优先级为显式调用参数 > 进程环境 > settings.json > 内置默认。key 的进程环境优先于 secrets.env；旧工作区 `.env` 仅兼容读取。数据库另兼容 MODELCREW_DATABASE_CONFIG、configs/local/database.env 和 stage-b/.env，后两者并存拒绝；旧文件不迁移、不覆盖。settings.json 禁止直接保存 api_key 或数据库 URL，请按指定变量名在私密 secrets.env 填写。端点和模型也必须由用户明确配置，不能只填 key 就假设所有外部依赖已就绪。

已有检索索引仍以其冻结的 model_path、qdrant_url、collection 和 embedding/corpus/catalog 哈希为准。统一设置不会悄悄重定向旧索引，换模型/服务/知识资料后须创建新版本；相对 model_path 按用户工作区解析。算法知识库补充后旧索引可变为过期状态，不修改历史文件以伪造可用。显式外部执行根/检索配置仍按已有兼容边界处理，不代表允许绕过业务产物审批。

导出支持范围仍限 Tectonic 0.17.0、Pandoc 3.6.4；其他引擎、外置 BibTeX/Biber、任意 TeX→Word 不由配置声明接通。配置不改变正文、选图、全页 PDF 和独立 M1/P1/P2/W1/W2 准入。

## 诊断结果

`doctor` 默认 core，仅检查初始化、可写性、首发平台、包资源与核心依赖；通过不代表业务可运行。workflow 增加模型/数据库配置、工作流依赖和 Docker 命令；full 增加其他依赖、索引配置与当前算法索引哈希、权重目录、导出工具路径。依赖版本显示实际安装值；本命令不是完整依赖求解器，发行包的版本约束仍由 pip 安装和 pip check 验证。工具路径存在不等于工具版本/真实渲染通过，索引配置通过也不等于语义质量或全部向量内容通过。

`--services` 才探测服务，超时有界，不启动容器、不建表、不自动重试模型。JSON 输出只显示配置存在性和工作区路径，不输出 key、连接串或模型端点；服务失败仅给稳定的脱敏说明。通过退出 0，缺项退出 1，配置/操作错误退出 2。原生 Word、生产检索、宿主端到端与独立审查由后续阶段验证。环境变量、系统权限或缺项变化后重新启动命令诊断。

## 2026-11-15 算法默认入口更新

默认算法查询使用安装包内索引与规范目录，按真实算法ID、中文/英文名称或显式类别查询，返回完整所选章节及哈希，不需要建立BGE/Qdrant算法索引。论文语义检索仍使用其原有向量依赖，二者分别诊断。配置摘要的 `algorithm_retrieval_mode` 为 `installed_literal_lookup`；兼容字段 `algorithm_index_file` 是旧向量配置的存储位置，不能据此推断当前启用了该后端。full诊断在默认模式检查包内算法资源，不把旧目录残留文件当作当前依赖。

显式设置 `retrieval.algorithm_config` / `MODELCREW_ALGORITHM_CONFIG` 或调用 `AlgorithmRetriever(config=...)`，才进入旧向量后端，配置、索引、来源和权重仍严格核验。旧配置无效明确失败，不自动改为内置查询；如要恢复默认内置路径，应由操作者清除该显式选择，项目不擅自修改用户配置。`algorithm_config_path` / `algorithm_catalog_path` 的默认返回值保留为历史维护位置，它们不负责选择运行后端。详见[入口收口](algorithm-entrypoint-closure.md)。
