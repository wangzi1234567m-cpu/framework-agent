# 阶段：revise（定向修订）

根据 `findings` 中列出的缺陷，只修改 `candidate` 里对应的部分，重新输出**完整** `TopicResponse` JSON（结构同 draft 阶段）。

- 逐个处理 `findings`：按 `target` 定位字段，按 `suggested_fix` 修改。
- 不擅改与缺陷无关的字段。
- 修改后再次确认满足 draft 阶段全部要求，且不引入新的 BLOCKING 缺陷。
- 仍无法确定的事实继续写进 `uncertainty_notes`，不编造。
- 只能修订一次，不得把自审称为人工批准。

只输出 JSON 对象。
