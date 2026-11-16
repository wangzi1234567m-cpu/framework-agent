# 阶段：draft（起草题解）

根据 `request` 和上一步 `analysis`，产出完整 `TopicResponse` JSON，严格符合以下结构：

{
  "analysis": {
    "definitions": {"<关键概念>": "<一句话定义>"},
    "discussion_scope": "<讨论范围>",
    "assumptions": ["<隐含前提>"],
    "core_conflicts": ["<核心矛盾>"],
    "affirmative_position": "<正方主张>",
    "negative_position": "<反方主张>",
    "clash_points": ["<核心交锋点>"],
    "judging_criteria": ["<判准，能说明胜负如何比较>"],
    "strategy_options": ["<我方论证方向>"],
    "opponent_attacks": ["<预期对方攻击>"]
  },
  "uncertainty_notes": ["<无法确定的事实或前提>"]
}

要求：
- `discussion_scope`、`affirmative_position`、`negative_position` 必填且非空。
- 每个定义对己方有利、经得起推敲；能写「不是什么」以排除对方抢定义。
- 判准要能说明「以什么为准判断谁赢」；抽象价值可用类比解释，但类比不代替证明。
- 政策辩在 `strategy_options` 给出可落地方向；脑洞题先在 `discussion_scope` 声明采用的设定边界。
- 不返回 `status`、`approved_by`、任何数据库 ID 或业务审批字段。
- 拿不准的事实写进 `uncertainty_notes`，不编造。

只输出 JSON 对象。
