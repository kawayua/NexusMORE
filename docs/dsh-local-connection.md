# DSH 接入与日常使用

当前实测宿主为Windows上的DSH Desktop 0.2.2-rc.1。枢模使用独立CPython 3.13，不使用DSH附带3.12。先完成[源码安装](../README.md)、[配置](user-configuration.md)和[服务准备](environment-preparation.md)。

在README同一PowerShell终端、同一Python和工作区下执行：

```powershell
& $python -m modelcrew.dsh_integration render --python $python --workspace $env:MODELCREW_WORKSPACE
& $python -m modelcrew.dsh_integration install --python $python --workspace $env:MODELCREW_WORKSPACE --profile "$env:USERPROFILE\.dsh\profiles\desktop"
```

profile路径以自己的实际安装为准。render只显示配置，install核对当前适配资源并保留原配置；遇到同名冲突、被修改管理块或锁时拒绝覆盖。安装返回成功仍需完整退出并重开DSH，运行`/nexusmore`检查真实连接。不要仅关闭到托盘。

## 原生审阅

附上题面和数据，以自然语言说明范围。系统在原生回复中附上待审文件，点击后在文件侧栏阅读，再在原输入框明确确认当前版本或提出修改。正文和配图同时待审时展示合并页，包含完整正文、全部候选图及暂列入文标记。

确认绑定原生用户消息、对象版本及实际展示证据。模型文字、自报actor和工具权限弹窗不代替业务批准。稿件变更、对象不唯一或展示失败后，先重新展示再确认。

## 中断与回退

重开原会话先读取状态和原回执，不另建任务来掩盖原失败。执行未知时先查询原请求，不能换幂等键重发。当前适配保留`/nexusmore-review`、`/nexusmore-review-status`用于诊断回退；具体对象范围由当前待办决定。

安装器在本地保存配置备份与回退回执。只有当前配置仍匹配安装后哈希、备份完整时才可自动回退；之后有用户/宿主修改时先人工比较，不能覆盖。回退入口为`python -m modelcrew.dsh_integration rollback --receipt <本地回执路径>`，不回滚业务数据库或用户批准。

接口发现、模型提供方、数值执行和论文审查是不同检查。其他宿主或DSH新版本需要各自验证，见[兼容说明](compatibility.md)。
