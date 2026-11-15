# F3 用户配置与初始化：实施及技术验证

2026-11-14，依据用户“进行F3阶段”完成本阶段实现与技术检查；不将该请求改写为用户已批准正式论文、独立节点审查或公开发行。F2 原冻结包与回执保持字节，F3 新候选另存，下一阶段 F4 尚未启动。

模型、数据库、论文/算法检索、执行器及导出工具现在共用版本 1.0.0 用户设置。安装包默认使用 %LOCALAPPDATA%/NexusMORE/workspace，通过 MODELCREW_WORKSPACE 或全局 --workspace 选择其他磁盘。数据子目录仍在工作区内，以保留产物相对身份；源码检出保留开发根和历史兼容读取。新增 init、config-show、doctor，重复初始化不覆盖配置、密钥和旧批准，显式缺失/错误配置不静默回落模型。密钥与数据库 URL 使用环境或私密 secrets.env，不直接写入 settings.json。

| 检查 | 结果 |
|---|---|
| 回归 | 两轮最终相关回归合并去重：215 项通过、2 项按环境跳过，无失败；大组 214 通过，诊断补充组 33 通过，存在重复测试 |
| 跳过说明 | 当前源码测试 Python 缺完整 DOCX 校验依赖；Windows 不允许非特权符号链接。junction 拒绝路径另有通过测试；完整依赖安装不使用系统 site 或 pytest |
| 历史恢复 | 补登记算法导航、论文 workflow 和 writer-instructions 三份原始字节快照；原 44 份迁移记录、65,666 个文件的身份恢复检查通过，旧哈希/批准不改 |
| 包构建 | wheel / sdist / sdist 重建 wheel 均通过严格成员与源码身份检查；75 个 Python 模块、219 项资源，资源内容与 F2 不变 |
| 源码外安装 | 最终候选新建核心 venv，另升级两个已隔离的 F3 核心/完整依赖 venv；console/module、pip check、配置、初始化、重复初始化、诊断通过；3 个安装包目录字节未变 |
| 模型验证 | 本地 HTTP 模拟成功一次、401 失败一次，无自动重发；配置指定模型和端点；自定义 key 变量缺失不回落其他凭据；日志脱敏 |
| MCP | 真实 stdio 子进程读取不存在的引用返回 reference_unavailable；日志落用户工作区，无网络论文检索、付费模型调用或业务批准 |
| Docker | 沙箱内命名管道权限不足被诊断为 permission_denied；沙箱外只读 docker info 返回 linux，不代表服务部署/数据库迁移通过 |
| 服务诊断负例 | 使用本地端口 1 的虚构数据库连接验证失败分支；未使用真实数据库密钥或修改数据库，不能算 PostgreSQL 服务验收 |

配置使用方法见[用户配置文档](../user-configuration.md)，机器回执见[user-initialization-20261114.json](user-initialization-20261114.json)。最终候选位于 tmp/user-initialization-validation-20261114/verified-build；前两轮 candidate-build/frozen-build 仅为本批中间候选，保留用于追溯，不冒充最终候选。

core doctor 通过仅表示基本包/配置环境通过。full 模式在未绑定实际权重、索引和原生工具的测试工作区保持 incomplete，符合预期；索引配置或工具路径存在不等于语义质量、真实渲染或独立审查。旧算法索引因资料哈希更新被拒绝，必须新建版本，不修改旧索引以伪造可用。

F4 接续 Python/原生工具准备、PostgreSQL/Qdrant Docker 部署与迁移、服务健康/持久化/恢复、原生 Word 及干净机器验证。F5 发行授权、F6 自动路由和生产检索、G DeepSeek Harness、H 最终端到端仍分别验收；当前尚不能宣称下载 Agent 后只填 key 即完整可用。
