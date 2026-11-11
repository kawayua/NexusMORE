# 阶段 A+：方法选择与数学基线

状态：已实现并核验；A+用户验收尚未记录。[验收报告](acceptance-report.md)说明完成范围、实测证据和后续边界。

先读[方法选择](method-selection.md)，再读[板凳龙数学稿](math/bench-dragon-mathematics.md)和[跨结构资源样例](math/resource-mathematics.md)。JSON草稿与同源TeX位于math/，来源记录在sources/，验证索引为[verification-summary.json](verification-summary.json)。原始算法资料未改写，索引当前为1.1.1。

## 复核入口

```powershell
python -m scripts.verify_aplus_baseline
python -m pytest tests/test_aplus.py -q
```

第一条验证命令只读取现有本地题目参数、已确认v2数组及参考实现，执行新的独立诊断与小型合成LP，保存stage-a-plus/runs/下独立run。需已有本地运行材料，缺文件/哈希不符应失败，不下载外部答案代替。依赖见[requirements-aplus.txt](../requirements-aplus.txt)。

`python -m scripts.prepare_aplus_baseline`可重建人工编写的两题方法/数学JSON与TeX；它不是LLM生成器，也不代表用户确认。读源记录绑定索引与实际读取范围，改原文后需重新审核和冻结，不只是更新哈希便视为数学通过。

49项直接检查、30项新增专项测试通过；现有151项加新增30项的全项目181项回归通过。全量测试在本机要使用工作区全新临时目录以避开系统Temp权限问题，例如：

```powershell
$aplusTemp = Join-Path (Get-Location) ('stage-a-plus\runs\pytest-' + [guid]::NewGuid().ToString('N'))
python -m pytest tests --integration -q --basetemp $aplusTemp
```

本阶段不要求完整论文，不编译PDF、不生成新科研图、不发布B+版本Schema、不修改旧确认。复用当前上下文与来源，不能宣称为盲测或严格独立模型求解。下一步交给B+做数学包/业务版本交接，再由C+真实编译和查看导出。
