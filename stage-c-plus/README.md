# C+ 算法检索、真实绘图与数学导出

> 更新任务重执行（2026-11-07）：中文15图稿、当前写作上下文、分开确认及导出门槛已重新验证；用户已明确通过补图后正文，15张选图沿用已有通过，图片未重画。301项完整回归及真实算法MCP复测通过。当前入口见[重执行报告](reexecution-20261107/README.md)，下文与原 progress.json 保留前次工具链验证范围。

C+ 是阶段 C 验收后的独立增补；工程实现和验证已完成，用户验收尚未记录。历史 C1—C6、A+/B+ 原验收与确认快照保持原样。详见 [验收报告](acceptance-report.md) 和 [机器可读进度](progress.json)。

`paper-search MCP` 新增 `algorithm_search`，与论文/网页检索共用引用归档及任务版本绑定；`code-executor MCP` 保持原有边界。六张有限算法卡片覆盖几何模型、括区间求根、连续 LP、整数 LP、ODE 初值积分和 brentq API，来源为五个完整关联小节。读取内置算法索引后构建，模型、数值算法与 API 分层。原索引是 A+ 已绑定哈希的历史快照，故不原地更新其中的阶段状态；本目录记录新增状态。

查询可声明 `category`、`layer`、`verification`、`facts`、`variable_count`、`available_dependencies`。明确违反前提的卡片排除；未声明的前提返回 `needs_review`，调用者填写 true 不构成数学证明。规模上限是本项目有限审查预算，并非求解器理论容量。向量相似度只用于排序。返回完整原文、原文件/行号/哈希、卡片版本和外部引用收据。本地算法来源没有伪造网页 URL，在线论文仍须保留真实链接。未增加 OCR 或图片论文正文识别。

实际绘图复用已确认 v2/revision 2 的历史轨迹，未执行新赛题求解。Python/Matplotlib 生成两个残差面板、矢量 PDF/SVG、600 dpi PNG/TIFF，保留数据 CSV、绘图源、输入 SHA-256、图契约和 QA。B+ 两份数学包分别生成 6 页与 2 页 LaTeX/PDF，共 31 个符号、15 个公式，真实使用 Tectonic 0.17.0 编译，全部页面已渲染审阅。它们是工程交接样稿，不是完整论文。

复现（先启动本项目 PostgreSQL、Qdrant；本机已有中文 BGE）：

```powershell
# catalog 已存在时沿用并核验；首次创建才运行 prepare（拒绝覆盖）。
python -m scripts.prepare_cplus_algorithms
python -m scripts.index_cplus_algorithms
python -m scripts.verify_cplus_retrieval --output stage-c-plus/runs/new-retrieval-probe
python -m scripts.verify_cplus_workflow --output stage-c-plus/runs/new-workflow-probe
python -m scripts.build_cplus_export --output stage-c-plus/runs/new-export-probe --compiler stage-c-plus/tools/tectonic.exe --qa-tools <本机Python审图工具目录>
python -m pytest tests --integration -q --basetemp=stage-c-plus/runs/new-pytest
```

使用内置 `--compiler` 默认路径也可。未传 `--qa-tools` 时只有内建字号/边界检查，不代表外部静态、对齐和碰撞审图已运行；本次完整验证传入了工具目录，具体脚本哈希保存在审阅记录。Tectonic 官方便携工具来源/哈希保存在本地 `tools/provenance.json`，缓存及二进制不入库。首次编译需下载 TeX bundle，后续使用本地缓存；不是离线依赖安装器。编译采用 `--untrusted`，本次只接受项目审核过的数学包，过滤器不是任意 TeX 的完整安全沙箱。

可查看的最终文件位于 `output/pdf/cplus/`；原始日志、逐页 PNG、失败探针和成功构建清单位于 `runs/`。结构检查、有限数学一致性检查、真实数值诊断、导出和人工视觉审阅分别记录。编译成功、检索命中或图片无碰撞均不替代一般性数学证明，也不证明碰撞安全性或全连续时间精度。未调用付费 LLM，不代用户确认模型/结果，不宣称已实现自主 Modeler 协作。

## 中文论文补充（2026-11-07）

用户已说明 A+/B+/C+ 当前任务完成，并要求调整论文体裁。上述数学探针保留为历史工程记录；新的中文数学建模首稿与图选讨论见[论文补充](../docs/chinese-modeling-paper.md)。该首稿遵循论文手章节、9 张候选/8 张暂选图及 MD 先审阅流程，math-reasoning 不再主导论文结构。用户正文审阅和图片最终选择尚待记录。

## ABC+ 阶段内完善与正文通过（2026-11-07）

用户现已通过中文单题正文，允许在 ABC 相关阶段完善。已新增六时刻板凳轮廓/局部细节候选图，候选总数15，原文和入文图不变，最终选图待讨论；已固化项目默认流程及每次加载入口。分工、实际实现边界和后续 D5/E 接入见[完善记录](paper-refinement-20261107.md)。
