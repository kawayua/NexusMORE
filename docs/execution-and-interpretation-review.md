# 阶段B：可替换执行与解释审核补齐

实现日期：2026-11-06。本次范围是固定样例/已审阅运行的接入、执行回执与恢复，以及结论证据审核；不运行新生成代码，不提前接入阶段C的MCP或阶段D的自动多Agent返工。

## 可替换执行后端

新增`ExecutionRequest`与统一回执，包含任务、业务版本、契约哈希、后端、操作标识、产物、模式和审核。操作标识由任务、版本、契约哈希、后端及配置共同计算。`create --executor ... --executor-config FILE`选择后端；配置与契约业务版本一同保存并受不可变记录保护。改变后端/配置通过`act --kind revise_model`创建新版本，重新等待方案确认，即使数学JSON没有变化也不静默改后端。恢复旧方案继承该版本记录的执行设置；本功能实施前的旧版本没有保存设置，恢复时需显式指定后端，不能假装已知历史配置。

| 后端 | 配置 | 行为与范围 |
|---|---|---|
| historical-fixture | 空对象 | 导入原有阶段A固定样例；mode=fixture，审核初态unknown |
| manifest-fixture | manifest_path、manifest_sha256 | 验证并冻结用户选择的样例清单，核对契约哈希与各产物字节哈希；始终标明固定样例 |
| reviewed-run | run_dir | 调用已有独立核验器登记已人工审阅、已受限执行的产物；mode=solver，不执行新代码。当前核验器仅适用于已实现的2024A问题1口径，不是任意题通用执行器 |

样例清单JSON包含`contract_sha256`、非空`description`和`artifacts`，每份产物含`path`、`sha256`、`role`。相对路径以项目根目录为基准。清单及产物均保存独立内容副本。配置文件示例：

```json
{"manifest_path":"D:/example/fixture-manifest.json","manifest_sha256":"这里填写清单文件的真实SHA-256"}
```

```powershell
python -m modelcrew create TASK contract.json --executor manifest-fixture --executor-config executor-config.json
python -m modelcrew act TASK --kind model --version 1 --decision approve --actor local-user --request-id unique-model-1
python -m modelcrew show TASK
```

方案未确认时不得派发。每次派发先写started记录，再保存成功回执与终态记录，然后另一个事务登记执行/发布结果；发布失败时，回执仍在，下一次恢复复用回执和冻结产物，不重复调用后端。失败/未知尝试保留，无结果时停在SOLVING并显示错误，不进入结果确认。固定样例读取和既有运行验证可安全重试；可能有副作用的扩展后端必须声明重放安全性或提供按operation_key查询的recover方法。结果不明且无法查询时停止，不能盲目重发。不宣称跨数据库与任意外部执行器天然exactly-once。

后端接口在Python中可注入，内置后端通过CLI及持久化配置跨进程选择；找不到后端时不自动换用默认后端。新进程若已有有效回执，可在不加载原后端的情况下完成发布。

## 解释修改后的审核

每次解释修改保留同一个execution_id，新增结果revision并撤销当前结果确认。新审核包含契约绑定、产物字节完整性、解释文本哈希和每条结论的来源、观测值、容差、单位、判定及原因。

`contracts/interpretation-claims-1.0.0.schema.json`定义结论格式，支持：按索引取标量、整体min/max/mean、与常数或另一证据值进行eq/le/ge比较。当前支持NPZ和包含顶层字段的JSON数值数组。输出ID、字段名、形状和单位必须符合契约，证据哈希必须属于当前执行和指定输出；拒绝不存在的字段、越界索引、非有限数值、无效单位及错误引用。未支持的格式返回unknown，不包装为通过。此处不进行数值求解，也不eval表达式。

示例结构如下，哈希必须替换成实际执行档案中的对应产物哈希：

```json
{
  "schema_version":"1.0.0",
  "claims":[{
    "id":"head_speed_at_t0",
    "source":{"artifact_sha256":"填写trajectories.npz真实SHA-256","output_id":"arrays","field":"speed_m_s","selector":{"index":[0,0]}},
    "operator":"eq","expected":1.0,"unit":"m/s","abs_tolerance":1e-9
  }]
}
```

```powershell
python -m modelcrew act TASK --kind revise_interpretation --version 1 --result-revision 1 --reason '核对龙头初始速率' --claims claims.json --structured-only --actor local-user --request-id explanation-1
```

`--structured-only`由系统把结论渲染成规范解释，不附加未经验证的自由叙述；所有数值断言通过且完整性通过时，审核可为passed。每条断言的容差明确保存，passed只表示该容差下的证据比较成立，不改变或放宽契约中的原求解验收容差。fixture上的passed仅说明固定数据中的断言成立，不代表新模型已运行或正确。

不使用structured-only时，reason中的自由解释也会保留。即使其中附带的结构化结论全部通过，额外自由文字的语义仍为unknown，需用户明确审阅；系统不声称理解并证明任意自然语言。没有claims的旧解释修改方式继续兼容，同样保存新的审核证据。

| 审核状态 | 结果确认规则 |
|---|---|
| passed | 仍需显式用户确认，不自动推进 |
| failed | 禁止确认；修改解释形成新revision；若问题来自模型/输入则通过新契约版本修改 |
| unknown | 用户确认时必须通过reason写明审阅意见，意见和结果revision一起留痕 |

确认前还会重新检查证据是否变化；变更或缺失需重新审核，不因旧审核曾通过而直接放行。每次解释、审核、确认及失败历史保留，旧结果不覆盖。本次没有自动回Coder/Modeler的角色路由，该部分属于阶段D。

## 验证入口

```powershell
python -m pytest tests --integration -q
python -m scripts.verify_executor_review
```

脚本使用TEST_SIMULATED_USER测试任务、真实PostgreSQL和固定数值证据，覆盖回执保存后/执行登记前中断与重启、CLI恢复、三种审核状态、确认拦截、复用计算以及重复确认。它不会修改dragon-q1的已有确认，也不会发起模型调用或新代码求解。
