# 源码快照范围

本仓库首个快照保存 ModelCrew 源码、工作流契约、迁移脚本、测试、配置示例、项目自编算法索引与论文规则，以及选入的阶段总结。当前工程状态见 [E 阶段收口报告](../stage-e/implementation/20261110-upstream-continuation-v1/E阶段联合验收收口报告.md)，后续安装、宿主接入与发布工作见 [F–H 路线](open-source-harness-roadmap.md)。

运行时数据库、密钥、任务原始附件、过程证据及论文成品保留在原工作区。历史文档中的部分路径指向这些本地材料。仓库未纳入未确认可再分发的外部算法原文、引用摘录和论文模板；算法索引仍会标出相关资料，论文上下文入口也仍校验 [workflow.json](../resources/paper/workflow.json) 列出的文件。使用对应流程前，需自行合法获取所需资料，按配置放到 `resources/algorithms/reference/` 和 `resources/paper/reference/` 的对应位置。包含赛题全文的两个历史输入契约样例也保留在本地。部分验收脚本和测试还需本地数据或服务，无法仅凭这个快照复现全部历史结果。

这是项目当前成果的 Git 快照，尚未附开源许可证；安装、第三方资源整理和完整 harness 接入仍以 F–H 的实际交付为准。
