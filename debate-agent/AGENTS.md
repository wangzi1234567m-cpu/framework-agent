# Debate Agent 协作边界

本项目处于 P0 设计与仓库准备阶段。详见 [PRD](docs/PRD.md)、[SAD](docs/SAD.md)、[双人协作规范](docs/TEAM_DEVELOPMENT.md)；三份文档尚待双人评审冻结。

- 开发者 A（项目发起人）负责正式领域模型、Pydantic Schema、API、持久化、工作流、审核、版本控制、前端与最终集成。
- 开发者 B 负责 Agent、Prompt/Skill、样本标注、写作规则草案及效果评测；不得绕过 A 的 Schema 契约直接写数据库或批准证据。
- `backend/knowledge/examples/` 是自动解析的原稿候选，不是人工审核通过的 `samples/`；`rules/framework_rules.md` 也仍待确认。
- 任何模型输出先通过正式 Schema；重要修改用 ChangeProposal 展示差异；CaseRevision 不可变；证据须 AI 核验与人工确认。
- 公共契约修改应更新 `docs/DOMAIN_MODEL.md`、`docs/AGENT_CONTRACTS.md` 等相关文件和测试，并由双方评审。
- 不要将根目录框架稿、研究原件或未经授权的内部材料上传到公共知识库。
