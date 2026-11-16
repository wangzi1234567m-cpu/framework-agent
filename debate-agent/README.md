# Debate Agent

面向辩手的框架稿 Agent：题解、人工确认、框架生成和编辑确认。目前能用合成模型响应在迁移后的测试数据库中跑通该闭环；真实鉴权、已审核写作方法、正式模型效果、前端和对照实验尚未完成。

## 项目文档

- [产品需求](docs/PRODUCT_REQUIREMENTS.md)：目标、用户价值、MVP 与后续方向。
- [架构与模块契约](docs/ARCHITECTURE.md)：架构图、技术选型、数据/API、Agent 工作流以及可转交的 Skill/Prompt 交付格式。
- [MVP 范围与验收](docs/MVP.md)：题解到框架闭环及通用模型 A/B/C 对照。
- [开发阶段与双人协作](docs/DEVELOPMENT_PLAN.md)：双方职责、阶段及退出条件。
- [项目协作边界](AGENTS.md)；[PR 模板](.github/pull_request_template.md)。`docs/PRD.docx` 是**历史 Word 导出**，不是现行需求；生效 CI 位于上层仓库根目录 `.github/workflows/debate-agent-ci.yml`。

当前项目位于上层 `框架稿/` 的 public Git 仓库内；根目录原始稿件已经出现在仓库历史中。**不要将未经授权的其他稿件、密钥或真实用户资料提交到 public 仓库**；`.gitignore` 无法撤销既有公开历史。当前改动只保存在本地，未自动推送。

## 目录与阶段

```text
frontend/                     A：Next.js 目标目录（尚无应用）
backend/app/
  api/ core/ models/ services/  A：可注入可信身份的路由、ORM、Service 与候选映射
  repositories/ domain/       A：旧目录占位；P1 持久化实现位于 services/ 与 models/
  schemas/                    A：domain/agent/api Pydantic 契约评审稿
  workflow/                    A：有限租约的独立 Runner；真实 PG 并发尚待验证
  agents/                      A：两个逻辑 Agent 的四段 Prompt/自审运行骨架
  infrastructure/llm/          A：可配置 OpenAI-compatible JSON 模型适配
backend/knowledge/
  examples/                    未审核的自动解析样本及 manifest
  annotations/                 第一阶段两轮分析报告
  rules/                       待审写作规则草案
  samples/ skills/ evals/      skills/ 为两套 DRAFT 样板及空发布清单，尚未正式审批
backend/scripts/              已有提取脚本和 PRD DOCX 导出器
backend/tests/                已有提取脚本测试；agents/ integration/ 尚空
backend/alembic/              A：P1、幂等命令及旧工作区归档迁移；本地仅做 SQLite 测试
docs/                         四份现行 Markdown + 历史 PRD.docx
.github/                      PR 模板与旧 CI；生效 CI 位于上层仓库根目录
```

## P1 可运行骨架

从 `debate-agent/` 运行：

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -v
python -m uvicorn app.main:app --app-dir backend
```

`/health` 检测进程；`/ready` 在未配置 `DATABASE_URL` 或数据库不可用时返回 503。业务接口**默认全部拒绝**，须先用真实身份提供商替换 `require_actor`，不可把请求头里的 UUID 当登录。对自己控制的空库配置 `DATABASE_URL` 后，在 `backend/` 目录运行 `python -m alembic -c alembic.ini upgrade head`；不要直接对现有数据执行迁移。独立 worker 在该目录运行 `python -m app.workflow.main --drain`，需要 `LLM_BASE_URL`（HTTPS，含适配服务的 `/v1`）、`LLM_API_KEY`、`LLM_MODEL` 环境变量；模型接口需支持 JSON object 响应。默认发布清单 `backend/knowledge/skills/published.json` 为空，两个 `0.1.0` 包只是占位草案，故正常 API 不会创建生成任务；经审核登记包哈希后才能启用。无真实数据库/密钥也可执行合成测试 `python -m unittest discover -s backend/tests -v`。

`app/agents/skills.py` 是方法包校验与只读加载器，`app/agents/runtime.py` 是两个 Agent 的分步执行入口，`app/services/mvp.py` 是唯一业务写入处，`app/workflow/runner.py` 领取、续租并提交任务结果。API 业务路由经依赖注入可测试，但真实身份未接入前一律返回 `503 AUTH_NOT_CONFIGURED`。当前只在 SQLite 上验证了迁移与单进程模拟闭环；真实 PostgreSQL 并发、人工界面和效果优势仍待验证。

方法负责人可按 `backend/knowledge/skills/topic-analysis/0.1.0/` 和 `framework-building/0.1.0/` 的草案格式交包：各含 `manifest.json`、`SKILL.md`、四段 Prompt、合法/拒绝示例。从 `backend/` 运行 `python -m app.agents.skills TOPIC 0.1.0` 或 `python -m app.agents.skills FRAMEWORK 0.1.0` 检查包并查看 SHA-256；命令**不会发布草案**。审查通过后，系统负责人在 `published.json` 登记包哈希、审核人、时间和 active 版本；`--published` 可验证是否真的入白名单。

## 第一阶段提取

需要 Python 3.11+；契约测试依赖 Pydantic v2，PDF 文字层解析依赖 PyMuPDF：`python -m pip install -r backend/requirements-contracts.txt pymupdf`。MD、DOCX 和 Word 导出脚本只用标准库。扫描版 PDF 需另行 OCR。以下命令均在 `debate-agent/` 中运行：

```powershell
python backend/scripts/extract_frameworks.py
python -m unittest discover -s backend/tests -v
```

Word 导出脚本仍可用于需要的临时文档，但旧 `PRD.docx` 不会随本次 Markdown 精简自动更新。

可传入 `--source "E:\稿件目录" --output "E:\输出目录"`。提取脚本只扫描输入目录直接子文件（`.md`、`.docx`、`.pdf`），跳过 Word `~$` 临时锁文件；不会修改原稿。已生成的 [manifest](backend/knowledge/examples/manifest.json) 将文件名、SHA-256、解析结果和失败原因关联起来；旧 JSON 不会自动清理，请以 manifest 为当次运行的索引。只有当前环境安装 PyMuPDF 时才能重新完整解析 PDF。

JSON 中的判准/论点/机理/案例/数据/来源只是规则匹配的**候选原文片段**，不是事实核验或人工批准；Markdown 丢失的图片在 `image_gaps` 中标记，未做 OCR。背景见[第二轮分析报告](backend/knowledge/annotations/analysis_report_md_update.md)、[第一轮历史快照](backend/knowledge/annotations/analysis_report.md)和[待审写作规则](backend/knowledge/rules/framework_rules.md)。原稿及未经授权材料不得被自动公开。
