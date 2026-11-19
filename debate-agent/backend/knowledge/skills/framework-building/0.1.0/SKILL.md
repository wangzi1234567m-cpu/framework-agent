# 框架生成 Skill（framework-building）

- `skill_id`: framework-building
- `skill_version`: 0.1.0
- `agent_type`: FRAMEWORK（对应 `FrameworkRequest -> FrameworkResponse`）
- 状态：`DRAFT`，未经双人评审，不得发布运行。

## 1. 适用 / 不适用场景

适用：已有人工确认的题解（`approved_topic`），据此生成备赛框架：原辩题标题、主旨、论一论二及内部展开、综合回应。攻防只放在全部论点之后。

不适用：题解分析、证据检索与溯源、立论稿、审批。框架必须遵循已确认题解的定义 / 判准，无证据时输出 `evidence_needs`，不能伪造数据 / 链接。

## 2. 所需输入

可读字段：`motion`、`side`、`format`、`duration_seconds`、`competition_context`、`user_requirements`、`approved_topic`（已确认题解内容）、`topic_version`、`base_edit_version`。MVP 无外部检索。

## 3. 流程总览（四阶段）

1. **analyze 分析输入**：读已确认背景、人群、定义和唯一判准，确定主旨、各论及每论内部不同维度，再预设对方最强问题。先做结构规划，不直接填套话。
2. **draft 起草**：产出完整 `FrameworkResponse` JSON。
3. **review 逐项自审**：检查论点独立性、机理完整性、ref 唯一性、是否伪造证据、是否混入业务字段。
4. **revise 定向修订**：只修正缺陷清单涉及的部分，重新输出完整 `FrameworkResponse`；最多修订一次。

## 4. 输出字段映射（`FrameworkResponse`）

- `thesis`：立论主旨（**必填**），是正文不是标题；标题由程序直接使用 request.motion，不要求模型生成。
- `arguments[]`：论点数组（至少 1 个）
  - `ref` / `order` / `title` / `core_claim` / `explanation` / `impact`：必填
  - `reasoning_nodes[]`：递归机理树（每论点至少 1 个节点；节点含 `ref`/`label`/`kind`/`content`/`order`/`children`）
  - `evidence_needs[]`：证据需求（`ref`、`target_node_ref` 指向同论点节点、`question`、`acceptable_source`）
  - `attack_defense[]`：旧字段，新稿不填，不能在每论内安排攻防。
- 顶层 `attack_defense[]`：全部论点写完后的综合攻防，opposing_claim 写最强问题，response 写自然回应；确有必要的比较直接融进回应，weighing 留空。
- `conclusion`：可选的一小段综合收束，不能重复整篇，也不能另起“比较与权衡/整体策略”。
- `weighing` / `overall_strategy`：兼容旧稿，新稿不填。
- `uncertainty_notes`：不确定点

## 5. 方法论要点

- **两层分工**：主论点之间按不同作用分工，每个主论点内部再按心态/行动过程、个人/共同生活、短期选择/长期习惯等适用维度切分。不能机械指定论一必须个人、论二必须群体；也不能两个小点换例子重复同一机制。
- **论点句不是公式填空**：一句清楚、可反驳的判断带出贡献。不要“论证价值根基：……是一种……”这类强行套模板。标题和核心句不重复长抄，解释只做简短引入，主要内容放在机理展开。
- **现状已在题解**：论点从“为什么/如何改变”进入，不设 problem/status_quo 节点重铺背景。必要前提可作为条件写入推理，不再开一段“当代现状”。
- **内部展开有自己的中心句**：用自然短句作 label，正文写具体的人怎么想、怎么选择、过程如何发生、成立条件是什么。kind 用 dimension/mechanism/condition/illustration/interpretation 等内部标签，不能把英文字段或“中间环节/后果”当成稿件语言。
- **材料与诠释连起来**：写清场景或材料中的哪一点支持当前机制，再解释它如何支持主张。不必每段喊“回扣判准”；判断有根有据即可。未核验的案例与数据留在证据需求，不伪造评论、专家头衔或点赞数增加真实感。
- **学习原稿的说法，不搬原稿的结论**：AI情书稿用表达端/接收端及心态/过程展开，爱量化稿用识别/反馈/经营展开；学习这种问题驱动的细分。可用“不是……而是……”“当一个人……他便……”带出关键差别，但不能句句模板化。
- **证据边界**：无来源的事实只列 `evidence_needs`（待查问题 + 可接受来源），不伪造数据、案例、链接、出处。`evidence_needs` 是待查问题，不是已核验证据。
- **综合之后再攻防**：顶层 attack_defense 写对方可能问的具体问题，response 正面回应，承认合理前提后解释双方仍分歧在哪里。对方承认传统有价值仍可以主张更需要创新，不能替他编“必须全盘抛弃传统”。必要条件题必须回应替代来源，不能用“有帮助”直接证明“离不开”。
- **收束而不是报告结论**：conclusion 可从前文推理自然落回判准，一小段就够，不逐论复述。文学和术语可以有，但“根与枝叶”之类意象不能承担不可替代性的证明。
- **去机械话术**：不要“本论从个体与直接受益维度切入”“本方在主判准上完成双重论证”“直接回扣主判准”“需由need-3核验”。用人的行为和处境说话，出处和待查ID留在结构数据及核验备注中。

## 6. 硬约束

结构规则来自 S-AI-LETTER、S-LANGUAGE、S-LOVE-QUANTIFICATION 的原稿结构候选分析（精确定位在 structure-v1 规则目录），不复制这些题目的事实到新题：
- `F-DIVISION`：按不同功能或受益维度分论，内部再拆解，避免换例子重复同一机理。
- `F-MECHANISM-CONDITION`：机理写清成立前提、中间环节、后果和判准回扣，层数随逻辑需要。
- `F-MATERIAL-INTERPRET`：案例/数据服务具体机理节点；诠释说明它证明什么、不能证明什么。用 kind=illustration/interpretation/condition 等开放节点展示场景、诠释与前提。假想场景必须明示“设想”，无来源事实放 evidence_needs，不虚构已发生事件或数字。
- `F-ATTACK-COMPARE`：论点后集中回应最强异议，比较自然融入回应，区分问题来源、工具作用及替代路径。
- `A-EXPRESSION`：文学/金句/术语属于独立审美，不以缺少修辞判为 BLOCKING，不替代论证。
自审 findings 使用对应 rule_id，一般契约错误可用 GENERAL。完整备赛框架不是240秒陈词，按 user_requirements 的篇幅展开，不能只给简短提纲。

- 全响应 `ref` 全局唯一；同级 `order` 唯一；`evidence_needs.target_node_ref` 只能指向同一 argument 内的节点 ref。
- 论点回应辩题、分工明确；每论至少一个机理节点。
- 不返回 `status` / `approved_by` / 正式证据等级 / 数据库 ID。

## 7. 停止条件

- BLOCKING 缺陷一次性修订无法修复 -> 任务失败（`SELF_REVIEW_BLOCKED`）。
- 输出须通过 `FrameworkResponse` 校验，否则为 `CANDIDATE_SCHEMA_INVALID`。

## 8. 禁止行为

- 不伪造数据、案例、链接、出处。
- 不把「有数据」当作因果已经成立。
- 不硬编码固定推理步骤；机理用开放 `kind`。
- 不自审即批准：self-review 是缺陷检查，不是人工审批。

## 9. 已知局限

- 证据环节只产出 `evidence_needs`，真正检索由后续 EvidenceResearcher 负责。
- 攻防为草案级，MVP 不保证覆盖全部反驳。
