# 版本化建模契约 v1.0.0

Schema见`model-contract-1.0.0.schema.json`，采用JSON Schema Draft 2020-12。所有对象关闭额外字段，必需数组非空，字段ID需唯一、来源与检查引用需存在；派生参数必须写推导。公式均为描述性文本，程序不eval公式。

| 字段 | 含义与边界 |
|---|---|
| schema_version | 契约格式版本；不等于业务契约版本号 |
| problem | 问题、范围和simulation/optimization/prediction/analysis目标 |
| sources | 题面、用户指导或参考来源及可得的哈希；不能将同题论文伪装为题面 |
| inputs | 输入角色、路径和字节哈希，支持追溯输入快照 |
| conventions | 单位、坐标、时间零点、方向、节点索引 |
| parameters | 给定/派生/假设数值及来源；物理单位不隐含换算 |
| variables | 变量数学含义、单位和定义域 |
| assumptions | 非题面事实的建模选择及来源 |
| constraints | 表达式、物理意义和对应检查ID |
| method | 求解步骤、选根规则、允许的等价变化和需重新确认的变化 |
| outputs | 产物路径、文件格式、字段形状、单位及显示精度 |
| checks | 稳定ID、独立核验方法、容差、证据要求；初态必须unknown |
| risks / alternatives | 不确定性、限制与备选思路 |

`python -m modelcrew validate contracts/examples/valid-2024-a-q1.json`执行结构与引用校验，另返回本题派生孔距检查。合法样例的数学状态仍为unknown；只检查了少量关系，没有自动证明整个模型正确。

样例：

- `valid-2024-a-q1.json`：结构与引用合法的提案，尚待用户审阅。
- `invalid-missing-checks.json`：缺少验收检查。
- `invalid-shape.json`：输出shape包含零维度。
- `invalid-reference.json`：约束指向不存在的check_id。
- `schema-valid-math-wrong.json`：JSON结构合法，但龙头孔距误写0.55 m；本题关系检查会报错。

业务契约版本由数据库分配1、2、3…；每个版本保存完整JSON及规范化内容SHA-256、父版本和用户指导。业务确认、request_id、execution_id、thread_id、结果revision独立关联，不把“已确认”写进可任意提交的数学JSON。

模型/输入变更创建新版本并重新确认，使当前执行引用和结果失效，旧记录只读保留。解释修改产生同一版本下的新结果revision，复用原执行，但必须重新确认结果。代码实现偏离硬性方法要求也必须新版本确认；本版仅声明这条规则，尚未自动比较生成代码语义。

用户补充的版本档案、回退语义及系统起草契约要求见 [版本档案与契约草稿设计](../docs/version-records-and-contract-drafts.md)。该文区分现有能力与待实现项，保留历史契约不变。

## 1.1.0兼容扩展（2026-11-06）

新增`model-contract-1.1.0.schema.json`和`input-templates-1.0.0.json`。新契约必须为每个input提供structure，描述模板版本、观测结构、字段类型/形状/单位、带来源的要求及待确认问题；字段含义不确定时保留null和阻塞问题。1.0.0继续原样校验，不重写历史契约。

新增合法样例`valid-2024-a-q1-input-1.1.json`含待用户审阅问题，不代表已获确认；`invalid-input-structure-1.1.json`将行数写成字符串，结构校验会拒绝。字段结构与字节哈希均不能证明建模语义正确。

实际CLI、兼容规则、版本档案和恢复说明见[功能说明](../docs/input-contract-and-version-cli.md)。

## B+ 数学交接（2026-11-06）

新增method-selection、mathematical-dossier、mathematical-package三个1.0.0 Schema，独立于原Model Contract 1.0.0/1.1.0，旧Schema未改。正式字段、绑定规则与局限见[数学交接说明](../docs/mathematical-handoff.md)，合法/非法JSON见[样例入口](../stage-b-plus/README.md)。数学正确性仍需审阅，Schema不判断任意LaTeX真假。


## D1 三手协作契约

`collaboration-{binding,call,artifact,snapshot,handoff,ticket,receipt}-1.0.0.schema.json` 为独立新增 Schema，不修改模型契约或旧事件。运行时由 `modelcrew.collaboration` 严格校验；文件哈希、职责权限、作者隔离、跨版本绑定及必查项完整性需要程序进一步检查，JSON Schema 合法本身不能放行。用法与后续节点接入要求见[交接说明](../docs/d1-collaboration-contracts.md)。


## D2 建模手输出

新增 `modeling-plan-1.0.0.schema.json`、`modeling-proposal-1.0.0.schema.json`、`modeling-m1-answer-1.0.0.schema.json`。模型只能提出 JSON 修改；完整 Model Contract 与 MathematicalPackage 校验仍沿用原 Schema，M1 逐项证据与派发身份继续走 D1。顶层 M1 总状态由程序汇总，不代替独立语义检查。见[D2 说明](../docs/d2-modeling-hand.md)。
