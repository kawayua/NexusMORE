# 贡献指南

欢迎提交文档、可复现问题、合成测试和代码改进。先读根目录[AGENTS.md](../AGENTS.md)，能力边界见[兼容说明](compatibility.md)。

## 开发与检查

在独立CPython 3.13环境中安装基础开发依赖：

```powershell
python -m pip install -e ".[dev,workflow,dsh]"
python -m scripts.check_public_repository
python -m pytest -q
```

本公开树保留的测试使用仓库资源和合成输入，不需要模型密钥、实际DSH、Docker、Word、研究原题或业务数据库。它们验证资源、契约、工作区、配置/注册边界和公开内容，不代表新设备完整业务或科学质量通过。完整业务开发另按[README](../README.md)准备依赖与独立工作区。

## 代码与文档

每次改动集中解决一个问题，说明触发条件、最终行为、实际执行的检查和未覆盖范围。文档命令需与CLI核对，注明联网、启动服务或模型调用；不要把没有执行的检查写成通过。

Python源码在`src/modelcrew/`，宿主源在`src/harness/`，包内宿主副本在`src/modelcrew/resources/harness/`。两份适配资源须同步；运行资源清单及其哈希也需随实际变更维护。第三方原文件与必要许可证/署名照实保留。

不绕过真实用户确认、独立质检、版本与幂等，不修改旧批准或回执来消除失败。数值、模型、正文、图表变更按影响生成新版本和审阅。

公开树的文件范围由`configs/public-repository.json`登记。新增文件时同时维护清单；重新生成公开视图时应将改动同步回维护源，避免后续导出丢失。不要加入过程报告、私有题面、真实密钥、数据库、运行目录、历史成品或未获授权材料。

## 问题与提交

使用[缺陷模板](../.github/ISSUE_TEMPLATE/bug_report.md)、[需求模板](../.github/ISSUE_TEMPLATE/feature_request.md)或[PR模板](../.github/pull_request_template.md)。提供版本、平台/宿主、发生阶段、最小复现和必要脱敏片段，优先用原创小样例，勿公开整份数据库和运行记录。

贡献内容应有权提供，并遵守[LICENSE](../LICENSE)、[第三方声明](../THIRD_PARTY_NOTICES.md)和[组合发行说明](combined-distribution-license.md)。提交或测试通过不代表业务批准、发行许可清除或发布版本。
