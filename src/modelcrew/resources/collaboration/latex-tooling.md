# 枢模 LaTeX 工具

后端统一 Python，入口 python -m modelcrew.latex_tools。初始化、环境诊断、资源绑定、真实编译与全页校验服务本地契约，不复制或运行上游 LaTeX 发布器。

init 在显式 workspace root 下创建新项目，中文为默认研究骨架，英文仅显式 profile=en 时提供。自定义模板须给来源、版本和明确主入口；来源未核验不得声称官方合规。内置骨架有占位符，尚非可交付论文。一个全局符号表、首页摘要关键词、正文第二页和既有中文政策继续适用。两个空上游 bib 文件的目标合并为一个可选核验文献交换文件，不当知识库。

doctor 只诊断所选引擎和实际所需工具，记录路径、版本、哈希和缺失项；不自动安装或下载。默认复用 Tectonic；本轮仅支持Tectonic 0.17.0/Pandoc 3.6.4；其他经典引擎暂不支持，实验分支不扩大支持范围。外置BibTeX/Biber和任意LaTeX→Word暂不支持，不作为本批必补任务；官方模板合规仍须按实际任务核验，不凭工具存在宣称接通。

bind 保存原件与项目副本哈希，输出到新位置并追加不可覆盖绑定记录。build 使用新 attempt 目录和完整源码副本，记录原源码、模板、绑定、编译器和产物身份；禁止 shell escape，Tectonic 仅用已缓存资源。命令、stdout、stderr、超时和失败均保存，不清除诊断目录。检查所有 PDF 物理页与预览，不接受只看首页、抽样页、跳过 PDF 或任意理由放过警告。validate 重新核对当前源码、绑定、编译产物、日志和全部预览。

原始 TeX 项目构建始终标记 engineering_probe、formal_approval=false、visual_review=PENDING、W2=NOT_RUN；没有发布或覆盖正式稿的开关。自由 TeX 源码不能证明与已批准 Markdown 等价。正式 export 仅接受已登记 project_id/build_id/request_id，调用原汇编导出流程，由现有 guard 校验模型、结果、正文/选图和历史绑定，再从同一已批准内容源构建 Word 与 PDF。编译成功不是独立 W2 或用户批准；原生 Word 渲染、所有页图和独立审查仍按既有流程完成。

任意 LaTeX→Word 无损转换不作为本工具承诺。当前可用路线是已批准 Markdown/AST 同源生成 LaTeX 与 Word 原生公式；复杂公式必须检查 OMML 和实际渲染。缺转换或字体/宏包时明确阻断，不能静默改语言、改内容、换文档类或伪称转换成功。

中文骨架通过 --cjk-font 或 MODELCREW_CJK_FONT 显式选择本地字体；Windows 可发现系统 simsun.ttc。字体文件复制到新工程并记录来源与哈希，不随发行包内置，不推定再发行许可。无可用字体时保留未完成标记并阻断构建；缺宏包仅报错，不联网补装。
