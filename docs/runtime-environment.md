# 首发运行环境

2026-11-14 后续决定：用户明确跳过全新 Windows / 空 Docker 镜像 / 完整首次联网安装测试，该项不是通过；本机隔离环境证据保留，继续 F5。见 [范围决定](release/environment-validation-exception-20261114.json)。

2026-11-14 F4 更新：私有 bootstrap 可在用户工作区自动准备独立 CPython 3.13.5 与生产 Python 依赖，无需用户手动安装 Python；Docker Desktop/WSL2、Harness、获得许可的 Word 和字体仍由宿主提供。PostgreSQL/Qdrant 使用工作区独立 Compose project 和命名卷，不接管历史服务。准备方式见 [服务与环境准备](environment-preparation.md)，实际验证及尚未覆盖的全新机器边界见 [F4 汇总](release/environment-preparation-summary.md)。下文 F1 基线与历史范围保留。

2026-11-12：用户确定首发为 Windows x86_64、CPython 3.13 和 Docker Linux 执行器。机器清单见 [运行环境配置](../configs/runtime-environment.json)。这是 F1 的运行环境范围决定，不是 F1 整体通过或干净环境验收。

## 支持范围与本机基线

| 层次 | 首发范围 | 本机验证基线 |
|---|---|---|
| 宿主 | Windows x86_64，CPython >=3.13,<3.14 | Windows 11 10.0.26200、CPython 3.13.5 64 位 |
| 容器服务 | Docker Desktop、WSL2 后端、Linux amd64 容器 | Desktop 4.85.0、Engine 29.6.2、API 1.55 |
| 求解执行器 | Python 3.13、非 root、禁网、只读根目录 | `modelcrew-reference:py313`，本次为 3.13.18；验证回执记录实际镜像 ID |
| 业务数据库 | PostgreSQL 16 | 沿用现有部署配置；本次不迁移数据库或数据卷 |
| 向量检索 | Qdrant 1.19.1、另行配置嵌入模型 | 仅向量检索需要；模型权重和缓存不随包分发 |
| 论文导出 | Tectonic 0.17.0、Pandoc 3.6.4 和所需字体/渲染工具 | 适用范围沿用 [LaTeX 支持决定](release/latex-support-decision-20261112.json) |

表中的 Docker 版本是本机基线，不是已经验证的最低版本。其他 Windows 构建和 Docker 版本仍需兼容验证；Linux/macOS 宿主、Windows ARM64、其他 Python 次版本和 Windows 容器不在当前首发范围。宿主 Python 和容器 Python 分开安装，都使用 3.13；容器实际补丁版本单独记录，不要求与宿主补丁号相同。

## 执行器准备与约束

新镜像使用 `configs/executor/Dockerfile.runtime` 构建，基础镜像按摘要绑定；构建仅以 `configs/executor/` 为上下文，不向 Docker 发送项目数据或密钥。构建首次需要网络，任务执行期间不联网安装包。numpy 2.3.1、scipy 1.16.0 和 openpyxl 3.1.5 固定在镜像中。

```powershell
docker build --pull=false --platform linux/amd64 -f configs/executor/Dockerfile.runtime -t modelcrew-reference:py313 configs/executor
python -m modelcrew.code_executor_mcp
```

新任务默认使用 py313。旧 py311 镜像、历史镜像 ID、任务包、回执和用户批准保留；显式历史配置不会被批量改写。新镜像缺失应明确失败，不自动退回旧 Python 或宿主执行。

执行器沿用 UID/GID 10001、禁网、只读根文件系统、只读任务包、删除全部 capabilities、no-new-privileges、CPU 1 核、32 进程。默认内存 256 MiB、超时 10 秒；既有任务登记范围为内存 64—1024 MiB、超时 1—180 秒。模型与 MCP 请求不能自由覆盖宿主配置。每次派发保存实际镜像 ID，状态查询和恢复沿用原任务绑定。

## 必要依赖与后续验收

Python 依赖以 `pyproject.toml` 功能组为准；仅安装核心包不等于数据库、检索、绘图和论文链路全部可用。业务运行需要 PostgreSQL；向量检索另需 Qdrant 和嵌入模型；导出另需对应引擎、字体和全页检查工具。Node.js 仅用于可选 JavaScript 宿主入口，其版本随宿主适配另定，不是 Python 核心或 Docker 执行器的必要条件。

F2 验证依赖解析与安装包；F3 落实用户配置、数据目录、初始化和诊断；F4/H2 在干净 Windows 环境验证首次安装、服务启动、确认点、恢复和完整导出。现有本机缓存、工具与服务不能替代上述验收。具体模型供应商和 harness 兼容性仍分别冻结，本次不扩大声明。

## 本轮验证

真实项目执行器探针通过：Linux x86_64 / Python 3.13.18，非 root、数值求解、XLSX 往返与根目录拒绝写入均核验；实际执行回执记录禁网、资源限制及镜像 ID。状态查询与新执行器实例恢复读取原回执，未重复执行。25项相关回归通过，pytest缓存目录权限警告不影响用例；193项包资源校验与最终目录检查通过。

Docker Hub首次构建因网络超时失败，随后从镜像站下载并按所得摘要固定基础镜像；记录的是该来源的内容摘要，尚未与官方仓库独立比对。构建网络/镜像源准备仍需纳入F3/F4；不宣称离线首次安装或官方摘要双重核验已通过。完整依据见[本轮决定与证据](release/runtime-environment-decision-20261112.json)。
