# 用户配置

先运行`modelcrew init`，在用户工作区生成配置。默认位置为`%LOCALAPPDATA%\NexusMORE\workspace`；可在启动命令及注册宿主前设置`MODELCREW_WORKSPACE`。源码检出的开发默认目录与安装态用户默认目录不同，显式指定更容易避免连错任务。

| 文件/设置 | 用途 |
|---|---|
| `configs/local/settings.json` | 配置模型、数据路径、数据库变量名、检索和导出工具 |
| `configs/local/secrets.env` | 保存真实密钥和连接信息，不进入Git |
| `model.provider / base_url / name` | 由用户选择服务与具体模型；base URL由客户端追加`/chat/completions` |
| `model.api_key_env` | 密钥变量名，默认为`MODELCREW_LLM_API_KEY` |
| `database.url_env` | 数据库连接变量名；独立服务准备时生成对应连接配置 |
| `execution.image` | 受控Python执行镜像，默认`modelcrew-reference:py313` |
| `export.pandoc / tectonic / cjk_font` | 原生文档工具和字体路径 |

配置优先级为显式调用参数、进程环境、settings.json、内置默认；密钥优先使用进程环境，其次秘密文件。环境变化后重新启动相关命令/宿主。显式无效配置会拒绝，不会悄悄切换模型或数据库。

```powershell
python -m modelcrew config-show
python -m modelcrew doctor --profile workflow --services
```

`config-show`返回脱敏摘要；`doctor core`仅检查基础条件，workflow增加业务依赖和配置，full增加相应检索/导出条件。只有`--services`才执行有界只读服务探测，不启动服务或发送模型请求。诊断通过不代表完成研究任务。

不要把实际API key或数据库URL直接填进公开JSON。模型调用会将相应任务材料发送给所配服务，应确认资料使用权限和服务的数据处理条件。图片与结构化输出能力按具体模型核对，不能根据协议名称推断全部兼容。见[支持范围](compatibility.md)。
