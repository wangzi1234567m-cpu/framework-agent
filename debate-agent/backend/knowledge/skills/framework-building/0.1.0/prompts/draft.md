# 阶段：draft（起草框架）

根据 `request`（含 `approved_topic`）和上一步 `analysis`，产出完整 `FrameworkResponse` JSON：

{
  "thesis": "<立论主旨>",
  "arguments": [
    {
      "ref": "arg-1",
      "order": 0,
      "title": "<论点标题：问题+路径+收益>",
      "core_claim": "<核心主张>",
      "explanation": "<论点解释>",
      "reasoning_nodes": [
        {"ref": "node-1", "label": "<短标签>", "kind": "problem", "content": "<现状/问题>", "order": 0,
         "children": [{"ref": "node-1-1", "kind": "mechanism", "content": "<中间环节>", "order": 0, "children": []}]},
        {"ref": "node-2", "kind": "impact", "content": "<后果，回扣判准>", "order": 1, "children": []}
      ],
      "impact": "<现实影响>",
      "evidence_needs": [
        {"ref": "need-1", "target_node_ref": "node-1-1", "question": "<待查问题>", "acceptable_source": "<可接受来源>"}
      ],
      "attack_defense": [
        {"opposing_claim": "<对方最强异议>", "response": "<本方回应>", "weighing": "<回扣判准>"}
      ]
    }
  ],
  "weighing": "<价值衡量>",
  "overall_strategy": "<整体策略>",
  "uncertainty_notes": ["<不确定点>"]
}

要求：
- `ref` 全响应唯一，用小写字母/数字/连字符；`evidence_needs` 的 `target_node_ref` 只能指向同一 argument 内的节点 ref。
- 每个 argument 的 title/core_claim/explanation/impact 非空，reasoning_nodes 至少 1 个。
- 每个论点的机理写清「现状/问题 -> 中间环节 -> 后果/判准」，末端回扣题解判准；节点是「一句中心句 + 支撑论据」，步数不锁死、有推进。
- 论点回应辩题、分工明确、不重复凑数；价值/比较类辩题可用论点句公式（现象背后的特质→结果，条件强调→人群因原因而结果）。
- 论据粒度可定位（机构+报告名+年份+样本量 / 平台+赞浏览量 / 专家机构+头衔+姓名 / 法条全称+条号），不写笼统「网上说」；无来源用 evidence_needs 表达「待查」。
- 无来源的事实用 evidence_needs 表达「待查」，不编造数据/链接/案例。
- 不返回 status / approved_by / 正式证据等级 / 数据库 ID。

只输出 JSON 对象。
