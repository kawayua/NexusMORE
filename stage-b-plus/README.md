# B+：数学交接与版本确认

状态：已实现并通过工程验收；未替用户确认新的正式建模方案或结果。[验收报告](acceptance-report.md)记录范围、实测与限制；[接口设计](../docs/mathematical-handoff.md)解释内部结构和变更规则。

本轮将A+人工审查过的材料转为独立版本的MethodSelection、MathematicalDossier与MathematicalPackage Schema，通过不可变记录绑定业务契约版本。原Model Contract 1.0.0/1.1.0与既有确认原样保留。

查看[板凳龙数学提案样例](proposals/bench-dragon.md)或[连续资源分配提案样例](proposals/resource.md)。前者对应已确认v2契约内容的迁移样例，后者有[独立LP契约](examples/resource-contract.json)；这些文件均是待审阅交接材料，不表示正式任务已挂载新数学包或获得新用户确认。JSON样例与四份非法样例位于examples/。

## 运行与复核

使用原有requirements-stage-b.txt、requirements-stage-c.txt环境及PostgreSQL；本轮未增加第三方依赖。先执行增量迁移：

```powershell
python -m modelcrew init-db
python -m modelcrew math-show TASK --version 1
python -m modelcrew math-publish TASK --version 1 --package PACKAGE.json --actor local-user --request-id math-001 --reason "首次发布，等待审阅"
```

math-publish仅支持未确认版本的首次挂载和现有版本的排版修订；已确认的旧任务需创建新业务版本，不允许把旧确认追认为新数学包的批准。数学变更使用：

```powershell
python -m modelcrew act TASK --kind revise_mathematics --version 1 --math-package CHANGED.json --actor local-user --request-id math-002 --reason "修改变量定义域"
```

实际方案确认前，先用math-show审阅完整提案，随后提交返回的semantic_sha256及审阅理由：

```powershell
python -m modelcrew act TASK --kind model --version 2 --decision approve --math-semantic-sha256 REVIEWED_HASH --actor local-user --request-id model-002 --reason "已审阅假设、定义域、推导与契约引用"
```

确认会触发所配置执行后端，不能把上述占位示例当作正式任务批准。结果确认同样传入math-semantic-sha256，并提供result-revision；结果解释变更沿用原B阶段审核和重新确认机制。

工程演示只创建唯一命名的合成任务，不调用模型、不求解正式赛题：

```powershell
python -m scripts.verify_bplus_handoff
New-Item -ItemType Directory -Path stage-b-plus/runs -Force | Out-Null
$bplusTemp = Join-Path (Get-Location) ('stage-b-plus/runs/pytest-' + [guid]::NewGuid().ToString('N'))
python -m pytest tests --integration -q --basetemp $bplusTemp
```

最新证据：46项B+专项测试、227项全量回归、22项流程演示均通过。[流程摘要](verification-summary.json)指向不可覆盖run。测试和演示中的TEST_SIMULATED_USER是测试标签，不是真实用户验收；本地API沿用既有可信本机边界，不提供身份认证。

C+仍需实现算法检索增补、真实绘图、LaTeX/PDF编译与查看排版。本轮只提供同源Markdown与TeX片段，未编译或声称图片已生成。runs与原有大体积工件被Git忽略，本地证据不自动随仓库分发。
