# 枢模资料与工具本地适配

2026-11-12，用户确认按剩余23项审查建议实施。四类来源的能力目标映射到枢模自行编写资料、既有能力与有明确边界的新工具；原文件、哈希与许可不改写，不执行或打包受限本机脚本。产品入口统一，不复制上游宿主预设，不要求用户另装技能包。

## 共享入口与规范

`python -m modelcrew.capabilities` 实际核验包资源和模块入口，读取 `resources/capabilities/registry.json`。注册表区分实现入口、工程检查、知识资料和未注册能力。`entry_available`只表示模块/函数可导入，依赖、供应商、渲染器或宿主仍须实际检查；不宣称所有harness自动路由已接通。

当前规范版本 **1.3.0**，共 **21份**本地指南，包资源 **193项**。新增产品入口、论文检索、文档工作区、数学形式化、统计验证和证明审查6份指南及1份能力注册表；LaTeX指南同步明确现支持范围。建模/代码/论文与M1/P1/P2/W1/W2按对应路由读取，统计解释亦进入论文与W1/W2。现有 `freeze_guidance`、模型/执行/论文运行和W2冻结流程不变，新任务取新规范，旧任务继续核验原冻结文件。

Python唯一后端、三手和独立只读质检、模型/结果确认、中文Markdown先审、正文与最终选图分别确认、唯一全局符号表及所有PDF完整预览/检查继续适用。程序编排器负责路由/版本/恢复，不新增总指挥Agent，不把本轮自检当独立节点通过。

## 论文候选与引用

`modelcrew.paper_discovery.discover` 复用既有 `paper_search_mcp.SearchTool`。默认来源保持本地 `paper_search`，可显式选择 `web_search`；不改变现有算法/本地索引配置或embedding参数，不强制双源。OpenAlex/AnySearch专用接口仍未注册，本轮没有调用这两个外部API。

```powershell
python -m modelcrew.paper_discovery --query "约束优化 数值稳定性" --source paper_search --output D:/work/modeling/references-v1
```

每次使用新目录，保存各来源完整结构化工具回执、调用身份、档案绑定和最终 `discovery.json`。状态区分 `ok`、`empty`、`partial`、`failed`，部分失败不会伪装为完整成功；原工具对凭据/内部错误的隔离继续生效。候选记录保存来源/内容哈希、原始hit与reference_id，可以通过原 `reference_get` 复验。

同一规范化DOI可组成候选组，但保留每个原始记录、冲突字段和全部来源。不合并不同DOI的同标题/不同出版版本，无DOI记录独立保留；相似建议只在已知作者/年份一致、跨来源时一对一提出，不执行合并。统一年份筛选对所有来源生效，年份缺失明确排除，排除理由留档。全部候选保持 `UNVERIFIED_CANDIDATE`，不称双源收录为真实性核验。

真实引用仍须读取DOI/出版机构页面或原文，核对作者、题名、年份、卷期页与所用论断，保存页码、摘录和引用档案，再由建模手记录采用/拒绝、适配和局限。新工具不自动读取/验证论文，不授予用户模型或结果批准。实测使用确定性检索样例经过真实MCP适配器和引用档案，不冒称真实学术API或embedding模型端到端验收。

## 文档工作区

新增 `modelcrew.office_tools`，按任务先实际读取固定官方docx/pdf/xlsx指南，继续保留Apache官方126文件。新工具只处理DOCX/XLSX工程工作区，不注册修订合并/接受、任意公式替换或编辑后论文发布。

```powershell
python -m modelcrew.office_tools doctor --output D:/work/modeling/document-doctor-v1
python -m modelcrew.office_tools profile --root D:/work/modeling --source draft.docx --output template-profile-v1
python -m modelcrew.office_tools unpack --root D:/work/modeling --source draft.docx --output document-workspace-v1
python -m modelcrew.office_tools pack --root D:/work/modeling --workspace document-workspace-v1 --output document-roundtrip-v1
```

所有源/输出均在显式工作根目录内，新目录拒绝覆盖。ZIP检查成员路径、链接/加密、大小/压缩比/数量、重复和大小写冲突，XML禁止DTD/外部实体加载。解包保留每个成员字节，原件只读，不美化XML、不合并run/修订、不自动修复。原件和成员哈希写入 `workspace.json`。

`pack`只接受原成员集合与字节未变的工程，重核当前原件和工作副本；修改工作区明确拒绝，不能靠重写清单绕过原件成员核对。成功只表示成员字节往返一致，不宣称ZIP封装本身字节一致、完整Schema通过、实际渲染或论文批准。DOCX结构检查继续通过已有 `document_tools.run('docx_validate',...)` 单独进行；实际编辑/修订与正式发布不在该工程工具范围。

模板画像保存各分节、样式/basedOn链、默认属性、主题及段落/表格直接属性；未知引用、缺省与局限显式呈现，循环继承拒绝。它保留可追溯的属性层，不实现完整Word主题替换/条件表格/编号或布局计算，不猜官方标题角色，也不把格式观察当合规。源文件哈希前后核对，新报告不改模板。

诊断核对实际依赖版本，不自动安装；缺依赖返回blocked。当前系统未安装defusedxml时官方结构检查相关依赖会阻断；本轮测试显式使用之前下载的0.7.1缓存补齐，未安装到系统。正常安装按项目 `documents` 功能依赖组准备，`lxml`用于新工作区XML检查。原生渲染需按实际任务另跑，诊断通过不是完整导出验收。

完整XLSX读取复用已有 `document_tools.read_spreadsheet` 与 `figure_data`，不静默猜表头/截断/覆盖重名列，不声称公式已重算。Word数学公式复用当前批准Markdown/AST→Pandoc→原生OMML路线和原生渲染检查，不采用受限来源的简化解析器。既有论文政策、全页PDF检查与批准门禁未更改。

## 数学论证与用户说明

自行编写 `mathematical-reasoning.md`、`statistical-validation.md`、`proof-review.md`，使用包资源定位，消除外部技能目录依赖。内容包含问题形式化、单位/维度/定义域、合法变换前提、数学包语义绑定、唯一全局符号表；统计先核对独立/配对/重复测量等设计，区分Welch及相应前提、FWER/Bonferroni和FDR/BH的算法及条件；证明框架要求补齐量词、假设、步长/常数和定理来源，不照搬不完整的收敛/泛化界。

资料不自动运行统计检验、计算示例数值或证明定理，不接管中文建模论文体裁。公式与假设修改沿用现有数学包语义版本和受影响批准失效规则，未证明缺口保留 `open_gaps`。三份本机原文不纳入发行，不因为新指南存在就宣称完整数学知识库/自动证明已实现。

产品说明使用枢模自己的共享入口、配置与功能状态，不导入上游宣传、Star历史、演示图片、默认Word/双语言/最多两个模型等规则，也不强制复制上游使用指南到任务目录。必要的真实来源、许可和署名照实保留。

## 支持范围与验证

本轮LaTeX支持基线仍为Tectonic 0.17.0、Pandoc 3.6.4、Python 3.13、Windows已验证环境。其他编译引擎、外置BibTeX/Biber、任意TeX→Word暂不支持。通用占位符公式编辑、修订合并/接受、公式重算、编辑后Office发布与全部宿主自动路由保持未注册，不由资料规范推定接通。

相关回归79项与真实PostgreSQL三手集成1项通过；集成使用确定性模型/执行器。合成DOCX画像/完整成员往返（含修订XML）、XLSX公式成员原字节往返、来源失败/空结果/部分结果、引用档案、路径与XML拒绝和旧冻结恢复均有检查。本轮没有生成正式论文、PDF或代用户确认。发行wheel按正常安装的文件系统布局，在源码外隔离Python中加载自身模块和193项资源，验证21份指南、新Office工具及真实MCP适配器/引用档案；显式复用已有可选依赖，不声称干净环境完整安装。

23项来源逐条去向、当前能力边界和哈希见[适配回执](release/remaining-resource-adaptation-20261112.json)。原139项来源处置冻结账本及历史审查/批准不回写；本轮为已授权的能力目标实施和独立资料替代层，不自动完成全部来源授权、知识内置或F1/F6验收。
