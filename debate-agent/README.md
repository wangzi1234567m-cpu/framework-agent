# Debate Agent

面向辩手的框架稿 Agent：题解、人工确认、框架生成和编辑确认。已有 Next.js 本机真实/Mock 工作台、后端闭环及同模型有/无 Skill 离线对照入口；真实鉴权、已审核写作方法、正式模型效果和最终评分验收仍待完成。

## 项目文档

- [产品需求](docs/PRODUCT_REQUIREMENTS.md)：目标、用户价值、MVP 与后续方向。
- [架构与模块契约](docs/ARCHITECTURE.md)：架构图、技术选型、数据/API、Agent 工作流以及可转交的 Skill/Prompt 交付格式。
- [MVP 范围与验收](docs/MVP.md)：题解到框架闭环及通用模型 A/B/C 对照。
- [开发阶段与双人协作](docs/DEVELOPMENT_PLAN.md)：双方职责、阶段及退出条件。
- [项目协作边界](AGENTS.md)；[PR 模板](.github/pull_request_template.md)。`docs/PRD.docx` 是**历史 Word 导出**，不是现行需求；生效 CI 位于上层仓库根目录 `.github/workflows/debate-agent-ci.yml`。

当前项目位于上层 `框架稿/` 的 public Git 仓库内；根目录原始稿件已经出现在仓库历史中。**不要将未经授权的其他稿件、密钥或真实用户资料提交到 public 仓库**；`.gitignore` 无法撤销既有公开历史。当前改动只保存在本地，未自动推送。

## 目录与阶段

```text
frontend/                     A：Next.js 本机真实/Mock 工作台
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
  samples/ skills/ evals/      已合并两套 DRAFT 方法包和评分草案；发布清单仍为空
local-evaluations/             本地真实模型结果与盲评材料，Git 忽略，不上传 public 仓库
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

`/health` 检测进程；`/ready` 在未配置 `DATABASE_URL` 或数据库不可用时返回 503。业务接口**默认全部拒绝**，须先用真实身份提供商替换 `require_actor`，不可把请求头里的 UUID 当登录。对自己控制的空库配置 `DATABASE_URL` 后，在 `backend/` 目录运行 `python -m alembic -c alembic.ini upgrade head`；不要直接对现有数据执行迁移。独立 worker 在该目录运行 `python -m app.workflow.main --drain`，需要 `LLM_BASE_URL`（HTTPS，含适配服务的 `/v1`）、`LLM_API_KEY`、`LLM_MODEL` 环境变量；模型接口需支持 JSON object 响应。默认发布清单 `backend/knowledge/skills/published.json` 为空，两个 `0.1.0` 包已填充方法内容，但仍是未经发布审核的草案，故正常 API 不会创建生成任务；经审核登记包哈希后才能启用。无真实数据库/密钥也可执行合成测试 `python -m unittest discover -s backend/tests -v`。

`app/agents/skills.py` 是方法包校验与只读加载器，`app/agents/runtime.py` 是两个 Agent 的分步执行入口，`app/services/mvp.py` 是唯一业务写入处，`app/workflow/runner.py` 领取、续租并提交任务结果。API 业务路由经依赖注入可测试，但真实身份未接入前一律返回 `503 AUTH_NOT_CONFIGURED`。当前只在 SQLite 上验证了迁移与单进程模拟闭环；本机 Mock 界面可用，真实 PostgreSQL 并发和效果优势仍待验证。

方法负责人可按 `backend/knowledge/skills/topic-analysis/0.1.0/` 和 `framework-building/0.1.0/` 的草案格式交包：各含 `manifest.json`、`SKILL.md`、四段 Prompt、合法/拒绝示例。从 `backend/` 运行 `python -m app.agents.skills TOPIC 0.1.0` 或 `python -m app.agents.skills FRAMEWORK 0.1.0` 检查包并查看 SHA-256；命令**不会发布草案**。审查通过后，系统负责人在 `published.json` 登记包哈希、审核人、时间和 active 版本；`--published` 可验证是否真的入白名单。

## 本机 Mock 工作台

需要 Node.js 20.9+、Python 3.11+；不需要数据库服务或 API Key。两个终端分别启动：

```powershell
# 终端 1，debate-agent/backend/ 目录
python -m uvicorn app.demo:app --host 127.0.0.1 --port 8001
```

```powershell
# 终端 2，debate-agent/frontend/ 目录
npm ci
npm run dev
```

打开 `http://127.0.0.1:3000`。页面固定使用合成示例题，可执行题解生成、JSON 编辑/保存、人工确认、框架候选生成、编辑/确认正式版本及 Markdown 导出。Mock 复用真实 Service 和 Runner，但模型响应是固定 fixture，不能测试任意辩题的质量。样例读取两套 `0.1.0` Skill 包的合法示例，修改样例后应重新验证。刷新可恢复最新项目和候选，后端重启清空临时 SQLite；这不是正式用户数据持久化方案。

`app.demo` 是独立应用：临时数据库在系统临时目录、不读取 `.env` 或调用外部模型；仅接受 localhost/127.0.0.1 Host、回环访问以及本机 3000 端口 Origin。它使用固定模拟身份，不得部署到服务器、反向代理后或绑定 `0.0.0.0`。生产 `app.main` 没有开放此身份覆盖。前端可用 `NEXT_PUBLIC_API_URL` 指定不同本机 API 地址，但该变量不能包含任何 Key。检查前端使用 `npm run typecheck`、`npm run build`。

## 本机真实 DeepSeek 工作台

项目 `.env` 配置好 Key 后，用下面命令**替代** Mock 后端，不要同时占用 8001；前端启动方式不变。真实调用会计费。

```powershell
# debate-agent/backend/ 目录
python -m uvicorn app.local_real:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:3000`，确认顶部为 `LOCAL REAL`。默认生态文化题、正方“离不开传统文化的滋养”，可在新项目中修改持方和写作要求。生成题解后必须由人确认，才能生成框架；可先下载待审核候选，不必确认正式版本。修改题解后须重新确认。`?test=1` 只用于显式标记自动流程演示，演示审批不代表用户认可。

真实本机库与阶段轨迹存于 `%LOCALAPPDATA%\DebateAgent\workbench`，刷新/重启能恢复最新项目和候选。后台 worker 持续领取本机任务；调用中不要随意重启，租约到期后的恢复可能增加调用费用。轨迹记录模型输出和用量，不含 Key。这是 Windows 单用户隔离测试入口，显式允许 DRAFT，**不是生产鉴权或 PostgreSQL 部署方案**；不能反代、部署或绑定公网。

默认单次输出预算：题解 `16384` token，框架 `32768` token，可用 `LLM_TOPIC_MAX_TOKENS`、`LLM_FRAMEWORK_MAX_TOKENS` 覆盖；默认 HTTP 超时150秒、Agent 单阶段180秒。预算不是目标字数，也不是提供方能力保证，换模型需核对其上限。备赛框架不按240秒陈词压缩。

## 同模型有 / 无 Skill 离线对照

从 `backend/` 运行以下烟测，输出目录必须是尚不存在的新目录：

```powershell
python -m app.experiments --model mock --kind FRAMEWORK --allow-draft --output "$env:TEMP/debate-ab-smoke-01"
```

真实模型配置使用项目 `.env` 中的 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL`；CLI 自动加载，已有进程环境变量优先。装好更新的 `requirements-dev.txt`，在 `.env` 填 Key 后，由系统负责人显式运行真实模型实验（会计费）：

```powershell
python -m app.experiments --model real --kind FRAMEWORK --allow-draft --cases "E:\私有评测题\cases.json" --repeats 3 --output "E:\私有评测结果\run-01"
```

`cases.json` 是 `[{"case_id": "case-01", "request": {...完整 FrameworkRequest...}}]`；框架 request 中包含由人确认的 `approved_topic`，每组必须相同。也支持 `--kind TOPIC` 和完整 `TopicRequest`。程序将 context 的 Skill/规则版本固定为本次包版本，不修改题解内容；输入文件先通过 Pydantic 校验。没有 `--cases` 时只跑内置合成示例，即使调用真实模型也不是正式 benchmark。

对照两组为 **WITHOUT_SKILL（通用指令 + Schema）**、**WITH_SKILL（方法包 + Schema）**，都经分析、初稿、自审、一次修订、再审，成功时各五次调用。不读取任何专有 Skill 正文或分步 Prompt 的基线仍保留通用任务与安全指令，不能把“无 Skill”误解为无提示词。单次上限默认按题解16384/框架32768 token，可通过 `--max-tokens` 覆盖；`--temperature` 默认 0。调用顺序随机化，可重复生成，失败保留，不自动重试或挑选最佳结果。两组成功时预算上限相同，但实际输入 token 和费用会因方法长度不同而变化。

完整输出 Schema 由共享 Agent 运行器附加，不仅用于实验；Service/Runner 调用同样受此边界约束。2026-11-19 已同步 PR #1 并使用 DeepSeek 做题解/框架小规模接入烟测；详细轨迹与未评分的匿名稿保存在本机 `local-evaluations/`。它们使用包内示例题，不是独立测试集，不构成效果优势结论。修订方法包后按新 SHA-256 单独保存复测，不合并成同一版本的样本。

每次导出四个文件：

- `private-results.json`：输入、完整阶段 Prompt/响应、包哈希、模型、参数、Git 版本/工作区是否脏、每次调用耗时与服务返回的 token。
- `blind-review.json`：匿名候选和配对编号，隐藏组别/方法及耗时，评分为 null；只把它交给盲评人。输出风格仍可能暴露组别，不保证绝对双盲。
- `private-mapping.json`：解盲映射，评分冻结前不交给评审人。
- `comparison.json`：各组完成率、平均耗时与调用次数；质量结论保持 `NOT_EVALUATED`。

可提供 `--input-price/--output-price`（同货币每百万 token）估算成本；未提供或 token 未返回时为 null，不冒充零成本。估算不含缓存优惠等服务方计费差异。输出含用户材料和方法正文，只存私有目录，不提交 public Git。当前暂未接通评分导入、质量胜负/统计置信区间或原生单次通用模型 A 组；正式 A/B/C 结论按 [MVP](docs/MVP.md) 的规程另行验收。此程序先验证 B/C 方法增量，不能凭 Mock 或合法 Schema 宣布 Skill 有效。

## 第一阶段提取

最新结构标注以 [experience](docs/experience.md) 的关系要求为依据。9份 Markdown 自动候选、3份重点稿关系解释保存在私有 `local-evaluations/structure-annotations-v3`；规则与样本代号索引在 `backend/knowledge/rules/structure-v1.json`、`samples/index.json`。规则已写入两套 DRAFT Skill，加载器不会自动从原稿学习；原文、AI解释、人审状态分离，出处尚未核验。复核引用：

```powershell
python backend/scripts/annotate_structure.py --source ".." --output "local-evaluations/structure-annotations-v3" --validate-only
```

需要 Python 3.11+；契约测试依赖 Pydantic v2，PDF 文字层解析依赖 PyMuPDF：`python -m pip install -r backend/requirements-contracts.txt pymupdf`。MD、DOCX 和 Word 导出脚本只用标准库。扫描版 PDF 需另行 OCR。以下命令均在 `debate-agent/` 中运行：

```powershell
python backend/scripts/extract_frameworks.py
python -m unittest discover -s backend/tests -v
```

Word 导出脚本仍可用于需要的临时文档，但旧 `PRD.docx` 不会随本次 Markdown 精简自动更新。

可传入 `--source "E:\稿件目录" --output "E:\输出目录"`。提取脚本只扫描输入目录直接子文件（`.md`、`.docx`、`.pdf`），跳过 Word `~$` 临时锁文件；不会修改原稿。已生成的 [manifest](backend/knowledge/examples/manifest.json) 将文件名、SHA-256、解析结果和失败原因关联起来；旧 JSON 不会自动清理，请以 manifest 为当次运行的索引。只有当前环境安装 PyMuPDF 时才能重新完整解析 PDF。

JSON 中的判准/论点/机理/案例/数据/来源只是规则匹配的**候选原文片段**，不是事实核验或人工批准；Markdown 丢失的图片在 `image_gaps` 中标记，未做 OCR。背景见[第二轮分析报告](backend/knowledge/annotations/analysis_report_md_update.md)、[第一轮历史快照](backend/knowledge/annotations/analysis_report.md)和[待审写作规则](backend/knowledge/rules/framework_rules.md)。原稿及未经授权材料不得被自动公开。
