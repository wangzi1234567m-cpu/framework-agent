# Debate Agent 软件架构设计 SAD V1.0

**版本：** V1.0  
**状态：** 待双人评审  
**架构风格：** 模块化单体 + 受控工作流  
**前端：** Next.js + TypeScript  
**后端：** FastAPI + Python  
**数据库：** PostgreSQL

---

# 1. 架构设计决策

## ADR-001：模块化单体

采用一个 FastAPI 后端和一个 Next.js 前端。

不拆微服务。

## ADR-002：统一论证事实源

DebateCase 是唯一正式论证事实源。

框架稿是 DebateCase 的结构化展示和文档导出。

立论稿是引用某个确认版本的稿件产物。

不能维护两套彼此独立的论点数据。

## ADR-003：树结构 + 关联关系

Argument 下使用递归 ReasoningNode 表示论证过程。

EvidenceLink 单独表示证据与论点或具体推理节点的关联。

不把案例全文复制到论证步骤中。

## ADR-004：样本、规则、Skill、评测四层知识体系

不将 RAG 作为主要学习方式。

先建设可执行规则和 Skill，再按需要检索优秀样本。

## ADR-005：证据溯源优先

SearchProvider 只提供候选来源。

EvidenceService 负责溯源信息管理。

EvidenceVerifier 负责 AI 核验。

ApprovalService 负责人工确认。

## ADR-006：人工审核和版本不可变

Agent 只能产生候选内容和修改提案。

所有正式修改经过业务服务验证和必要的人工确认。

## ADR-007：先用普通 Python 工作流

第一版使用显式状态机和 Python Workflow Runner。

暂不强制使用 LangGraph。

当流程出现复杂并行、长时间暂停恢复、子图复用需求时再评估引入 LangGraph。

---

# 2. 整体系统架构

```text
                    Next.js Frontend
                           |
                       REST API
                           |
                       FastAPI
                           |
       +-------------------+-------------------+
       |                   |                   |
   CaseService        EvidenceService      DraftService
       |                   |                   |
       +-------------------+-------------------+
                           |
                    Workflow Runner
                           |
       +-------------------+-------------------+
       |                   |                   |
  TopicAnalyzer      FrameworkBuilder    EvidenceResearcher
       |                   |                   |
       +-------------------+-------------------+
                           |
               EvidenceVerifier / Reviewer
                           |
                     SpeechWriter
                           |
                    LLM / Search Adapters
                           |
                       PostgreSQL
                           |
             Samples / Rules / Skills / Evals
```

## 2.1 前端层

负责：
- 项目列表。
- 辩题创建。
- 题解审核。
- 框架树编辑器。
- 证据溯源面板。
- 自然语言修改面板。
- 版本对比。
- 框架稿和立论稿编辑器。

## 2.2 API 层

FastAPI 负责：
- 接收请求。
- 校验参数。
- 身份和项目权限检查。
- 调用 Application Service。
- 返回统一响应。
- 管理生成任务。

不在 Router 内编写 Prompt 或复杂业务逻辑。

## 2.3 Application Service

核心服务：

- DebateProjectService
- TopicAnalysisService
- CaseService
- EvidenceService
- ApprovalService
- ChangeProposalService
- DraftService
- EvaluationService

服务负责数据持久化、状态流转和事务。

## 2.4 Agent 层

Agent 不直接连接数据库。

Agent 通过 Pydantic 输入输出模型被 Workflow 调用。

模块包括：

- TopicAnalyzer
- FrameworkBuilder
- EvidenceResearcher
- EvidenceVerifier
- FrameworkReviewer
- SpeechWriter
- ChangeProposalAgent

## 2.5 Knowledge 层

由四部分构成：

```text
knowledge/
├── samples/
├── annotations/
├── rules/
├── skills/
└── evals/
```

知识资产必须有版本、来源和审核状态。

## 2.6 Infrastructure 层

- LLMProvider
- SearchProvider
- DocumentFetcher
- PDFParser
- DatabaseRepository
- Logging
- Configuration

---

# 3. 核心领域模型

## 3.1 DebateProject

一次备赛项目。

字段：
- id
- motion
- side
- format
- duration_seconds
- competition_context
- user_requirements
- created_at
- updated_at

## 3.2 TopicAnalysis

题解分析版本。

字段：
- id
- project_id
- version
- definitions
- discussion_scope
- assumptions
- core_conflicts
- judging_criteria
- strategy_options
- status

状态：
DRAFT / PENDING_APPROVAL / APPROVED / REJECTED

## 3.3 DebateCaseWorkingCopy

当前可编辑的框架工作版本。

字段：
- id
- project_id
- schema_version
- edit_version
- approved_topic_analysis_id
- thesis
- definitions
- judging_criteria
- weighing
- arguments
- overall_strategy
- updated_at

## 3.4 Argument

固定外层结构。

字段：
- id
- title
- order
- core_claim
- explanation
- reasoning_nodes
- impact
- evidence_links
- attack_defense
- extension_data
- status

## 3.5 ReasoningNode

递归论证节点。

字段：
- id
- label
- kind
- content
- order
- children

kind 使用开放字符串或可扩展类型注册机制。

不能把论证步骤硬编码为固定的 step1、step2、step3 逻辑。

## 3.6 SourceRecord

来源记录。

字段：
- id
- title
- publisher
- author
- source_type
- canonical_url
- doi
- document_url
- published_at
- retrieved_at
- content_hash
- source_grade
- metadata

## 3.7 EvidenceItem

证据内容。

字段：
- id
- evidence_type
- factual_claim
- summary
- source_ids
- research_metadata
- case_metadata
- exact_locator
- limitations
- trace_status
- verification_status
- source_grade
- relevance_score
- human_approval_status

## 3.8 EvidenceLink

证据与论证节点的关联。

字段：
- id
- evidence_id
- target_type
- target_id
- supported_claim
- relevance_explanation
- relation_type

target_type：
ARGUMENT / REASONING_NODE

relation_type：
SUPPORTS / CONTRADICTS / CONTEXTUALIZES

## 3.9 CaseRevision

正式确认的不可变版本。

字段：
- id
- project_id
- revision_number
- snapshot_json
- schema_version
- approved_by
- approved_at
- created_at

## 3.10 Approval

人工审核记录。

字段：
- id
- target_type
- target_id
- target_version
- decision
- comment
- reviewer_id
- created_at

## 3.11 ChangeProposal

AI 或用户指令生成的修改提案。

字段：
- id
- project_id
- target_type
- target_id
- base_revision
- operation
- patch_json
- before_snapshot
- after_snapshot
- status
- created_at
- reviewed_at

operation：
ADD / UPDATE / DELETE / REORDER / LINK / UNLINK

status：
PENDING / ACCEPTED / REJECTED / CANCELLED

## 3.12 SpeechDraft

立论稿。

字段：
- id
- project_id
- source_revision_id
- version
- status
- duration_target
- content

## 3.13 SpeechSection

立论稿段落。

字段：
- id
- draft_id
- text
- order
- dependency_refs
- based_on_revision_id
- edit_version
- stale

dependency_refs 应尽可能指向具体 Argument 或 ReasoningNode。

## 3.14 GenerationJob

生成任务记录。

字段：
- id
- project_id
- job_type
- status
- current_step
- input_snapshot
- output_snapshot
- error_code
- error_message
- attempts
- model
- prompt_version
- skill_version
- created_at
- completed_at

---

# 4. 核心 Schema

下面是第一版的结构示意，最终以双方评审后的 Pydantic 模型为准。

```python
from typing import Any
from pydantic import BaseModel, Field


class ReasoningNode(BaseModel):
    id: str
    label: str = ""
    kind: str = "other"
    content: str
    order: int = 0
    children: list["ReasoningNode"] = Field(
        default_factory=list
    )


class Argument(BaseModel):
    id: str
    title: str
    core_claim: str
    explanation: str
    reasoning_nodes: list[ReasoningNode]
    impact: str = ""
    evidence_links: list[str] = Field(
        default_factory=list
    )
    attack_defense: dict[str, Any] = Field(
        default_factory=dict
    )
    extension_data: dict[str, Any] = Field(
        default_factory=dict
    )


class DebateCase(BaseModel):
    motion: str
    side: str
    thesis: str
    definitions: dict[str, str] = Field(
        default_factory=dict
    )
    judging_criteria: list[str] = Field(
        default_factory=list
    )
    arguments: list[Argument] = Field(
        default_factory=list
    )
    overall_strategy: str = ""


class EvidenceCandidate(BaseModel):
    id: str
    evidence_type: str
    factual_claim: str
    source_ids: list[str]
    exact_locator: dict[str, Any] = Field(
        default_factory=dict
    )
    limitations: list[str] = Field(
        default_factory=list
    )
    trace_status: str
    proposed_source_grade: str
```

约束：
- ID 稳定。
- reasoning_nodes 允许任意合理深度。
- 不允许循环结构。
- 不允许引用不存在的节点。
- AI 输出必须通过 Pydantic 校验。
- extension_data 不能代替核心字段。
- 历史快照必须带 schema_version。

---

# 5. 写作方法论工程设计

## 5.1 WritingRule 数据结构

```text
WritingRule
├── rule_id
├── title
├── principle
├── applicability
├── required_behavior
├── anti_patterns
├── positive_examples
├── negative_examples
├── scoring_dimension
├── scoring_rubric
├── source_sample_ids
├── status
└── version
```

status：
DRAFT / REVIEWING / APPROVED / DEPRECATED

只有 APPROVED 的规则才能进入正式生产 Skill。

## 5.2 Skill 数据结构

每个 Skill 是一份有版本的任务说明和执行流程。

建议结构：

```text
skills/
├── topic-decomposition/
│   ├── SKILL.md
│   ├── rules.yaml
│   ├── examples.json
│   └── eval_cases.json
│
├── argument-design/
│   ├── SKILL.md
│   ├── rules.yaml
│   ├── examples.json
│   └── eval_cases.json
│
├── reasoning-construction/
├── argument-differentiation/
├── evidence-requirement-analysis/
├── framework-review/
└── speech-conversion/
```

SKILL.md 至少包含：

1. 适用场景。
2. 触发条件。
3. 输入要求。
4. 执行步骤。
5. 规则引用。
6. 禁止行为。
7. 输出 Schema。
8. 质量检查。
9. 示例。

## 5.3 量化评测

建立独立的 EvaluationCase 和 EvaluationRun。

评测维度以 1–5 分锚定评分。

每条评分必须有具体的行为描述，不能只给分数。

评测方式：
- 人工专家评分。
- 两份输出盲测比较。
- AI 辅助评分。
- 对照通用模型基线。
- 记录评测人员间的一致性。

不允许仅凭模型自己打分，就认定某条 Skill 有效。

## 5.4 样本检索

第一版采用元数据和标签检索优秀样本。

RAG 作为辅助：
- 找到相似辩题。
- 找到相似论证方式。
- 提供正面和反面示例。

第一版不强制建设向量数据库。

---

# 6. Evidence Provenance 架构

## 6.1 检索与溯源分离

```text
SearchProvider
     ↓
Candidate Source
     ↓
Source Locator
     ↓
Original Document Fetcher
     ↓
PDF / Web Parser
     ↓
SourceRecord
     ↓
Evidence Claim Extraction
     ↓
Provenance Verification
     ↓
Argument Relevance Verification
     ↓
Human Approval
     ↓
Approved Evidence
```

## 6.2 研究与数据证据

ResearchMetadata：

- research_type
- institution
- authors
- published_at
- population
- sample_size
- sampling_method
- collection_period
- geography
- methodology
- measurement_definition
- limitations
- report_url
- pdf_url
- doi
- page_number
- table_number

要求：
- 优先取得原始研究 PDF 或官方数据库。
- 精确定位原文页码、表格或章节。
- 不允许只凭搜索摘要生成结论。
- 原文缺失关键方法时标记 TRACE_INCOMPLETE。
- 无法确认的数据不进入正式证据集合。

## 6.3 案例证据

CaseMetadata：

- subject_name
- organization
- event_date
- event_location
- event_description
- official_record_urls
- media_report_urls
- corroboration_sources

要求：
- 主体真实。
- 事件真实。
- 时间和经过可核验。
- 至少具有可信媒体报道或官方记录。
- 优先多来源交叉印证。
- 匿名化研究参与者不得被包装为可独立核实的真人案例。

## 6.4 来源等级与论证匹配独立

source_grade：
A / B / C / D / X

relevance_score：
1–5

verification_status：
PENDING / AI_REVIEWED / HUMAN_APPROVED / REJECTED / DISPUTED

AI 只能提出建议等级和核验结论。

Human Approval 是正式入库的必要条件。

## 6.5 原始材料保存

保存：
- URL。
- DOI。
- 文档标题。
- 发布机构。
- 作者。
- 检索时间。
- 原文定位。
- 内容哈希。
- 允许保存的原始文本或文件引用。

未经授权的版权材料不直接打包进公共仓库。PDF 原件可以保存外部引用和必要的合法元数据。

---

# 7. 工作流设计

```text
CREATE_PROJECT
      ↓
ANALYZE_TOPIC
      ↓
WAIT_TOPIC_APPROVAL
      ↓
BUILD_FRAMEWORK
      ↓
ANALYZE_EVIDENCE_NEEDS
      ↓
RESEARCH_EVIDENCE
      ↓
VERIFY_PROVENANCE
      ↓
VERIFY_ARGUMENT_RELEVANCE
      ↓
WAIT_EVIDENCE_APPROVAL
      ↓
REVIEW_FRAMEWORK
      ↓
WAIT_FRAMEWORK_APPROVAL
      ↓
CREATE_CASE_REVISION
      ↓
RENDER_FRAMEWORK_DRAFT
      ↓
GENERATE_SPEECH
      ↓
WAIT_SPEECH_REVIEW
      ↓
COMPLETED
```

## 7.1 人工暂停

等待人工确认时，Workflow 进入持久化等待状态。

用户完成操作后，从对应节点继续。

## 7.2 局部返工

- 题解不通过：重新分析题解。
- 论点不通过：重新构建相关论点。
- 来源不通过：重新搜索来源。
- 证据匹配不通过：更换证据或修改论证。
- 框架不通过：只修改有问题的部分。

不能因为一个局部问题导致全部流程从头开始。

## 7.3 工作流实现

第一版使用 Python 函数和明确状态机。

GenerationJob 负责保存运行状态和结果。

数据库负责业务状态和人工审核记录。

不引入 Redis、分布式消息队列或复杂 LangGraph 部署。

---

# 8. 人工编辑与 ChangeProposal

自然语言修改流程：

```text
User Instruction
      ↓
Target Resolver
      ↓
Operation Planner
      ↓
ChangeProposal
      ↓
Schema Validation
      ↓
Diff Preview
      ↓
Human Accept / Reject
      ↓
CaseService Apply
      ↓
New WorkingCopy Version
```

操作类型：
- ADD_NODE
- UPDATE_NODE
- DELETE_NODE
- REORDER_NODE
- LINK_EVIDENCE
- UNLINK_EVIDENCE
- REWRITE_SECTION

必须携带：
- target_id
- base_revision
- operation
- patch
- before_snapshot
- after_snapshot

用户指令不明确时，系统先澄清。

AI 不能直接修改已经确认的 CaseRevision。

---

# 9. 版本和稿件一致性

1. WorkingCopy 可修改。
2. 每次重要保存递增 edit_version。
3. 用户确认后创建不可变 CaseRevision。
4. SpeechDraft 必须绑定 source_revision_id。
5. 每个 SpeechSection 保留 dependency_refs。
6. 修改框架后，仅标记相关稿段 stale。
7. 局部重写先生成候选，用户确认后替换。
8. 立论稿出现新论点时，生成 ChangeProposal，而不是自动修改 DebateCase。
9. 并发编辑使用乐观锁，冲突返回 HTTP 409。

---

# 10. API 设计

统一前缀：`/api/v1`

| Method | Endpoint | 功能 |
|---|---|---|
| POST | /projects | 创建辩题 |
| GET | /projects | 查询项目 |
| GET | /projects/{id} | 获取项目 |
| POST | /projects/{id}/topic-analysis-runs | 生成题解 |
| POST | /topic-analyses/{id}/approval | 审核题解 |
| POST | /projects/{id}/framework-runs | 生成框架 |
| GET | /cases/{id} | 获取论证工作区 |
| PATCH | /cases/{id}/working-copy | 修改工作版本 |
| POST | /cases/{id}/revisions | 确认并创建正式版本 |
| POST | /arguments/{id}/evidence-search-runs | 搜索证据 |
| POST | /evidence/{id}/verification-runs | AI 溯源核验 |
| POST | /evidence/{id}/approval | 人工审核证据 |
| POST | /change-proposals | 创建修改提案 |
| POST | /change-proposals/{id}/decision | 接受或拒绝提案 |
| POST | /case-revisions/{id}/speech-drafts | 生成立论稿 |
| GET | /jobs/{id} | 查询任务 |
| POST | /jobs/{id}/retry | 重试任务 |
| POST | /drafts/{id}/export | 导出稿件 |

所有异步任务返回 job_id。

错误响应必须有统一 error_code、message、request_id。

---

# 11. 技术选型

| 层 | 选型 |
|---|---|
| 前端 | Next.js / TypeScript |
| 后端 | FastAPI |
| 数据校验 | Pydantic v2 |
| ORM | SQLAlchemy 2 |
| 数据库 | PostgreSQL |
| 迁移 | Alembic |
| 模型调用 | 可替换 LLM Adapter，DeepSeek 优先 |
| 搜索 | SearchProvider Adapter |
| PDF 解析 | PyMuPDF 等文本解析工具 |
| 测试 | pytest / Ruff |
| 前端测试 | ESLint / TypeScript |
| CI | GitHub Actions |

第一版不强制使用：
- LangGraph。
- Redis。
- 向量数据库。
- Kubernetes。
- 微服务。

---

# 12. 项目目录

保留现有 backend 目录，避免为了目录命名进行无意义迁移。

```text
debate-agent/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── services/
│   └── types/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── domain/
│   │   ├── schemas/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── agents/
│   │   ├── workflow/
│   │   └── infrastructure/
│   │
│   ├── knowledge/
│   │   ├── samples/
│   │   ├── annotations/
│   │   ├── rules/
│   │   ├── skills/
│   │   ├── evals/
│   │   └── examples/
│   │
│   ├── scripts/
│   ├── tests/
│   └── alembic/
│
├── docs/
│   ├── PRD.md
│   ├── SAD.md
│   ├── DOMAIN_MODEL.md
│   ├── API_SPEC.md
│   ├── AGENT_SPEC.md
│   ├── AGENT_CONTRACTS.md
│   ├── EVIDENCE_SPEC.md
│   ├── KNOWLEDGE_SPEC.md
│   ├── EVAL_SPEC.md
│   └── TEAM_DEVELOPMENT.md
│
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   └── pull_request_template.md
│
├── .env.example
├── .gitignore
├── README.md
└── AGENTS.md
```

现有的框架稿提取脚本、样本索引和历史分析文件应保留并逐步迁移到上述知识目录，不得直接删除。

---

# 13. 测试体系

## 单元测试

- Schema 合法性。
- 论证树递归。
- 来源等级校验。
- 证据关联。
- 状态转换。
- ChangeProposal 应用。

## 集成测试

- TopicAnalysis → Human Approval。
- FrameworkBuilder → DebateCase。
- EvidenceResearcher → SourceRecord。
- EvidenceVerifier → Approval。
- CaseRevision → SpeechDraft。

## 端到端测试

完整跑通：
创建辩题 → 题解确认 → 框架生成 → 证据核验 → 人工确认 → 框架稿 → 立论稿。

## 质量评测

- 通用模型基线。
- Prompt 基线。
- Skill + Workflow 方案。
- 人工评分。
- 盲测对照。
- 规则命中和缺陷分析。

---

# 14. 安全与可靠性

1. API Key 只能保存在服务端环境变量。
2. 用户上传文件和网页内容均为不可信输入。
3. 网页中的指令不能覆盖 Agent 系统指令。
4. 来源内容与模型推断必须分开保存。
5. 不记录敏感凭证。
6. 未经授权的内部稿件不得公开。
7. AI 不允许直接批准证据和正式框架。
8. 模型失败不影响已保存的人工数据。
9. 异步任务必须可追踪和有限重试。

---

# 15. 架构验收标准

- [ ] 空数据库可以成功迁移。
- [ ] 可以创建并恢复辩题。
- [ ] 题解审核前不能生成正式框架。
- [ ] 论证机理支持任意合理层级。
- [ ] Agent 输出通过 Pydantic 校验。
- [ ] Skills 和 Rules 有版本。
- [ ] 证据有完整来源字段。
- [ ] AI 核验后必须等待人工确认。
- [ ] 自然语言修改产生 ChangeProposal。
- [ ] 修改可以预览、接受和拒绝。
- [ ] CaseRevision 不可变。
- [ ] 立论稿绑定明确的框架版本。
- [ ] 修改框架可以准确标记受影响稿段。
- [ ] 主要流程具有自动化测试。

**架构冻结条件：用两份风格不同的真实框架稿完成数据模型回填，验证论点、嵌套机理和证据关联均能被正确表达，再冻结 Schema。**