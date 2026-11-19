# 贡献指南

欢迎通过问题报告、文档修订、合成测试或代码改进参与枢模 · NexusMORE。开始前阅读根目录 [AGENTS.md](../AGENTS.md)；当前范围和待验证事项见[兼容说明](compatibility.md)。当前开发线尚未公开发行，取得源码不表示所有历史材料可再分发。

## 开发环境

在源码根目录使用CPython 3.13和独立venv。以下是文档/基础维护的最小安装，不配置真实密钥，不连接业务数据库：

```powershell
py -3.13 -m venv .venv
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python -m pip install -e ".[dev,dsh]"
& $python -m pip check
```

开发完整业务时按 [README](../README.md) 另装 `.[paper,dsh,dev]` 并准备独立测试服务。`src/modelcrew/`是Python源码，`src/harness/`是项目自编宿主JS源，`src/modelcrew/resources/harness/`是安装包副本；两份宿主资源需要同步且核验哈希。目录用途和命名见[仓库布局](repository-layout.md)，不在根目录新增阶段目录或研究产物。

## 不需要私有数据的基础检查

以下检查仅使用仓库文档、配置和合成测试，不要求模型密钥、Word、Docker、DSH安装、研究题原件、历史成品或业务数据库，也不调用付费模型：

```powershell
& $python -m scripts.check_public_documentation
& $python -m scripts.check_repository_layout --final
& $python -m pytest tests/test_public_documentation.py tests/test_repository_layout.py -q
```

文档检查范围由 `configs/documentation-checks.json` 明确列出；默认检查当前使用/贡献入口的本地链接、路径边界、文本控制字符及目录规则，不递归宣称所有历史文档都完好。原始旧README快照只校验保留哈希，其旧相对链接沿用原语义。

已安装完整业务依赖时，可额外运行 `& $python -m scripts.check_public_documentation --check-cli`，检查文档关联入口的真实`--help`是否包含所需参数；此选项不会执行安装、服务启动、迁移、宿主注册或任务求解。无需安装完整依赖的文档贡献可只跑默认检查。

修改具体业务后，再选择相关单元测试。`python -m pytest` 全集含历史/可选依赖测试，不能把最小依赖环境中的缺项说成业务回归结论。PostgreSQL集成测试只在专用测试工作区和数据库中显式启用`--integration`；测试初始化会执行迁移，绝不能指向自己的正式任务库。真实Docker、宿主、模型与导出检查按实际条件另记，未运行项如实说明。

## 提交改动

一个改动集中解决一个问题，保留无关工作区修改。说明触发条件、修改后的行为、实际检查结果及未覆盖范围；缺陷修复优先增加能复现问题的合成测试。文档命令必须与实际CLI核对，标清是否联网、写配置、启动服务或消耗模型额度。

不要修改旧批准、冻结上下文、历史回执、已接受误差或上游原始文件来消除失败。需要改变数值、模型、正文、图或证据时生成新版本并按影响审查。三手与独立质检、版本/幂等、真实用户决定及同attempt复核额度属于业务边界，不能为方便测试绕过。

变更包内资源时维护相应清单和哈希，保留来源、许可证及必要署名；仅改文件名不解决授权。新增依赖说明用途、版本及许可影响。用户文档与源码仓库内容、wheel/sdist资源清单是不同交付范围；当前H4没有重建发行包，H5需要核对发行候选中的文档和材料覆盖。

PR使用[提交模板](../.github/pull_request_template.md)，不要把没有执行的检查勾成通过。维护者合并、公开推送和发布仍由实际授权流程决定；本指南不代替业务用户批准。

## 报告问题与提出需求

缺陷使用[问题模板](../.github/ISSUE_TEMPLATE/bug_report.md)，功能建议使用[需求模板](../.github/ISSUE_TEMPLATE/feature_request.md)。提供版本、实际系统/宿主、发生阶段、最小复现、预期与实际结果、错误代码及必要的脱敏片段。若与新设备有关，写明哪些步骤成功、哪些尚未尝试，不把一个环境的问题泛化为所有环境。

公开前移除密钥、数据库连接串、个人身份和路径、私有题目、原始聊天及未获许可附件。可用原创小输入复现时优先用合成数据；原始证据在本机保留，不直接贴整份数据库或运行目录。涉及密钥/私人材料时先停止公开粘贴，使用维护者实际公布的非公开联系渠道；本项目没有在这里承诺一个不存在的邮箱或安全平台。

## 许可

贡献内容需要有权提供，并适用仓库实际许可证及第三方例外，详见 [LICENSE](../LICENSE)、[第三方声明](../THIRD_PARTY_NOTICES.md)及[组合发行说明](combined-distribution-license.md)。不要求捏造作者签字、代签用户批准或删除合法署名；发现来源不明材料请说明位置与疑点，先保留证据再处理。
