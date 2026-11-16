# 阶段：revise（定向修订）

根据 `findings`，只修改 `candidate` 对应部分，重新输出完整 `FrameworkResponse` JSON（结构同 draft）。

- 按 `target` 定位、按 `suggested_fix` 修改，不擅改无关字段。
- 修改后复核：ref 唯一、机理完整、evidence_needs 指向正确、无伪造、末端回扣判准。
- 保持已批准题解的定义与判准；仍不确定的事实写进 uncertainty_notes；不分配正式 UUID。
- 只能修订一次，不得把自审称为人工批准。

只输出 JSON。
