# 枢模文档工具接入

本轮已完成此前84个文件的逐项来源比对，并接入一组重新取得的官方工具。完整处置见[逐项报告](document-tools-source-review.md)。本机原目录、旧论文和验收记录均未改写。

## 来源与许可

固定官方提交为 `2c5958ecac7cee2b583967a2c4981d0f4a75c579`，其 Word、PDF、表格目录均附 Apache-2.0 许可，入口说明也指向该许可，没有本机版本的 Proprietary 标记。126个文件从官方重新下载，先验证Git blob，再保存SHA-256和下载URL；源文件保持原字节。它们位于 `src/modelcrew/resources/document-tools/upstream/`，[清单](../src/modelcrew/resources/document-tools/manifest.json)和各目录的 `LICENSE.txt` 随代码保留，参见[第三方声明](../THIRD_PARTY_NOTICES.md)。许可核验结论只覆盖这个固定官方快照，不覆盖本机修改版或全部建模资料。

84项的处置：54项与官方内容相同（只规范化CRLF/LF进行比较），16项以当前官方版本替代，3项是原限制性许可的证据，1项为空文件、不能据此推断作者；剩余10项仍需授权或独立替代，没有复制到工具目录。标准Schema也经过逐文件内容比对，未仅凭ISO、ECMA或Microsoft文件名判定许可；本次从附有Apache许可的官方工具目录取得，并保留其内部注释与来源。

## 官方下载与必须携带的工具指南

维护者准备源码或发行包时，如果工具目录尚未提供或完整性检查失败，需要从[官方固定版本完整归档](https://github.com/anthropics/skills/archive/2c5958ecac7cee2b583967a2c4981d0f4a75c579.zip)取得相关文件。解压后，将该版本的 `skills/docx/`、`skills/pdf/`、`skills/xlsx/` 三个完整目录放到 `src/modelcrew/resources/document-tools/upstream/` 下；保留 `SKILL.md`、`LICENSE.txt`、配套脚本、Schema、模板及参考文档。不要只下载脚本或三个入口文件，否则配套工具可能无法运行。

| 枢模内必须携带的入口 | 作用 | 官方固定版本目录 |
|---|---|---|
| [docx/SKILL.md](../src/modelcrew/resources/document-tools/upstream/docx/SKILL.md) | Word 读取、生成、编辑、转换及相关检查的工具指南 | [官方 docx](https://github.com/anthropics/skills/tree/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/docx) |
| [pdf/SKILL.md](../src/modelcrew/resources/document-tools/upstream/pdf/SKILL.md) | PDF 读取、提取、表单处理等工具指南 | [官方 pdf](https://github.com/anthropics/skills/tree/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/pdf) |
| [xlsx/SKILL.md](../src/modelcrew/resources/document-tools/upstream/xlsx/SKILL.md) | 表格读取、编辑、公式及重算等工具指南 | [官方 xlsx](https://github.com/anthropics/skills/tree/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/xlsx) |

三个 `SKILL.md` 已在本地随126个配套文件一并纳入，并列在哈希清单中，不能在打包时作为“非代码文件”裁掉。恢复下载后，在项目根目录运行 `python -m modelcrew.document_tools verify`，确认文件完整且与当前清单相符。校验失败时查明原因，不通过重新计算清单来掩盖版本不一致；升级官方版本须单独复核许可、变更和受影响功能，保留新版本及证据。

发行包应预先携带这些文件，正常使用者只安装枢模，无需手工安装外部技能包，也无需重复下载已内置文件。上述下载说明用于维护者准备发行资源、源码资源缺失或损坏时恢复；目前没有自动下载功能。F2必须将入口指南及其配套文件纳入wheel/sdist，并在安装后验证可读，不能用“请用户另装技能”代替资源打包。

开始Word、PDF或表格任务时，按文件类型先实际读取相应 `SKILL.md`，再按需加载它引用的参考与工具，不默认同时加载三个全文；记录读取路径和哈希。它们只提供工具操作指导，不接管三手角色、中文建模论文结构或用户确认规则。资源已存在不代表运行时已自动加载，三手自动路由仍按后续F6接通和实测。

## 实际可调用入口

`modelcrew.document_tools` 提供 `verify`、`list` 和五项操作（PDF两项、Word结构检查、表格预览和完整读取）。无需安装任何外部技能；Python依赖已并入论文工具依赖清单。现有仓库仍未完成F2安装包构建，这不等于离开源码安装后的可移植验收已通过。

```powershell
python -m pip install -e ".[documents]"
python -m modelcrew.document_tools verify
python -m modelcrew.document_tools list
python -m modelcrew.document_tools pdf_fields --input C:/project/input.pdf --output C:/project/new-fields-run
python -m modelcrew.document_tools pdf_structure --input C:/project/input.pdf --output C:/project/new-structure-run
python -m modelcrew.document_tools docx_validate --input C:/project/paper.docx --output C:/project/new-word-check
python -m modelcrew.document_tools xlsx_preview --input C:/project/input.xlsx --output C:/project/new-table-preview
```

每次先验证配套资源哈希，在新目录复制输入后运行，记录输入哈希、固定版本、退出码和输出。输出目录已存在时拒绝覆盖；缺依赖返回blocked；不自动修复Word，不重算或覆盖原表格。表格预览由本项目独立实现，保留公式字符串，只显示前10行/12列，不声称公式已计算，也不替代完整附件解析。上游Excel重算脚本已随配套资源保存，但LibreOffice重算尚未实测，未开放为默认自动调用。

Python调用入口为 `modelcrew.document_tools.run(tool, source, output_dir)`。这是枢模代码中的本地工具适配入口。建模/论文请求可将本说明作为sources输入，但工具说明进入上下文不等于执行器已挂载工具。三手自动调用、执行器资源挂载及MCP端点仍待接通，不声称三手每次都会自动选择或执行这些工具。上游SKILL说明是按需参考数据，不能取代本项目中文论文、用户确认与独立质检规则。

## 本轮验证

7项专项检查全部通过：126文件完整性、84项决策覆盖、资源篡改拒绝、PDF表单提取及输入不变/目录不覆盖、PDF结构提取、表格公式预览、真实Word结构校验与缺依赖阻断。Word测试通过临时目录中的defusedxml 0.7.1补足依赖，未安装到系统Python。

验证过程中发现并修复适配层的Windows默认编码问题：子进程显式启用UTF-8。另发现python-docx默认模板的zoom元素缺少Schema必需属性；测试使用明确符合Schema的合成文档，而未修改校验规则绕过错误。上述是结构和接口验证，不是论文排版、逐页审图、W2或正式论文验收；实际论文仍走既有审批和导出流程。

## 表格完整读取与工具失败边界（2026-11-11）

本轮结合上游测试目标新增项目自编 `xlsx_read`，与只供查看的 `xlsx_preview` 分开。读取保留首行、空单元格、各工作表及公式文本，不自动推断表头，不声称公式已重算。默认最多读取1,000,000个单元格，超限明确失败，不截断后返回完整成功；Python入口可按工作表指定期望行数，缺表或行数不符拒绝返回完整结果。

```powershell
python -m modelcrew.document_tools xlsx_read --input C:/project/input.xlsx --output C:/project/new-complete-read
```

Python入口为 `modelcrew.document_tools.read_spreadsheet(path, expected_rows={"observations": 8193}, max_cells=1000000)`。输出为新的 `rows.json`，包含所有读取的行、各表实际行数和 `formula_values_recalculated=false`；原文件不变，旧输出目录不覆盖。可选依赖仍由 `documents` 依赖组提供。

外部工具返回零退出码后，还要确认要求的输出文件存在且为可解析的结构化JSON；缺输出或无效JSON登记失败。超时、非零退出和暂存输入被修改均不得返回成功回执。Word批注的本轮正反例只验证固定Apache官方辅助脚本，不等于已注册成可由三手自动调用的工具。

表格公式重算、通用公式转换及修订接受仍未注册。调用这些未知工具明确拒绝，不把预览、读取公式或文件存在当成计算或转换成功；后续F6接通真实工具和依赖后再验收，三手完整自动路由仍未实现。

## 2026-11-12 本机扩展目标的本地替代

此前保留的10项受限扩展已按用户确认逐项映射到枢模自编规范、现有工具和有边界的新实现，不复制或执行原脚本。新增 `modelcrew.office_tools` 提供实际版本诊断、DOCX格式层只读画像、DOCX/XLSX受控解包与未改成员往返；修改成员的pack明确拒绝，不自动修复/合并修订，不当正式发布口。原生OMML、全量表格读取和正式源门禁复用既有实现；通用公式编辑、修订接受和重算仍未注册。固定Apache官方126文件保持字节，外部依赖按documents组准备。本轮测试使用既有缓存defusedxml，未全局安装；画像/往返不代表结构或全页视觉通过。详见[使用与当前边界](capability-adaptation.md)。
