# W2 证据引用协议

当前协议为 2.2.0，入口是 `modelcrew.w2_protocol`。它解决审查模型编造证据编号、JSON Pointer 和页码补零格式的问题，不改变模型的科学或版式判断，也不替用户批准论文。

程序先从封存的论文、原 W1 论断证据、图目录、渲染检查及实际页面生成引用登记表。证据使用 `E0001` 等编号，页面使用 `P0001` 等编号，每项绑定实际来源、确定的选择器和内容哈希。模型只接收这些编号及对应真实内容；原始资料里的图号、文件名和业务编号均不是合法引用编号。模型返回 `evidence_refs` 和 `page_ref`，不能返回自由填写的 artifact_id、selector 或文件路径。

接收端精确验证登记表、每个引用、五类检查及全部页面的唯一覆盖，然后按登记表生成原生 Evidence。未知编号、缺页、重复页、矛盾状态、超过数量或长度限制、没有问题说明的非通过检查均拒收。没有模糊匹配、补齐缺页、猜测 Pointer、删除多余引用或截短解释。原始响应、编译后的原生结构和二者的内容哈希分别保存。模型的状态、说明、问题原因和复核要求原文保留。

问题只返回 `issue_kind` 一个类别；程序按公开映射生成原生 domain/target：model→model/modeling，implementation→implementation/coding，writing→writing/writing，infrastructure→infrastructure/recovery；explanation_coding 和 explanation_writing 分别路由到代码手和论文手。这是预先声明的协议映射，模型不能同时给出互相矛盾的领域和目标。

每项最多三条引用；原生文本硬上限从 `collaboration.Check` 的正式 Schema 读取，目前为300字，提示建议简短表述。逐页报告槽位和要求的总页数在请求中完整列出。旧2.1版的200字限制与原生300字约束不一致，旧失败返回保留为失败，不用新版协议重新解释。

`JsonModel` 对此协议实际发送 response_format。当前供应商实测拒绝 json_schema，故兼容默认是 json_object；`MODELCREW_W2_RESPONSE_FORMAT=json_schema` 可在服务确实支持时显式选择。程序不会在一次调用失败后静默切换模式重发；无论服务选择哪种模式，本地登记表、Schema 和回执门禁始终严格校验。日志区分请求的输出模式与是否能证明服务器执行了 Schema。

新 W2 操作使用2.2版，冻结的旧 v1 操作按原封存数据保留原恢复路径。正式 W2 的一次独立复核额度、未知传输不重发、派发前提交claim等约束不变。协议资格验证使用 `python -m scripts.qualify_w2_protocol` 的独立新目录，每目录只允许一次供应商调用，不写正式 W2 数据库状态，不创建正式回执，不重置复核次数；有效的 FAIL/BLOCKED 同样可以证明协议合格。

本次真实资格验证使用同一真实稿、原始论断证据及54张实际页面。最终2.2版完整接收五类检查、54页报告和所有引用，供应商原始结论为FAIL，完整保留。报告见 `stage-e/implementation/20261110-w2-protocol-v2/证据协议修复记录.md`。旧正式W2仍为原两次拒收，用户已验收版本的内容与文件哈希未变。
