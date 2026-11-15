# F2统一安装包最终汇总验收与收口

2026-11-14：按用户要求“对F2进行最终汇总验收与收口”，本版私有开发安装包验收通过，F2收口。冻结发行名nexusmore、导入/命令modelcrew、版本0.1.0.dev0，目标Windows x86_64 / CPython3.13。下一阶段为F3，尚未开始实施。本结论限已约定安装包范围，不授予公开发布或正式论文批准。

| 验收项 | 结果与范围 |
|---|---|
| 构建与入口 | wheel、sdist、源码包重建wheel通过；console/module的version/help/resources-check通过 |
| 包内内容 | 219项声明资源、74个Python模块；126项文档工具、21份协作指南、12项迁移及现有JS/部署/渲染适配文件 |
| Python依赖 | 核心＋workflow/documents/figures/evidence/retrieval/paper共7组有分组实测证据；最终候选又完成全部生产extra联合安装、导入与pip check |
| 知识基线 | A1—A7、B1—B3、C1—C5共15项均有本版范围的独立资料；113算法案例＋39数学案例在最终安装中复算通过 |
| 源码外安装 | 三个独立venv：wheel核心、源码包重建wheel核心、全部生产extra；不使用源码路径/用户或系统site/pytest |
| 回归与原记录 | 最终wheel所有成员内容逐字等同此前127项通过测试的候选；sdist仅安装文档变化、测试/运行代码未变；历史记录与候选哈希未变 |
| 目录 | F0最终目录规则检查0问题；本批不重签F0或旧任务批准 |

## 冻结产物

- wheel：`D:\big-third-up\modelcrew\tmp\package-closure-validation-20261114\frozen-build\wheel\nexusmore-0.1.0.dev0-py3-none-any.whl`；SHA256 `78dfdcfc6c91b5aab11e3aaaa5d107ce68dac649d535589ff5e3e0940bfa9153`。
- 源码包：`D:\big-third-up\modelcrew\tmp\package-closure-validation-20261114\frozen-build\sdist\nexusmore-0.1.0.dev0.tar.gz`；SHA256 `4b8feee584bfbab1d151c386890973019df5e358a2f9d215caf42863d6d14941`。
- 源码包重建wheel：`D:\big-third-up\modelcrew\tmp\package-closure-validation-20261114\frozen-build\wheel-from-sdist\nexusmore-0.1.0.dev0-py3-none-any.whl`；SHA256 `4123eb0200e526af805061914aedf1159bdb914257057294c9b283cf2179fd89`。

机器验收与完整证据见[收口回执](package-closure-20261114.json)。旧用户批准仍只绑定原200项候选，原收口与分批记录不追改；本次依据新的明确收口要求完成当前候选的技术验收，没有把用户请求改写成论文/选图/独立节点或公开发布批准。

## 依赖配置说明

生产workflow配方另存configs/dependencies/workflow-runtime.txt，与pyproject的workflow extra完全一致；旧workflow.txt是含pytest的历史开发配方，保留字节，不能作为生产安装配方。其他五个extra与对应配置逐项相同，生产extra不安装pytest。实际用户安装以发行包extra为入口，开发测试依赖单独处理。

## 继续保留的边界

paper组的Python依赖已通过，原生Word渲染仍是权限/环境阻塞；Tectonic/Pandoc此前工程探针不等于正式论文通过。检索原实测使用固定tiny BERT和持久化本地Qdrant，不是生产BGE语义质量或Docker服务器验收。资料读取/固定案例不等于自动选择/通用求解/自动证明，实际任务的模型、结果、正文/选图与独立M1/P1/P2/W1/W2仍分别执行。

当前wheel不捆绑CPython、Docker、模型权重和原生工具；安装F2包不是完整“只填key”产品体验。Harness下载安装继续由用户负责；PostgreSQL/Qdrant按既定Docker路线由后续初始化管理。

## 后续任务交接

| 阶段 | 工作 |
|---|---|
| F3 | 统一用户配置、数据目录、初始化和诊断 |
| F4 | 运行时/原生工具准备，Docker服务迁移、健康与恢复，解决Word渲染和干净机器验收 |
| F5 | 项目许可证与第三方依赖、模板、字体的公开发行授权/归属 |
| F6 | 语义索引、角色/阶段自动读取与执行器调用、版本和失败恢复 |
| G | 优先DeepSeek Harness真实工作流MCP、确认与重连联调 |
| H | 公开样例、最终宿主端到端、文档与首发准备 |
