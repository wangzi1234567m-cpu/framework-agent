# Debate Agent

AI 辩论论证生产与稿件辅助工作台。当前处于 **P0：设计与仓库准备**：已有第一阶段框架稿经验提取，但题解、框架生成、证据审核、前端和立论稿流程尚未实现。

## 项目文档

- [PRD V1.0](docs/PRD.md) / [Word 版](docs/PRD.docx)：产品需求，待双人评审冻结。
- [SAD V1.0](docs/SAD.md)：来自用户提供的完整架构原文，待双人评审冻结。
- [双人协作规范](docs/TEAM_DEVELOPMENT.md)：A 负责系统契约/Schema/API/工作流，B 负责 Agent/方法论/评测。
- [领域模型](docs/DOMAIN_MODEL.md)、[Agent 契约](docs/AGENT_CONTRACTS.md)、[API](docs/API_SPEC.md)、[证据](docs/EVIDENCE_SPEC.md)、[知识](docs/KNOWLEDGE_SPEC.md)、[评测](docs/EVAL_SPEC.md)均是**待编制的入口，不是已冻结契约**。
- [项目协作边界](AGENTS.md)；[PR 模板](.github/pull_request_template.md)；基础 CI 配置仅在 GitHub 仓库创建后才会运行。

当前本地项目**还不是 Git 仓库**，没有自动创建私有 GitHub 仓库、分支保护或 Issues。

## 目录与阶段

```text
frontend/                     A：Next.js 目标目录（尚无应用）
backend/app/
  api/ core/ domain/ schemas/ models/ repositories/ services/  A：未实现
  workflow/                    A：旧空白占位，未实现
  agents/                      B：旧空白占位，未实现
  infrastructure/llm/ search/ documents/  A/B 接口边界，未实现
backend/knowledge/
  examples/                    未审核的自动解析样本及 manifest
  annotations/                 第一阶段两轮分析报告
  rules/                       待审写作规则草案
  samples/ skills/ evals/      B：正式资产目标目录；evals/ 只有旧空白占位
backend/scripts/              已有提取脚本和 PRD DOCX 导出器
backend/tests/                已有提取脚本测试；agents/ integration/ 尚空
backend/alembic/              A：待初始化
docs/                         正式文档及尚待编制的契约入口
.github/                      PR 模板与解析器基础 CI
```

## 第一阶段提取

需要 Python 3.10+；PDF 文字层解析依赖 PyMuPDF：`python -m pip install pymupdf`。MD、DOCX 和 Word 导出脚本只用标准库。扫描版 PDF 需另行 OCR。以下命令均在 `debate-agent/` 中运行：

```powershell
python backend/scripts/extract_frameworks.py
python -m unittest discover -s backend/tests -v
python backend/scripts/export_docx.py docs/PRD.md docs/PRD.docx
```

可传入 `--source "E:\稿件目录" --output "E:\输出目录"`。提取脚本只扫描输入目录直接子文件（`.md`、`.docx`、`.pdf`），跳过 Word `~$` 临时锁文件；不会修改原稿。已生成的 [manifest](backend/knowledge/examples/manifest.json) 将文件名、SHA-256、解析结果和失败原因关联起来；旧 JSON 不会自动清理，请以 manifest 为当次运行的索引。只有当前环境安装 PyMuPDF 时才能重新完整解析 PDF。

JSON 中的判准/论点/机理/案例/数据/来源只是规则匹配的**候选原文片段**，不是事实核验或人工批准；Markdown 丢失的图片在 `image_gaps` 中标记，未做 OCR。背景见[第二轮分析报告](backend/knowledge/annotations/analysis_report_md_update.md)、[第一轮历史快照](backend/knowledge/annotations/analysis_report.md)和[待审写作规则](backend/knowledge/rules/framework_rules.md)。原稿及未经授权材料不得被自动公开。
