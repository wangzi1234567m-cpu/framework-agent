# Debate Agent 协作边界

本项目当前聚焦题解到框架稿的 MVP。现行文档只有 [产品需求](docs/PRODUCT_REQUIREMENTS.md)、[架构与模块契约](docs/ARCHITECTURE.md)、[MVP 验收](docs/MVP.md) 和 [开发阶段](docs/DEVELOPMENT_PLAN.md)；待双方用已授权的真实样本评审。`docs/PRD.docx` 为历史导出，非现行规范。

- 系统负责人 A 负责领域模型、Pydantic Schema、API、持久化、Agent 代码与工作流、Skill 接入、审核、版本控制、前端和最终集成。
- 写作方法负责人 B 负责获授权样本标注、规则及 Prompt/Skill 草案、量表草案和盲评；不必编写 Agent 代码，不得改公共 Schema 或发布未经审核的规则。
- `backend/knowledge/examples/` 是自动解析的原稿候选，不是人工审核通过的 `samples/`；`rules/framework_rules.md` 也仍待确认。
- 任何模型输出先通过正式 Schema；MVP 只生成候选和待查证据需求，题解及框架有人工关口；CaseRevision 不可变，证据核验与自然语言修改属于后续阶段。
- 公共契约修改应同步更新 `docs/ARCHITECTURE.md`、必要时更新 `docs/MVP.md`、Schema 及测试，并由双方评审。
- 不要将根目录框架稿、研究原件或未经授权的内部材料上传到公共知识库。
