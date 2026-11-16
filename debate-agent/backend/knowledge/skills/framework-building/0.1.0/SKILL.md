# 框架生成 Skill（framework-building）

- `skill_id`: framework-building
- `skill_version`: 0.1.0
- `agent_type`: FRAMEWORK（对应 `FrameworkRequest -> FrameworkResponse`）
- 状态：`DRAFT`，未经双人评审，不得发布运行。

## 1. 适用 / 不适用场景

适用：已有人工确认的题解（`approved_topic`），据此生成可编辑、可追溯的框架论点（含递归机理、证据需求、攻防）。

不适用：题解分析、证据检索与溯源、立论稿、审批。框架必须遵循已确认题解的定义 / 判准，无证据时输出 `evidence_needs`，不能伪造数据 / 链接。

## 2. 所需输入

可读字段：`motion`、`side`、`format`、`duration_seconds`、`competition_context`、`user_requirements`、`approved_topic`（已确认题解内容）、`topic_version`、`base_edit_version`。MVP 无外部检索。

## 3. 流程总览（四阶段）

1. **analyze 分析输入**：读已确认题解，确定立论主旨与论点分工。
2. **draft 起草**：产出完整 `FrameworkResponse` JSON。
3. **review 逐项自审**：检查论点独立性、机理完整性、ref 唯一性、是否伪造证据、是否混入业务字段。
4. **revise 定向修订**：只修正缺陷清单涉及的部分，重新输出完整 `FrameworkResponse`；最多修订一次。

## 4. 输出字段映射（`FrameworkResponse`）

- `thesis`：立论主旨（**必填**）
- `arguments[]`：论点数组（至少 1 个）
  - `ref` / `order` / `title` / `core_claim` / `explanation` / `impact`：必填
  - `reasoning_nodes[]`：递归机理树（每论点至少 1 个节点；节点含 `ref`/`label`/`kind`/`content`/`order`/`children`）
  - `evidence_needs[]`：证据需求（`ref`、`target_node_ref` 指向同论点节点、`question`、`acceptable_source`）
  - `attack_defense[]`：攻防（`opposing_claim`、`response`、`weighing`）
- `weighing`：价值衡量
- `overall_strategy`：整体策略
- `uncertainty_notes`：不确定点

## 5. 方法论要点

- **论点分工**：论点按不同原因或不同受益维度分工，标题尽量含「问题 + 路径 + 收益/损害」；不得重复表达凑数。
- **机理链**：每论写清「现状/问题 -> 起作用的中间环节 -> 后果/判准」，末端回扣题解判准；分清「解释机制」与「证明机制」，不把「有数据」当因果已成立。
- **递归机理**：用开放 `kind` 字符串（如 problem/mechanism/evidence/impact）组织节点，不硬编码 step1/step2/step3；允许任意深度，禁止循环与悬空引用。
- **证据边界**：无来源的事实只列 `evidence_needs`（待查问题 + 可接受来源），不伪造数据、案例、链接、出处。
- **攻防**：先列对方最强异议，再写本方回应与价值比较，回扣判准。

## 6. 硬约束

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
