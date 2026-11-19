# 可公开审查的小样例候选 v1

这里的两道题、整数输入和参考值均为本项目新编合成材料，按仓库 `LICENSE` 的 AGPL-3.0-only 管理，无第三方赛题全文、私有数据或历史成品。具备清楚的来源及许可标记不等于已授权公开发布；整体仍保持 Private，公开发行按 F5/H5 单独验收。

`reservoir-balance.json` 检查逐步水量平衡；`integer-allocation.json` 检查有界整数分配。题面及输入在 `statement` / `input`，参考值在 `expected`。真实宿主联调时只向模型提交题面和输入，参考值仅供评测端核对；这里不宣称参考值对公开模型保密。

在仓库根目录运行 `python -m scripts.check_evaluation_data`，使用 Python 标准库重算参考值、核对文件哈希与分层边界，不调用模型、Docker、数据库或宿主。该命令通过仅表示数据包机械一致，不能作为安装、MCP、真实求解或论文质量通过证据。需在 H2 另行经真实宿主执行。

两个样例均无论文交付要求；不能据此减少研究题的九候选/八正式图、人工确认、独立检查或全页 PDF 要求。评测方案见 `docs/evaluation-protocol.md`。
