> 当前结论（2026-11-02）：阶段A单题基线已由用户接受，详见[验收小结](../stage-a/2024-A-problem-1/stage-a-summary.md)。以下保留准备过程和历史状态。

# 阶段 A 准备情况记录

更新日期：2026-11-01。当前试验题已切换为2024年A题“板凳龙”问题1，旧选题不再作为活动基线。

## 已核对

本地目录`D:\big-third-up\A题`包含三页题面PDF，以及result1.xlsx、result2.xlsx、result4.xlsx。已读取题面、核对图4及问题1模板。问题1使用result1.xlsx，其他模板留作后续范围之外的材料。官方链接待补；文件哈希保存在stage-a/2024-A-problem-1/input-manifest.json。

已建立范围说明、参数文件和运行前人工验收清单。人工参考程序现已完成数值求解，两次运行各通过14项核验，内部轨迹数据完全一致；尚未调用MiMo或完成LLM生成代码基线评测。结果入口见stage-a/2024-A-problem-1/reference-result.md。

Git仓库已初始化；当前remote列表为空，尚未关联远程、提交或推送。用户提供远程地址为https://gitee.com/yaukin/modelcrew-agent.git，远程为空是用户提供的信息，本轮未再次在线检查。沙箱用户所有者检查需使用命令级safe.directory参数，不修改全局配置。

Docker客户端存在，但本轮复测Linux引擎管道不存在，尚不能运行容器。不把命令可用视作执行隔离已就绪。

## 模型与下一步

模型配置沿用mimo、候选标识mimov2.6pro、https://api.xiaomimimo.com/v1、OpenAI兼容接口。实际标识和兼容性未验证；.env.example密钥为空，不读取或展示真实密钥。用户未设置费用上限，不做无限后台调用。

下一步接入模型提案与代码生成，并使用已完成的参考计算作独立对照。人工参考、固定联调及LLM运行分别记录；生成代码执行前完成审阅与受控环境验证。

## MiMo独立基线进展

已接通真实API并将候选标识匹配为mimo-v2.6-pro。共3轮尝试：2次输出截断，1次完整方案和代码但数学审阅失败。未执行生成代码，未完成数值对比，不能宣称阶段A整体通过。详情见stage-a/2024-A-problem-1/mimo-baseline-result.md。Docker启动失败原因已定位到Inference Manager本地监听初始化。

## 更换模型后的状态

当前供应商bailian、模型deepseek-v4.1-flash-1017。一轮代码截断后，仅重试代码阶段获得完整程序；未提供参考或论文。完整代码静态数学和安全审阅通过，Docker引擎仍未就绪，因此运行和参考数值对照未测。详情见stage-a/2024-A-problem-1/model-retry-status.md。

## 2026-11-02 求解执行更新

Docker引擎已正常，ModelCrew求解容器已创建并保留，百炼代码运行退出码0，22项参考对照通过。详见`stage-a/2024-A-problem-1/docker-execution-result.md`。此前未执行状态为历史记录。
