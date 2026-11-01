# Debate Agent 双人开发协作规范 V1.0

**协作模式：** Tech Lead + Agent Engineer  
**仓库：** debate-agent  
**默认分支：** main  
**仓库可见性：** Private

> 本文为目标协作规范；GitHub 仓库、分支保护、CI 与 PR 流程须在仓库创建后配置。当前本地目录尚不是 Git 仓库。

---

# 1. 角色定义

## 开发者 A：Tech Lead / 系统负责人

负责系统设计、工程骨架、数据契约、工作流和最终集成。本项目中由发起人负责契约及 Schema 定义。

具体职责：

### 产品与架构
- PRD、SAD。
- 领域模型。
- API 设计。
- 工作流状态机。
- 模块边界。
- 技术决策记录。

### 后端
- FastAPI。
- Pydantic Schema。
- SQLAlchemy。
- PostgreSQL。
- Alembic。
- Application Services。
- Workflow Runner。
- GenerationJob。
- ApprovalService。
- ChangeProposalService。

### 前端
- Next.js 项目骨架。
- 项目管理。
- 题解审核。
- 框架树编辑器。
- 证据审核工作台。
- 自然语言修改面板。
- 版本管理。
- 稿件编辑和导出。

### 工程管理
- GitHub 仓库。
- CI。
- PR 审查。
- 集成测试。
- 部署。
- 版本发布。

## 开发者 B：Agent Engineer / 智能能力负责人

负责将辩论写作经验转化为 Agent 能力。

### 方法论建设
- 优秀框架稿分析。
- 样本结构化标注。
- Writing Rules。
- Skills。
- 评分量表。
- 评测样本集。

### Agent 开发
- TopicAnalyzer。
- FrameworkBuilder。
- EvidenceResearcher。
- EvidenceVerifier。
- FrameworkReviewer。
- SpeechWriter。
- ChangeProposalAgent。

### 效果评测
- Prompt 测试。
- Skill 测试。
- 输出质量分析。
- 证据溯源测试。
- 错误案例分析。
- 与通用模型基线对照。

---

# 2. 文件与目录责任

## A 主要负责

```text
backend/app/api/
backend/app/domain/
backend/app/schemas/
backend/app/models/
backend/app/repositories/
backend/app/services/
backend/app/workflow/
frontend/
backend/tests/integration/
.github/
docs/
```

## B 主要负责

```text
backend/app/agents/
backend/app/infrastructure/llm/
backend/app/infrastructure/search/
backend/knowledge/samples/
backend/knowledge/annotations/
backend/knowledge/rules/
backend/knowledge/skills/
backend/knowledge/evals/
backend/tests/agents/
```

## 共同负责

以下文件必须双方评审：

- DOMAIN_MODEL.md
- API_SPEC.md
- AGENT_CONTRACTS.md
- EVIDENCE_SPEC.md
- EVAL_SPEC.md

A 维护正式版本，B 可以通过 PR 提出修改。

---

# 3. 开发边界

## A 不应该做的事情

- 不在业务 API 中直接编写复杂 Prompt。
- 不在 Workflow 中硬编码 Agent 的内部生成逻辑。
- 不绕过 Schema 直接读取模型原始文本。
- 不擅自改变 B 的 Skill 规则。
- 不把未经审核的 AI 输出写入正式知识库。

## B 不应该做的事情

- 不直接连接数据库。
- 不直接修改 CaseRevision。
- 不直接批准证据。
- 不擅自修改公共 Pydantic Schema。
- 不将 Prompt 输出的文字当成正式业务状态。
- 不把搜索摘要当作已经核验的来源。

## 契约变更规则

任何 Agent 输入输出字段变化：

1. 提交变更申请。
2. 说明变更原因。
3. 更新 Pydantic Schema。
4. 更新 API 或调用方。
5. 更新测试样例。
6. 双方审核。
7. 合并后才能作为正式契约。

---

# 4. Agent 模块交付标准

一个 Agent 不能只交付 Prompt。

每个模块必须交付：

1. Python 实现。
2. Pydantic Request。
3. Pydantic Response。
4. Prompt 或 Skill 文件。
5. 模型调用适配。
6. 超时和异常处理。
7. Mock 模式。
8. 单元测试。
9. 至少两个真实样本测试。
10. 输入输出示例。
11. 已知局限。
12. 版本记录。

统一调用形式：

```python
result = await agent.run(request)
```

Agent 不直接访问数据库。

Agent 不拥有最终业务状态的写入权限。

---

# 5. GitHub 协作规则

## 5.1 仓库规则

- 私有仓库。
- 默认分支 main。
- 两位开发者均作为 Collaborator。
- 日常开发禁止直接提交 main。
- 每个任务建立 Issue。
- 每个 Issue 对应一个 feature branch。
- 每个 feature branch 对应一个 PR。
- 通过测试并经另一位成员审查后合并。

## 5.2 分支命名

```text
main

feat/domain-model
feat/topic-agent
feat/framework-builder
feat/evidence-provenance
feat/evidence-verifier
feat/workbench
feat/speech-writer

fix/schema-validation
fix/evidence-status

docs/prd-v1
docs/architecture-v1
```

## 5.3 Commit 规范

```text
feat: 新增功能
fix: 修复问题
docs: 修改文档
test: 增加测试
refactor: 重构
chore: 工程配置
```

示例：

```bash
git commit -m "feat(domain): add argument schema"
git commit -m "feat(agent): implement framework builder"
git commit -m "test(evidence): add provenance validation cases"
```

## 5.4 PR 必须说明

- 对应 Issue。
- 修改内容。
- 修改原因。
- 输入输出示例。
- 是否修改 Schema。
- 是否修改数据库。
- 测试命令。
- 测试结果。
- 已知问题。

---

# 6. Definition of Done

所有功能只有满足以下条件才能标记完成：

1. 代码能够运行。
2. 输入输出满足契约。
3. 关键路径有测试。
4. 错误情况有处理。
5. 日志能够定位问题。
6. 没有将未核验内容冒充可靠证据。
7. 文档同步更新。
8. PR 通过审核。
9. CI 通过。
10. 实际功能经过人工验收。

Agent 输出流畅不等于 Agent 完成。

---

# 7. 开发阶段和任务安排

## P0：设计与仓库准备

A：
- 整理文档。
- 建立 GitHub 仓库。
- 初始化工程骨架。
- 设计基础 Pydantic Schema。
- 建立 CI。

B：
- 选择两份不同风格的优秀框架稿。
- 完成结构化拆解。
- 审核现有写作规则。
- 设计第一批 Skills。
- 设计量化评分表。

共同：
- 确认 Argument 和 ReasoningNode。
- 确认证据溯源字段。
- 确认 Agent Contracts。
- 确认第一批评测用例。

交付：
PRD.md
SAD.md
DOMAIN_MODEL.md
AGENT_CONTRACTS.md
KNOWLEDGE_SPEC.md
EVIDENCE_SPEC.md
EVAL_SPEC.md

## P1：题解和框架最小闭环

A：
- Topic API。
- Topic Approval。
- CaseService。
- Framework API。
- 前端框架编辑页面。

B：
- TopicAnalyzer。
- Argument Design Skill。
- Reasoning Construction Skill。
- FrameworkBuilder。
- Framework Reviewer。

联合验收：
输入辩题 → 人工确认题解 → 生成完整论点 → 编辑保存。

## P2：证据溯源

A：
- SourceRecord。
- EvidenceItem。
- EvidenceLink。
- Evidence Approval。
- 来源审核界面。

B：
- SearchProvider 接入。
- EvidenceResearcher。
- EvidenceVerifier。
- 研究报告提取。
- 案例真实性和来源审核逻辑。

联合验收：
对一个论点找到真实证据，定位原始来源，展示研究方法或事件信息，完成人工确认。

## P3：完整框架稿

A：
- 框架版本。
- 论点树编辑。
- ChangeProposal。
- 框架导出。

B：
- 多论点生成。
- 论点分工检查。
- 机理质量评测。
- 攻防生成。
- 证据匹配优化。

联合验收：
输入完整辩题，生成可编辑、可追溯的完整框架稿。

## P4：立论稿

A：
- SpeechDraft。
- SpeechSection。
- dependency_refs。
- 版本同步。
- 稿件编辑和导出。

B：
- SpeechWriter。
- Speech Conversion Skill。
- 口语表达优化。
- 框架忠实度评测。

联合验收：
根据确认框架生成立论稿，修改框架后能够正确识别受影响稿段。

## P5：系统质量

A：
- 全链路测试。
- 异常处理。
- 部署。
- 数据恢复。
- CI 完善。

B：
- 完整评测集。
- 通用模型对照。
- Skill 效果报告。
- 来源溯源错误分析。

联合验收：
完成真实辩题测试，形成系统质量报告。

---

# 8. 首批 GitHub Issues

建议按以下顺序建立：

| Issue | 标题 | Owner |
|---|---|---|
| #1 | docs: 冻结 V1.0 论证数据模型 | A + B |
| #2 | feat(knowledge): 两份优秀框架稿结构化标注 | B |
| #3 | feat(knowledge): WritingRule 与 Skill 规范 | B |
| #4 | chore: 初始化 monorepo 与 CI | A |
| #5 | feat(domain): DebateCase 和 Argument Schema | A |
| #6 | feat(topic): TopicAnalyzer 与人工审核 | B + A |
| #7 | feat(framework): FrameworkBuilder | B |
| #8 | feat(evidence): 来源溯源数据模型 | A |
| #9 | feat(evidence): EvidenceResearcher 和 Verifier | B |
| #10 | feat(workbench): 自然语言修改与 Diff 审核 | A |
| #11 | feat(draft): SpeechWriter 与稿件版本 | B + A |
| #12 | test: 建立 V1.0 评测基线 | A + B |

---

# 9. 每日协作

每天进行一次简短同步：

1. 昨天完成了什么？
2. 今天要合并什么？
3. 是否修改公共契约？
4. 是否阻塞对方？
5. 当前有什么测试失败？

不要以写了多少代码作为进度指标。

以完成了多少可验收的功能作为进度指标。

---

# 10. 最终协作原则

A 负责保证系统能够稳定运行、数据一致、模块可以组合。

B 负责保证 Agent 真正理解辩论写作任务、能够执行方法论规则、输出质量经过评测。

双方共同对最终结果负责。

任何一方都不能以“代码已经写完”或“模型已经能回答”为理由跳过功能验收。
