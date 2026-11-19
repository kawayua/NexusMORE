# H5 首发候选准备

H5负责生成可审阅的本地发行候选、文件校验和、依赖/许可清单、敏感材料检查以及实测与限制说明。当前组合方案、历史许可待办和用户批准沿用原记录；本页不授予第三方许可，也不将工程检查写成法律合规结论。

## 本轮入口与范围

在已具备开发依赖的项目根目录运行：

```powershell
python -m scripts.build_release_candidate --output runs/release-candidates/first-release-20261119-r1
```

输出目录必须不存在，且位于本仓库的`runs/release-candidates/`内。命令本地构建wheel/sdist，从安全解包的sdist重建wheel，并生成哈希、依赖/许可元数据、扫描报告、来源身份和候选说明。它不安装到系统、不启动业务服务、不调用模型、不修改DSH配置、不提交Git或公开上传。构建使用当前已安装setuptools，不冒称隔离/可重复二进制构建。

`configs/distribution-files.json`逐项限定额外源码包文件，运行资源仍以pyproject及资源清单为准，测试仅含Python/MJS源文件。H4当前使用/贡献入口及其必要直接链接目标随sdist携带；原始历史页面中的本机档案链接仍保留历史语义，不把私有档案打包。`audit_sdist`在解包前拒绝越界、重复、链接/特殊成员及非白名单文件，并逐字核对必需源码；wheel使用已有精确资源审核。

## 如何阅读结果

输出包含`preparation-result.json`、`SHA256SUMS`、当前wheel/sdist与重建审计、`dependency-inventory.json`、`installed-constraints-win-py313.txt`、`license-inventory.json`、`archive-scan.json`、`source-identity.json`和`RELEASE_NOTES.md`。可审阅交付归入候选ZIP；发现高置信敏感内容时保留失败报告并拒绝生成汇总ZIP。

依赖清单是当前解释器中`paper,dsh`依赖闭包的实际元数据，区分未安装、版本冲突和所用extra；constraints仅为这个已安装环境快照，不是带下载哈希的完整安装锁，不声称适用于其他平台。许可清单收集本机发行包的声明和实际通知文件身份，不导入依赖代码，且不证明所有原生组件义务已清除。

敏感检查覆盖候选wheel、重建wheel和sdist的实际成员，拒绝私密目录、凭据文件、路径逃逸和特殊成员，检查固定高置信令牌/私钥模式；只输出规则、成员名、行号及匹配指纹，不回显匹配原文。个人本机路径列为人工复核项，二进制/不可解码内容单列。合成测试和历史示例也可能产生复核项，不能擅自改写冻结材料来清零。规则扫描不是完整隐私审计；需要人工复核的事项不能写成通过。

## 保留的待办与后续动作

原F5延期记录仍有原生wheel精确来源映射、PyTorch非Git构建输入、官方PyMuPDF构建对应、工具/镜像/权重/字体的实际分发范围，以及对应源码可获取安排等事项。新候选绑定新的项目源码和哈希；旧源码材料包仅是历史证据，不能自动当成新候选的完整对应源码证明。详见[原待办](release/licensing-deferral-20261114.json)、[原生来源核对](source-completeness.md)及[组合发行说明](combined-distribution-license.md)。

当前保留`Private :: Do Not Upload`和`0.1.0.dev0`，候选用独立目录和内容哈希区分；这不是正式版本发布。实际公开前需核对这些待办、敏感复核项、最终源码获取与相邻文件安排，并取得对应外部发布指示。

用户已明确干净环境/新设备测试移到开源后亲自尝试，本轮不以此阻塞准备，也不登记通过。G沿用既有本地Windows/DSH实测，H1/H3额外评测不在本轮执行，不宣称其他宿主或新题总体性能。顺序依据见[用户决定](release/h-stage-sequencing-decision-20261119.json)，日常使用见[使用指南](user-guide.md)。

本地维护检查：`python -m pytest tests/test_release_candidate.py tests/test_package_distribution.py tests/test_release_source_evidence.py -q`。它们核对包边界和故障拒绝行为，不替代真实用户批准、独立论文质检或公开发布审查。
