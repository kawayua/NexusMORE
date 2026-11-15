# 枢模 LaTeX 工具与同源导出

2026-11-12，用户确认保留初始化、环境诊断、资源绑定、真实编译与完整校验目标，按枢模本地契约适配。项目自行编写 `modelcrew.latex_tools`、中文/可选英文研究骨架和共享规范，没有复制、导入或运行上游发布器。7项来源的原始审查与许可状态保留，两个只有注释的上游 bib 不当成文献知识。

## 当前支持版本（2026-11-12 用户确认）

当前支持基线为 Python 3.13、Tectonic **0.17.0**、Pandoc **3.6.4**；PDF 检查实测 PyMuPDF **1.27.2.3** 与 pypdf **6.16.1**。已验证 Windows 本地缓存编译、中文默认/显式英文骨架，以及获批准 Markdown/AST 同源生成 LaTeX/PDF/Word 原生公式并在本机 Word 渲染。其他版本或平台未据此获得兼容承诺。

**暂不支持**其他编译引擎（XeLaTeX、LuaLaTeX、pdfLaTeX、MiKTeX 等）、外置 BibTeX/Biber 后端和任意 LaTeX→Word 转换。它们不属于本批必补缺口或当前支持能力；源码中的实验调用分支也不代表对外支持，后续只有新需求明确纳入才另行接通。当前文献使用经核验的正文/任务文献记录及内联参考文献，同源 Word 导出不等于自由 TeX 转换。环境诊断通过只表示所选工具可见，不能扩大此支持范围。

## 入口与适用范围

后端为 Python，命令入口 `python -m modelcrew.latex_tools`。原始 TeX 工作区与正式论文导出分开保存：前者始终是 `engineering_probe`，后者只从已登记汇编及当前审批进入既有工作流。任何编译退出码、机械检查或作者自检都不授予用户批准或独立 W2。

| 动作 | 实际行为 |
|---|---|
| `init` | 在显式根目录下创建新工程，保存模板来源/版本/文件哈希和当前冻结规范；默认中文，可显式选择英文或提供自定义模板与主入口。已有目录拒绝覆盖。 |
| `doctor` | 实际读取所选工具的路径、版本、哈希与 Python 依赖版本；保存诊断命令及失败日志；不安装、不下载。工具存在不证明模板兼容、原生 Word 渲染或文献后端可用。 |
| `bind` | 将工作区内独立原件复制到工程，保存原件和副本哈希及追加式绑定记录；拒绝路径逃逸、链接路径、冲突覆盖和用绑定替换 TeX/策略元数据。 |
| `build` | 预检并复制完整源码，在新 attempt 中实际编译；保存命令、stdout/stderr、退出码、超时、编译器/源码/绑定/产物身份。前后检查源文件及绑定变化，保留失败目录。 |
| `validate` | 重核当前源码、资源绑定、构建副本、完整日志/产物清单、PDF 和每一页预览哈希；不只读上次 passed。 |
| `export` | 仅接受已登记的 project/build/request/actor，进入 `Workflow.export_assembly`，沿用模型、结果、正文与选图的现有门禁、幂等与恢复；不接受自由 TeX 路径代替批准源。 |

示例中的目录均相对显式 workspace root；每次构建、诊断和审阅使用新目录。

```powershell
python -m modelcrew.latex_tools init --root D:/work/modeling --output latex-draft-v1 --profile zh --cjk-font C:/Windows/Fonts/simsun.ttc
python -m modelcrew.latex_tools doctor --output D:/work/modeling/latex-doctor-v1 --need-word
python -m modelcrew.latex_tools bind --root D:/work/modeling --project latex-draft-v1 --source confirmed/figure-01.pdf --destination figures/figure-01.pdf
python -m modelcrew.latex_tools build --root D:/work/modeling --project latex-draft-v1 --output latex-attempt-v1
python -m modelcrew.latex_tools validate --root D:/work/modeling --project latex-draft-v1 --attempt latex-attempt-v1
python -m modelcrew.latex_tools export --project-id PROJECT --build-id BUILD --request-id REQUEST --actor ACTOR
```

骨架中的占位内容必须替换，未完成就阻断。中文结构保持首页摘要/关键词、正文第二页，以及假设后、模型前的唯一全局符号表；表列含符号、含义、单位和适用范围。不内置未经核验的页数、方程数、字数或评分比例，不声称当前年份官方模板合规。自定义模板要求显式来源、版本和主文件，具体赛事结构映射另行验证。英文仅为显式选项。

中文字体通过 `--cjk-font` 或 `MODELCREW_CJK_FONT` 选择；Windows 默认查找系统 `simsun.ttc`。将选定文件复制到新工程并记录身份，显式设置字体文件路径，避免字体族路径与系统回退错误。骨架以该本地字体覆盖中文与西文基础字形；排版风格如需调整另走模板版本。字体不随 wheel 打包，不推定字体再发行许可。无字体保留未完成标记，缺宏包明确失败。安装 Python 的 paper/figures 可选依赖可提供 PDF 检查所需 PyMuPDF、pypdf；外部编译器、缓存、Pandoc 和原生 Word 仍由环境提供。

## 编译、校验与审批

本轮实际验证 Tectonic 0.17.0、Pandoc 3.6.4 和本机原生 Word。Tectonic 使用 `--untrusted --only-cached`，经典引擎关闭 shell escape，发现 MiKTeX 时禁用自动安装。xelatex/lualatex/pdflatex 只提供显式诊断及调用分支，未完成实际兼容验收，不列为已验证能力。任意 BibTeX/Biber 后端、动态宏/模板语义及编译时 SVG/EPS 转换不静默降级，当前明确阻断不支持项。静态预检不是完整 TeX 解释器或操作系统沙箱。

源码检查包括未完成标记、静态包含/循环、重复标签、引用键、缺失图与资源绑定；真实编译检查未定义项、缺字、字体/宏包警告及 overfull/underfull。没有任意理由放过警告、跳过 PDF、强制正式发布或覆盖旧稿的开关。PDF 使用现有全页检查，核对真实物理页数，生成所有页面预览，检查字体/字形、Type3、递归 Form XObject 和页面越界，保存每页哈希。机械检查之后仍须实际逐页审图及适用节点的独立只读审查。

正式路线继续先交付中文 Markdown 和候选图，确认模型/结果、分别确认正文和最终选图后，同一批准内容源生成 LaTeX/PDF/Word。新 CLI 复用现有已登记汇编流程，没有另造批准记录或自由 TeX 发布口。当前 Word 路线是 Markdown/AST 经 Pandoc 生成并检查原生 OMML，不能外推为任意 LaTeX→Word 无损转换；不存在的通用转换器不会被当成已接通。

新增 `latex-tooling.md` 已纳入 coding/writing/P2/W1/W2 的共享路由；当前规范版本1.2.0，共15份规范。新工程/新运行冻结新规范，旧冻结上下文与已通过论文不改写。通用工具自动选择、全部 harness、官方模板及干净环境完整安装仍由对应阶段验收；其他引擎、外置文献后端和自由 TeX 转换按上述用户决定暂不支持。

## 实测与回执

中文骨架真实编译3页并核验全部预览；已查看该工程探针3页，结果不是论文批准。private wheel 在隔离 Python 中直接加载自身模块、3个 LaTeX 资源及共享规范，校验186项资源，并实际编译/校验3页中文探针及2页可选英文探针。复用了现有可选依赖、编译器和缓存，不冒称干净环境端到端安装。

既有已确认 v6 内容在全新目录同源导出，LaTeX PDF 27页、Word 原生渲染27页，原生公式31项检查通过，16幅配图均保留。计入16份配图 PDF 后，18份不同 PDF 共70页均有完整机械检查与预览证据。参考文献段改为局部左对齐以消除长网址欠满行警告，未设置警告例外；原批准稿、旧产物和确认记录未改。本轮只查看新导出的受影响末页，不冒称70页全部人工审阅。新验证副本保持 `visual_review=PENDING`、`W2=NOT_RUN`。

实测路径、测试 XML、源码与包哈希及14项缺口去向见[适配回执](release/latex-tools-adaptation-20261112.json)。本轮补齐工具基础和当前批准源的导出校验缺口，不代表完整知识授权、任意转换、所有模板或完整 F1/F6 已验收。

2026-11-12 本地规范后续更新：共享规范现为1.3.0、21份，资源193项；本页15份/1.2.0为LaTeX当次适配记录。当前Tectonic/Pandoc支持范围保持不变，新任务按[能力适配](capability-adaptation.md)读取本地资料；旧工程继续原冻结规范。
