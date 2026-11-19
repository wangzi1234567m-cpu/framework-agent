# 阶段：review（逐项自审）

对照 `request` 和已起草的 `candidate`，逐项检查并返回缺陷清单：

{"findings":[{"target":"<字段路径，如 analysis.judging_criteria>","rule_id":"<规则ID或空串>","severity":"BLOCKING|IMPROVEMENT","issue":"<问题>","suggested_fix":"<修订建议>"}]}

检查项：
1. 是否偏题、偷换概念：定义是否回应辩题、范围是否越界。
2. 判准与持方是否一致：判准能否说明胜负如何比较。
3. 必填字段（discussion_scope / affirmative_position / negative_position）是否非空。
4. 是否编造了请求里没有的事实、数据、出处。
5. 是否混入了 status / approved_by / 数据库 ID 等业务字段。
6. 政策辩是否给出可落地方向；脑洞题是否声明设定边界。
7. 定义/判准是否给了「骨干句」收口、判准是否配正例+反例；是否用定义战技巧锁定有利范围。
8. 若辩题隐含价值态度分野，是否写入 judging_criteria 或 opponent_attacks。
9. analysis.background / analysis.target_audience 是 Schema 内合法字符串字段，不因其存在判为缺陷；仅检查背景事实是否明确待核验、人群是否对应辩题而非稿件读者。字段合法性以运行器附带的 JSON Schema 为准。

severity 取 `BLOCKING`（必须修复，否则失败）或 `IMPROVEMENT`（建议优化）。
没有缺陷就返回 `{"findings":[]}`。这是模型自审，不能批准题解。只输出 JSON 对象。
