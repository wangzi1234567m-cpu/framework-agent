# 阶段：draft（起草题解）

根据 `request` 和上一步 `analysis`，产出完整 `TopicResponse` JSON，严格符合以下结构：

{
  "analysis": {
    "background": "<辩题背景，未核实内容标注待核验>",
    "target_audience": "<辩题涉及的人群，不明确时说明待确认>",
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
- `analysis.background` / `analysis.target_audience` 是合法字符串字段，不放到响应顶层。后者指辩题涉及人群，不是读者或评委；不编造背景事实或数据，无法判断时允许为空并写入 uncertainty_notes。
- 每个定义对己方有利、经得起推敲；能写「不是什么」以排除对方抢定义。
- 判准要能说明「以什么为准判断谁赢」；抽象价值可用类比解释，但类比不代替证明；可配「正例 + 反例」让判准可操作，并给一句「骨干句」收口。
- 定义战技巧按需选用（类比澄清 / 非 A 澄清 / 拉平 / 领域式定义 / 反循环论证）；若辩题隐含双方的价值态度分野，写入 `judging_criteria` 或 `opponent_attacks`。
- 政策辩在 `strategy_options` 给出可落地方向；脑洞题先在 `discussion_scope` 声明采用的设定边界。
- 不返回 `status`、`approved_by`、任何数据库 ID 或业务审批字段。
- 拿不准的事实写进 `uncertainty_notes`，不编造。

只输出 JSON 对象。
