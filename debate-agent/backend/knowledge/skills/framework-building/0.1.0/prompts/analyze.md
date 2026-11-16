# 阶段：analyze（分析输入）

读入 `request`，重点是 `approved_topic`（已确认题解：definitions / discussion_scope / judging_criteria / strategy_options 等）以及 `motion / side`。

返回 JSON 对象 `analysis`，至少包含：
- `thesis_hint`：立论主旨方向
- `argument_plan`：拟设计的论点数组，每个含 `title`、`core_claim`、`division_reason`（分工依据：不同原因或受益维度）
- `must_follow`：从题解中必须遵守的定义与判准要点
- `uncertainties`：不确定点

要求：论点之间分工清晰、不重复表达；不修改题解、不假设能读到未传入的工作区正文。只输出 JSON 对象。
