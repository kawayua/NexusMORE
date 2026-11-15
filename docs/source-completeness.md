# 原生构建、组件许可与对应源码核对

2026-11-14：本轮证据收集、原生功能重建和材料打包完成；**F5 整体仍待关闭发布门禁，未登记完整对应源码或公开发行许可全部通过。** 上次 AGPL 组合方案、历史包与批准保持原字节，不将新材料追写到旧记录。

## 已完成

对独立运行环境盘点 124 个第三方 distribution（包括传递依赖和安装工具，并非 124 个直接业务依赖），取得其官方固定版本元数据与 121 份 PyPI 摘要核验的 sdist。没有 sdist 的 psycopg-binary、pywin32、torch 改为固定官方源码提交；torch 按实际 Windows wheel 的内部 commit 递归收集根仓库和子模块，共 73 份唯一修订归档。核对发现 PyPI wheel 内部版本本就是 2.6.0+cpu；版本文件和全部 11 个 DLL 与已安装运行环境逐字节相同，没有把 v2.6.0 标签源码误作实际运行提交。

修正许可盘点器遗漏嵌套 BUILD_LICENSES 的问题，保留安装树 233 份许可/通知原文；再从源码包中提取 662 份按文件名识别的原文供复核。tokenizers 安装树缺少完整许可，但官方 sdist 含 Apache-2.0 原文，已补到源码材料；未因主体 MIT/BSD/Apache 就忽略 orjson、certifi、tqdm、NumPy/SciPy 等逐文件条款和运行时例外。

取得 PostgreSQL/libpq 18.3、OpenSSL 3.6.2 官方源码与上游摘要，补充 GPL 全文；保留 psycopg-binary 的 LGPL 原文。取得 Python 3.13.5、Pandoc 3.6.4、Tectonic 0.17.0、Qdrant 1.19.1、PostgreSQL 16.14 镜像对应主项目与固定 BGE 版本的主许可材料。数据库服务版本与驱动内 libpq 版本分开记录；主许可不等于所有嵌套组件已通过。

**PyMuPDF 1.27.2.3 / MuPDF 1.27.2 已在本机真实编译生成 Windows x86_64 CPython 3.13 wheel。** 使用 MSVC、SWIG 4.4.1、libclang 18.1.1，保留构建参数、官方原始源码哈希、两处本地兼容处理及补丁：VS 升级输出库路径复制，以及普通 GIL 构建移除上游不被接受的 `nogil=False` 参数。本地 wheel 未覆盖已安装产品或替换官方依赖，不声称字节相同或相同 ABI 标签。普通用户不需要安装这些编译工具。

将本地 wheel 解包至新隔离目录，使用 `python -I` 显式加载该目录内模块，使用两份既有工程 PDF 共 4 页，全部提取文字、核对页数及替换字符、渲染、保存哈希并逐页实际查看；中文和公式清晰，未见缺字、截断或重叠。没有新建正式论文，也没有登记独立 W2 或用户批准。原生功能通过不代表所有发行材料已通过。

## 交付材料

私有验证目录为 `tmp/release-source-completeness-validation-20261114/`。最终证据包位于 `source-notice-packet-final/`，共 200 份源码归档：项目 1、Python sdist 121、psycopg-binary/pywin32 固定仓库 2、torch 源码图 73、libpq/OpenSSL 2、MuPDF 1。每份记录 SHA256，包含逐源通知、完整许可、版本元数据、构建补丁和重建说明，绑定上次已验收的运行 wheel 哈希。原始环境变量日志、密钥、论文、字体、权重及原生二进制不进入包。

部分冻结 build 输出文件在本次进程下拒绝读取，未修改其 ACL；从先前冻结的成对审阅 ZIP 中恢复相同 sdist/wheel 字节，并按旧 build-audit 中 SHA256 核验一致。该恢复留有记录，不修改或重签原始构建证据。

维护入口为 `scripts/audit_release_licensing.py`、`scripts/collect_release_sources.py` 与 `scripts/prepare_release_source_evidence.py`。最后一个脚本只打包明确白名单证据，校验固定输入、拒绝路径越界、忽略归档链接并限制单份许可大小，不执行上游源码。实际 ZIP 完整性与源码读回哈希均核验。相关回归 26 项通过。

## 尚未关闭的门禁

| 项目 | 已有证据 | 仍需完成 |
|---|---|---|
| 其他原生 wheel | 上层源码与完整已附通知；libpq/OpenSSL 版本源码 | PDFium hash=null 的精确源码/构建来源，Windows vcpkg 基线和补丁，lxml/Pillow/数值库/Rust wheel 等外部构建输入按实际组件核对 |
| PyTorch 原生组件 | 实际 wheel/DLL 对齐，Git 子模块源码图齐全 | MKL2025.0.1 的实际链接/装载与适用材料、非 Git 下载输入；不因主项目 BSD 自动通过，也不直接判定不可发行 |
| PyMuPDF 官方二进制映射 | 本地功能重建及补丁通过 | 官方 wheel 精确构建映射、本地重建产物是否选作发行版本的对应材料；本次未自动替换 |
| 原生工具、服务、模型和字体 | 固定版本主许可已收集 | 按实际分发方式核对 TeX 资源、容器系统组件、模型权重和字体；宿主 Word/MSVC/字体授权不随本产品自动授予 |
| 正式源码交付 | 本地成对运行候选与扩展材料包 | 最终二进制相邻的可获取完整源码安排尚未发布；没有公开地址或书面提供承诺。远程服务按实际部署另处理 |

这些均保留为公开发布门禁，当前继续 Private 开发；未执行 Git 提交、推送、公开上传或采购。用户已明确跳过的全新 Windows/空 Docker 镜像首次安装验证仍为用户例外，不伪造通过，也不重新混入这批许可验收。机器回执见 `docs/release/source-completeness-20261114.json`。
