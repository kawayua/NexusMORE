# 环境与服务准备

当前基线是Windows x86_64、CPython 3.13、Docker Desktop/WSL2 Linux amd64容器。先安装并启动Docker，DSH由用户准备。Word原生渲染另需本机已授权Microsoft Word及所用中文字体。

源码安装见[README](../README.md)。设置业务工作区并执行init后，可运行：

```powershell
python -m modelcrew environment setup
python -m modelcrew.workflow_mcp migrate
python -m modelcrew environment status
python -m modelcrew doctor --profile workflow --services
```

setup准备工作区独立的PostgreSQL/Qdrant、迁移、执行器和文档工具，可能下载镜像及固定版本工具；不安装Docker、DSH、Word或模型密钥。独立服务绑定工作区，已有自定义数据库/管理配置会保守拒绝接管。

| 分步命令 | 用途 |
|---|---|
| `environment prepare` | 创建工作区专用服务配置和凭据 |
| `environment up / status` | 启动或检查服务 |
| `environment migrate` | 补齐业务数据库迁移 |
| `environment executor` | 准备默认受控执行镜像 |
| `environment tools` | 准备原生文档工具 |
| `environment restart / stop` | 重启或停止工作区服务，保留数据卷 |

默认算法资料读取不需要向量模型。论文语义检索需另准备本地嵌入模型、Qdrant和有来源的论文索引；`environment embedding`涉及较大权重下载，`environment retrieval --output <新目录>`只提供合成部署探针，不自动构成真实论文库。

正式LaTeX基线为Tectonic 0.17.0、Pandoc 3.6.4。首次Tectonic编译可能下载宏包；离线前需要实际缓存和完整依赖。任务容器执行期间禁网，所需科学/绘图依赖及字体应预先准备，不能依赖求解中临时安装。

不要通过删除共享卷、重置业务库或全局Docker清理来修复工作区。新设备完整安装尚待验证，保留实际系统、版本和缺项记录。见[排错指南](troubleshooting.md)。
