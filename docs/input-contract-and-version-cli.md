# 输入契约、版本档案与恢复功能

实现日期：2026-11-06。通过本地可信CLI使用；actor是审计标签，不是身份认证。

## 输入结构与草稿

`contracts/input-templates-1.0.0.json`预设表格、时间序列、数组、嵌套JSON、图像、地理数据、参数集合、说明文档和输出模板的基本描述项目。当前解析器支持CSV/TSV/XLSX、NPY/NPZ、JSON/GeoJSON、常见图片、文本/Markdown/PDF文本层；其他类型产生阻塞问题，不冒充已解析。表格前六行用于展示，不据样本推断整列语义或宣称全量类型校验完成；扫描型PDF和图示仍需用户核对。

契约1.1.0为每个文件增加structure，保存模板标识与版本、实际观测结构、字段类型/形状/单位、带来源的要求及待确认项。模板规则与本题业务语义分开。旧1.0.0契约继续可验证，不修改已存v1/v2。

```powershell
python -m modelcrew inspect-input 'D:\big-third-up\A题\附件\result1.xlsx' --role required_output_template
python -m modelcrew draft-inputs contracts/examples/valid-2024-a-q1.json --output stage-b/runs/input-draft.json
python -m modelcrew validate stage-b/runs/input-draft.json
python -m modelcrew resolve-input stage-b/runs/input-draft.json --input-id input0 --question-id statement --resolution '这里填写核对题面后的具体意见' --output stage-b/runs/input-draft-reviewed.json
```

输出文件使用独占创建，不覆盖已有草稿。`resolve-input`只写候选文件，不代表用户已确认整份方案；涉及单位或字段要求变化时，应同步修订结构中的fields/requirements。未解决的阻塞问题、文件哈希变化或实际观测结构不一致会阻止1.1.0方案确认。未变的文件结构在方法改版时可直接继承。

完整契约草稿生成命令如下，使用.env或环境中的MODELCREW_LLM配置，会调用模型并产生费用；不会运行模型代码、写入任务或自动确认。每次输出目录必须全新，保存请求、实际方案输出、下一步建议、契约、用量和失败信息。

```powershell
python -m modelcrew generate-draft --statement 'D:\big-third-up\A题\A题.pdf' --attachment required_output_template 'D:\big-third-up\A题\附件\result1.xlsx' --scope '2024年A题第一小题' --output stage-b/runs/new-draft-bundle
python -m modelcrew create new-task stage-b/runs/new-draft-bundle/contract.json --draft-dir stage-b/runs/new-draft-bundle
```

带draft-dir创建时，方案说明和下一步档案与任务在同一业务事务中入库；任意条目失败全部回滚。完整模型草稿目前仅通过模拟模型接口测试，尚无本轮真实模型生成验收证据。

## 每版档案和回退

```powershell
python -m modelcrew versions dragon-q1
python -m modelcrew dossier dragon-q1 --version 2
python -m modelcrew record dragon-q1 --version 2 --kind feedback --text-file feedback.txt --actor local-user --request-id feedback-unique-001
python -m modelcrew act TASK --kind restore_version --version 2 --source-version 1 --reason '填写恢复原因' --actor local-user --request-id restore-unique-001
```

record支持proposal、feedback、next_step、change_note、code、experiment；可通过--artifacts传入含path/sha256/role的数组文件，并通过--metadata附加模型名、用量或执行状态等信息。支持将失败尝试以experiment条目保存，不能把未执行标成成功。新产物保存内容寻址副本，原运行目录被重写不会覆盖档案副本；文件系统对象不代表业务提交，失败事务可能留下未引用副本。读取档案时重新检查文件字节完整性。

档案同时关联完整契约、与父版差异、所有执行、各结果revision、确认/指导事件和确认摘要。历史版本未记录的Agent原始说明、下一步等明确列为缺失，不根据后来理解伪造。旧执行只登记了原路径和哈希，没有自动生成过去的文件副本。

恢复旧方案会创建新版本，parent_version指当前版，restored_from_version指被恢复版；检查原输入文件仍可取得且哈希匹配，清空当前执行和确认引用，并重新等待方案确认。历史版本及结果不删除，历史确认不迁移为新确认。重复相同request_id不重复创建；同一request_id换内容会被拒绝。查看档案不会切换当前版本。

## 执行接口与解释审核

任务持久化executor_key，Workflow可注入执行后端。默认historical-fixture经接口读取历史样例并保存副本，仍明确是fixture，不代表按新契约重算；找不到配置后端时拒绝恢复，不静默换用默认实现。真实求解继续通过人工审阅、受限Docker执行及attach-solver登记。

修改解释时复用execution_id，重新执行契约绑定与产物完整性审核，保存新证据和审核时间。文件变化/缺失或绑定错误使审核failed并阻止确认；自由文本解释的语义仍为unknown，需要用户确认时通过--reason写明审阅意见。确认前再核对审核产物是否变化。该审核不等于通用数学或文字语义证明。

## 验证

```powershell
python -m pytest tests --integration -q
python -m scripts.verify_version_recovery
```

集成测试使用真实PostgreSQL和checkpointer，任务与操作者均标为测试；部分求解登记事务测试使用模拟验证器，并非实际重跑数值求解。重启脚本只操作专用数据库和测试任务，在两个确认等待点及恢复旧版已提交/检查点未推进时各重启一次，核验新进程恢复和幂等。

容器modelcrew及modelcrew-907b747d1efd4311是一次性求解作业，退出0表示完成；日常只需数据库容器modelcrew-stage-b-postgres常驻。不要用重启历史求解容器来启动系统服务，其原目录可能被程序重新写出。当前还没有网页服务容器。

执行接口与解释审核的后续补齐以[专项说明](execution-and-interpretation-review.md)为准：增加CLI可选后端、按版本绑定的配置、持久化回执与恢复，并支持按证据核对数值结论。自由文字仍保留人工审阅关卡。
