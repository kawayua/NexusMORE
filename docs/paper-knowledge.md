# 中文论文资料与研究模板

2026-11-14：按用户“先补C1-C5”独立编写，资料版本1.0.0，工作流1.3.0。五份文件服务于枢模中文数学建模体裁，内容依据已确认项目规则，未复制待授权原文、官方模板、私有类文件或字体。它们是当前私有开发发行资料，不宣称某届官方合规或项目整体已取得公开发行许可。

| 编号 | 包内路径（相对resources） | 内容与接入 |
|---|---|---|
| C1 | [paper/reference/chapter-template.md](../src/modelcrew/resources/paper/reference/chapter-template.md) | 完整Markdown章序、逐章证据要求、单题与汇编区别、唯一全局符号表 |
| C2 | [paper/reference/writing-guidelines.md](../src/modelcrew/resources/paper/reference/writing-guidelines.md) | 中文叙事、方法前提、真实结果/引用、三手与M1/P1/P2/W1/W2、审批与失效 |
| C3 | [paper/reference/paper-format.md](../src/modelcrew/resources/paper/reference/paper-format.md) | A4/25mm/12pt及Word样式映射、首页摘要/次页正文、公式图表引用及全页检查 |
| C4 | [paper/reference/latex-format.md](../src/modelcrew/resources/paper/reference/latex-format.md) | 当前工具版本、标准组件与本地字体准备、同源AST、警告阻断、真实编译与检查 |
| C5 | [paper/templates/chinese-research/main.tex](../src/modelcrew/resources/paper/templates/chinese-research/main.tex) | 自包含导言和中文全文工程示例、一张符号表、公式与交叉引用，无私有sty/cls |

新任务的`modelcrew.modeling_paper.writing_context()`每次实际读取workflow指定的10份上下文文件，保存真实文本及SHA-256；`modelcrew.paper_layout.contract()`要求五份资料齐全，并检查文档类/字号/边距映射。包内`paper_export`采用契约选中的新模板，不再写死历史main.tex。声明当前资料版本却缺文件时明确失败，不静默退回历史参考。

四份规范采用英文用途名，主模板用独立目录，避免改变旧中文文件名和旧`resources/paper/reference/main.tex`的历史身份。旧冻结任务和旧模板契约仍按原协议核对；原脚本、源账本、批准文件及构建包不改写。本批未修改collaboration 1.3.0的21份冻结指南；论文工作流与五份资料各自版本/哈希独立记录，不将资料补齐说成F6完整自动路由。

模板使用ctexart、fontspec等标准TeX组件，需要受支持Tectonic缓存。准备工程时把合法本机宋体放到fonts/simsun.ttc，记录字体来源与哈希；字体不随wheel/sdist发行，不推定再分发许可。将LATEX_TEMPLATE_TITLE受控标题槽替换为明确工程标题后，可经latex_tools自定义模板工程编译。模板正文仅为校验说明和代数排版示例，没有真实赛题结果、参考文献或正式图；真正论文正文由批准Markdown/AST替换，不复用示例当结论，也不免除候选/正式图要求。

当前支持范围仍为Windows x86_64、CPython 3.13、Tectonic 0.17.0、Pandoc 3.6.4。不增加其他引擎、BibTeX/Biber或任意TeX→Word。原生Word渲染权限问题单独保留，不以LaTeX PDF冒充Word渲染通过。

当前工程模板实际编译3页，全部页面预览、机械检查及作者观察；这不是正式论文、独立W2或用户批准。包内205项资源和安装后读取另经私有构建验证；具体工具/字体/文件哈希、隔离安装及检查范围见[本批回执](release/paper-knowledge-supplement-20261114.json)。完整知识仍缺A/B两类10项，见[后续补充清单](knowledge-supplement-checklist.md)。
