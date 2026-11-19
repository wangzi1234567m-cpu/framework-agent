# 阶段：review（逐项自审）

对照 `request`（含 approved_topic）和 `candidate`，返回缺陷清单：

{"findings":[{"target":"<字段路径，如 arguments[0].reasoning_nodes>","rule_id":"<规则ID或空串>","severity":"BLOCKING|IMPROVEMENT","issue":"<问题>","suggested_fix":"<建议>"}]}

检查项：
1. `ref` 全响应唯一、同级 `order` 唯一、`evidence_needs` 只指向同论点节点。
2. 论点是否回应辩题、分工是否重复（独立性）。
3. 每个论点机理是否完整（现状→环节→后果），是否把「有数据」当因果。
4. 是否编造了数据/案例/链接/出处；证据不足是否用 evidence_needs 表达。
5. 是否混入 status / approved_by / 正式证据等级 / 数据库 ID。
6. 末端是否回扣题解判准、攻防是否回应争议。
7. 论点句是否一句话、判断句、可辩驳；机理节点是否「中心句 + 论据」、有推进非并列。
8. 论据粒度是否可定位（机构+报告名+年份 / 平台+赞浏览量 / 法条全称+条号），有无笼统「网上说」。
9. 攻防是否按战场组织、含接质口径；weighing 是否完成价值比较。金句、文学语句、专业术语和层数只属于审美参考，缺少它们不构成论证缺陷或 BLOCKING。
10. 案例/数据/假想场景是否有明确支持对象和诠释回扣；假想场景必须标明“设想”，不把它当实证。自审按 SKILL 中 T-/F-/A- 规则填写 rule_id；一般契约缺陷可用 GENERAL。

severity 取 BLOCKING 或 IMPROVEMENT；无缺陷返回 `{"findings":[]}`。这是模型自审，不能批准框架。只输出 JSON。
