# 题解分析 Skill（topic-analysis）

- `skill_id`: topic-analysis
- `skill_version`: 0.1.0
- `agent_type`: TOPIC（对应 `TopicRequest -> TopicResponse`）
- 状态：`DRAFT`，未经双人评审，不得发布运行。

## 1. 适用 / 不适用场景

适用：给定辩题、持方、赛制与用户要求，产出**待人工确认的题解**（定义、讨论范围、双方立场、判准、论证方向、预期攻击）。

不适用：证据检索与溯源、框架论点生成（交给 framework-building）、立论稿、以及任何需要联网或外部事实核验的任务。MVP 不执行外部检索。

## 2. 所需输入

可读字段：`motion`、`side`、`format`、`duration_seconds`、`competition_context`、`user_requirements`。只能使用请求内的信息与已授权方法材料，未给出的信息不得编造；拿不准的事实写入 `uncertainty_notes`。

## 3. 流程总览（四阶段）

1. **analyze 分析输入**：判断辩题类型（政策 / 价值 / 事实 / 脑洞），列出需界定的关键概念、双方可能立场、候选判准、不确定点。
2. **draft 起草**：按「输出字段映射」产出完整 `TopicResponse` JSON。
3. **review 逐项自审**：按自审清单逐项检查，输出缺陷清单（`BLOCKING` / `IMPROVEMENT`）。
4. **revise 定向修订**：只修正缺陷清单涉及的部分，重新输出完整 `TopicResponse`；最多修订一次。

## 4. 输出字段映射（`TopicResponse`）

`analysis`（对象）：
- `definitions`：关键概念 -> 一句话定义（对己方有利、经得起推敲），可为空对象
- `discussion_scope`：讨论范围（**必填**）
- `assumptions`：隐含前提列表
- `core_conflicts`：正反双方真正的价值 / 事实冲突
- `affirmative_position`：正方主张（**必填**）
- `negative_position`：反方主张（**必填**）
- `clash_points`：核心交锋点
- `judging_criteria`：判准（说明以什么为准判定胜负）
- `strategy_options`：我方论证方向
- `opponent_attacks`：预期对方攻击路径

`uncertainty_notes`：无法确定的事实、范围或前提。

## 5. 方法论要点（已对齐 `.claude/agents/debate-题解`）

- **定义先行**：先界定争议词、范围和评价方向；遇近义词或极端化解释写「不等于什么」。每个定义尽量给出「是什么 / 不是什么 / 论证范围」，把讨论锁定在对我方有利、经得起推敲的范围。
- **定义战技巧**（按需选用）：类比澄清（「孤独是状态，不是处境」）；非 A 澄清（先说「不是什么」再定义）；拉平（把对方极端推到对等极端）；领域式定义 / 缩小证明负担（边界本不唯一，只证几个重要领域）；反循环论证（点破对方把利好塞进定义）。
- **判准可比**：判准必须能说明胜负如何比较；抽象价值可用类比解释，但类比不代替证明。技巧：适度 vs 过度（中性事物看现状是适度还是过度）；概念拆分（X ≠ Y）；划出「X 与 Y 的核心差别」；配正例 + 反例让判准可操作。
- **态度区分（价值态度分野）**：当辩题隐含双方对同一对象的不同价值态度时，明确写清分野（如「尊重而甘愿地继承」vs「轻蔑而被动地绕过」），并入 `judging_criteria` 或 `opponent_attacks`，供框架阶段直接取用。
- **辩题类型**：政策辩需在 `strategy_options` 给出可落地方向；价值辩重判准与价值比较；事实辩重定义边界与可证范围；脑洞题先在 `discussion_scope` 声明采用的设定边界，不把设定推演写成现有事实。
- **攻击预判**：`opponent_attacks` 写对方最可能从哪打，`clash_points` 写主攻与需防守的战场。
- **骨干句收口**：每个定义 / 判准尽量用一句「能上场的骨干句」收口，便于框架阶段直接引用；面向用户呈现时可展开、整合进框架时精简。

### 5.1 背景与人群（当前 DTO 缺口，需与系统负责人确认字段）
完整题解方法论还包含「背景刻画」（数据化现状 + 问题导向小结 + 可感意象 + 学理/机理 + 出处）与「目标人群」（核心人群 + 普惠/公平比较 + 立论动机链）。当前 `TopicResponse` 无 `background` / `target_audience` 字段，建议新增或先并入 `discussion_scope` / `strategy_options`，由系统负责人定 Schema，写作方不擅改。

## 6. 停止条件

- 阻断性缺陷（BLOCKING）无法在一次性修订内修复 -> 任务失败（`SELF_REVIEW_BLOCKED`）。
- 输出必须通过 `TopicResponse` 的 Pydantic 校验，否则为 `CANDIDATE_SCHEMA_INVALID`。

## 7. 禁止行为

- 不返回 `status`、`approved_by`、数据库 ID 等业务或审批字段。
- 不编造数据、出处、机构、法条；拿不准的事实写入 `uncertainty_notes`。
- 不做外部检索，不假设能读到用户工作区正文。
- 不自审即批准：self-review 是缺陷检查，不是人工审批。

## 8. 已知局限

- 定义背书与背景刻画依赖外部检索，MVP 关闭检索，相关内容只能给出方向并标「待核验」，不构成正式结论。
- 本 Skill 只产出待审题解，是否批准由人工决定。
