# Agent 输入输出契约（待双人评审）

**Owner：开发者 A 维护、开发者 B 提议；状态：待定义，非正式契约。**

每个 Agent 采用 `await agent.run(request)`；明确 Pydantic Request/Response、错误类型、超时、版本信息、Mock 行为和人工审核边界。Agent 不直接读写数据库，不批准证据或正式版本。字段变更按 [协作规范](TEAM_DEVELOPMENT.md) 第 3 节经双方评审；先与 [领域模型](DOMAIN_MODEL.md) 对齐。
