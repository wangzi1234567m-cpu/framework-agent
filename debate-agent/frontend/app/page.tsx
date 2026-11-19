"use client";

import { useEffect, useState } from "react";
import { api, exportMarkdown } from "../services/api";
import type { ProjectInput, Project, Topic, WorkingCopy, Revision, Job, Reasoning, DebateCase, TopicContent } from "../types/contracts";

const idempotency = () => crypto.randomUUID();
const pretty = (value: unknown) => JSON.stringify(value, null, 2);

function Mechanism({ nodes }: { nodes: Reasoning[] }) {
  return <ol className="mechanisms">{nodes.map(node => <li key={node.id}>
    <strong>{node.label || "机理"}</strong><p>{node.content}</p>
    {node.children.length > 0 && <Mechanism nodes={node.children} />}
  </li>)}</ol>;
}

export default function Workbench() {
  const [input, setInput] = useState<ProjectInput | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [topic, setTopic] = useState<Topic | null>(null);
  const [topicText, setTopicText] = useState("");
  const [working, setWorking] = useState<WorkingCopy | null>(null);
  const [caseText, setCaseText] = useState("");
  const [revision, setRevision] = useState<Revision | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [stage, setStage] = useState(0);
  const [mode, setMode] = useState("MOCK");
  const [model, setModel] = useState("mock-v1");
  const [notice, setNotice] = useState("");
  const [notes, setNotes] = useState<string[]>([]);
  const [testConfirmation, setTestConfirmation] = useState(false);

  useEffect(() => {
    async function initialize() {
      setTestConfirmation(new URLSearchParams(location.search).has("test"));
      const data = await api<{ project: ProjectInput; mode: string; model?: string; notice: string }>("/demo/config");
      setInput(data.project); setMode(data.mode); setModel(data.model || "mock-v1"); setNotice(data.notice);
      const session = await api<{ project_id: string | null; job_id: string | null; uncertainty_notes: string[]; test_confirmation?: boolean }>("/demo/session");
      setTestConfirmation(!!session.test_confirmation || new URLSearchParams(location.search).has("test"));
      if (!session.project_id) return;
      const restored = await api<Project>(`/api/v1/projects/${session.project_id}`);
      setProject(restored); setInput(restored);
      if (session.job_id) {
        const pending = await api<Job>(`/api/v1/jobs/${session.job_id}`);
        setJob(pending);
        if (["QUEUED", "RUNNING"].includes(pending.status)) {
          setBusy(true);
          try { await waitJob(session.job_id); } finally { setBusy(false); }
        }
      }
      await loadResults(restored.id);
    }
    initialize().catch(err => setError(err.message));
  }, []);

  async function loadResults(projectId: string) {
    const result = await api<Topic>(`/api/v1/projects/${projectId}/topic-analyses/current`).catch(() => null);
    if (result) { setTopic(result); setTopicText(pretty(result.content)); setStage(result.status === "APPROVED" ? 2 : 1); }
    const candidate = await api<WorkingCopy>(`/api/v1/projects/${projectId}/working-copy`).catch(() => null);
    if (candidate) { setWorking(candidate); setCaseText(pretty(candidate.case)); setStage(3); }
    const session = await api<{ uncertainty_notes: string[] }>("/demo/session");
    setNotes(session.uncertainty_notes);
  }

  async function waitJob(jobId: string) {
    for (let i = 0; i < 900; i++) {
      const current = await api<Job>(`/api/v1/jobs/${jobId}`);
      setJob(current);
      if (current.status === "SUCCEEDED") return;
      if (["FAILED", "CANCELLED"].includes(current.status)) throw new Error(current.error_code || "任务失败，候选未被批准");
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error("等待超时，任务仍保留在后端；刷新可查看状态，请勿重复提交。");
  }

  async function act(task: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try { await task(); } catch (err) { setError(err instanceof Error ? err.message : "操作失败"); }
    finally { setBusy(false); }
  }

  async function runJob(path: string, body: unknown) {
    const accepted = await api<{ job_id: string }>(path, "POST", body);
    setJob(await api<Job>(`/api/v1/jobs/${accepted.job_id}`));
    await api("/demo/run-next", "POST");
    await waitJob(accepted.job_id);
  }

  async function begin() {
    if (!input) return;
    const created = project || await api<Project>("/api/v1/projects", "POST", input);
    setProject(created);
    await runJob(`/api/v1/projects/${created.id}/topic-analysis-runs`, { idempotency_key: idempotency() });
    const result = await api<Topic>(`/api/v1/projects/${created.id}/topic-analyses/current`);
    setTopic(result); setTopicText(pretty(result.content)); setStage(1);
    await loadResults(created.id);
    setMessage("题解候选已生成。请检查讨论范围与判准，再人工确认。");
  }

  async function saveTopic() {
    if (!topic) return;
    const content = JSON.parse(topicText) as TopicContent;
    const result = await api<Topic>(`/api/v1/topic-analyses/${topic.id}/revisions`, "POST", {
      expected_version: topic.version, idempotency_key: idempotency(), content,
    });
    setTopic(result); setTopicText(pretty(result.content)); setWorking(null); setRevision(null);
    setTestConfirmation(new URLSearchParams(location.search).has("test"));
    setMessage("已保存新的待审题解版本，需要重新确认。");
  }

  async function approveTopic() {
    if (!topic) return;
    if (pretty(JSON.parse(topicText)) !== pretty(topic.content)) throw new Error("请先保存题解修改，再确认。");
    const automatedTest = new URLSearchParams(location.search).has("test");
    const result = await api<Topic>(`/api/v1/topic-analyses/${topic.id}/approval`, "POST", {
      expected_version: topic.version, decision: "APPROVED",
      comment: automatedTest ? "AUTOMATED_TEST_ONLY：流程演示确认，不代表用户审核" : "本机工作台用户确认",
    });
    setTestConfirmation(automatedTest);
    setTopic(result); setStage(2); setMessage(automatedTest ? "自动流程演示已模拟题解确认，不代表你的认可；框架仍待你审核。" : "题解已确认，可以生成框架。");
  }

  async function build() {
    if (!project || !topic || topic.status !== "APPROVED") return;
    await runJob(`/api/v1/projects/${project.id}/framework-runs`, {
      idempotency_key: idempotency(), approved_topic_analysis_id: topic.id, expected_topic_version: topic.version,
    });
    const result = await api<WorkingCopy>(`/api/v1/projects/${project.id}/working-copy`);
    setWorking(result); setCaseText(pretty(result.case)); setRevision(null); setStage(3);
    await loadResults(project.id);
    setMessage("框架候选已进入工作区，尚未成为正式版本。");
  }

  async function saveCase() {
    if (!working) return;
    const result = await api<WorkingCopy>(`/api/v1/cases/${working.id}/working-copy`, "PATCH", {
      expected_edit_version: working.edit_version, case: JSON.parse(caseText) as DebateCase,
    });
    setWorking(result); setCaseText(pretty(result.case)); setRevision(null);
    setMessage("工作区修改已保存。");
  }

  async function confirmCase() {
    if (!working) return;
    if (pretty(JSON.parse(caseText)) !== pretty(working.case)) throw new Error("请先保存框架修改，再确认。");
    const result = await api<Revision>(`/api/v1/cases/${working.id}/revisions`, "POST", {
      expected_edit_version: working.edit_version, idempotency_key: idempotency(),
    });
    setRevision(result); setStage(4); setMessage("正式版本已确认，可以导出 Markdown。");
  }

  async function download() {
    if (!revision) return;
    const blob = new Blob([await exportMarkdown(revision.id)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url;
    link.download = `framework-v${revision.revision_number}.md`; link.click();
    URL.revokeObjectURL(url);
  }

  async function downloadCandidate() {
    if (!working || !project) return;
    if (pretty(JSON.parse(caseText)) !== pretty(working.case)) throw new Error("请先保存框架修改，再下载候选。");
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001"}/demo/projects/${project.id}/candidate-export`);
    if (!response.ok) throw new Error("候选导出失败，请检查本机服务后重试。");
    const text = await response.text();
    const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "框架候选-待审核.md"; link.click();
    URL.revokeObjectURL(url);
  }

  function newProject() {
    setProject(null); setTopic(null); setWorking(null); setRevision(null); setJob(null);
    setTestConfirmation(new URLSearchParams(location.search).has("test"));
    setTopicText(""); setCaseText(""); setNotes([]); setStage(0); setMessage("修改设置后生成新的题解，不会覆盖此前项目。");
  }

  const steps = ["备赛设置", "题解审核", "框架生成", "工作区", "正式版本"];
  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/"><span className="brand-mark">辩</span><span>辩论工坊<small>DEBATE WORKBENCH</small></span></a>
      <div className="side-caption">我的备赛</div>
      <div className="side-active">框架稿工作台 <span>01</span></div>
      <div className="side-muted">写作方法库 <small>DRAFT 方法包</small></div>
      <div className="side-muted">对照实验 <small>离线 CLI</small></div>
      <div className="side-bottom"><span className="dot" /> 本机开发环境<p>{mode === "REAL" ? "真实模型候选，等待你审核。" : "Mock 只验证流程，不评价写作能力。"}</p></div>
    </aside>
    <main>
      <header><div className="breadcrumb">我的备赛 <span>/</span> 框架稿工作台</div><span className="badge">LOCAL {mode}</span></header>
      <div className="main-content">
        <div className="title-row"><div><p className="eyebrow">从一个问题，走向完整论证</p><h1>搭建你的论证框架</h1><p className="subtitle">先厘清题意，再构建论证。关键判断始终由你确认。</p></div><span className="edition">MVP · 工作流预览</span></div>
        <div className="notice"><strong>{mode === "REAL" ? "真实模型 · 待人工审核" : "合成演示模式"}</strong><span>{notice}</span></div>
        {testConfirmation && <p className="notice">自动流程测试：题解确认记录仅用于验证后半流程，不代表你的审核；实际题解与框架都请你复核。</p>}
        <nav className="steps" aria-label="工作流进度">{steps.map((name, i) => <div key={name} className={stage >= i ? "reached" : ""}><span>{stage > i ? "✓" : `0${i + 1}`}</span>{name}</div>)}</nav>
        {error && <div role="alert" className="error">{error}<button onClick={() => location.reload()}>刷新重连</button></div>}
        {message && <p role="status" className="success">{message}</p>}
        <div className="workspace">
          <div className="primary-column">
            <section className="card">
              <div className="section-heading"><div><span className="section-number">01</span><h2>备赛设置</h2></div><span className="muted">{mode === "REAL" ? "真实生成，可修改设置" : "固定合成示例"}</span></div>
              <label>辩题<input value={input?.motion || ""} readOnly={mode !== "REAL" || !!project || busy} onChange={e => input && setInput({ ...input, motion: e.target.value })} placeholder="连接后端后载入辩题" /></label>
              <div className="form-grid"><label>持方<select value={input?.side || "正方"} disabled={mode !== "REAL" || !!project || busy} onChange={e => input && setInput({ ...input, side: e.target.value })}><option>正方</option><option>反方</option></select></label><label>赛制<input value={input?.format || ""} readOnly={mode !== "REAL" || !!project || busy} onChange={e => input && setInput({ ...input, format: e.target.value })} /></label></div>
              {mode === "REAL" && <><label>立论时长（秒，不限制框架篇幅）<input type="number" min="1" value={input?.duration_seconds || 240} disabled={!!project || busy} onChange={e => input && setInput({ ...input, duration_seconds: Number(e.target.value) })} /></label><label>写作要求<textarea value={input?.user_requirements || ""} disabled={!!project || busy} onChange={e => input && setInput({ ...input, user_requirements: e.target.value })} /></label></>}
              <div className="card-footer"><span>立论时长 {input?.duration_seconds || 240} 秒</span><button disabled={busy || !input || !!topic} onClick={() => act(begin)}>{busy && !topic ? "执行中…" : "生成题解"} <span>→</span></button></div>
              {project && <button className="secondary" disabled={busy} onClick={newProject}>新建备赛项目</button>}
            </section>
            {topic ? <section className="card">
              <div className="section-heading"><div><span className="section-number">02</span><h2>题解与判断依据</h2></div><span className="pill">{topic.status === "APPROVED" ? testConfirmation ? "流程测试确认" : "已确认" : "待人工审核"} · v{topic.version}</span></div>
              <h3>背景与人群</h3><p>{topic.content.background || "背景待确认"}</p><p>{topic.content.target_audience || "人群待确认"}</p>
              <h3>关键定义</h3>{Object.entries(topic.content.definitions).map(([term, text]) => <p key={term}><strong>{term}：</strong>{text}</p>)}
              <h3>讨论范围</h3><p>{topic.content.discussion_scope}</p>
              <h3>双方立场</h3><p>正方：{String(topic.content.affirmative_position || "")}</p><p>反方：{String(topic.content.negative_position || "")}</p>
              <h3>核心争议</h3><ul>{topic.content.core_conflicts.map(text => <li key={text}>{text}</li>)}</ul>
              <h3>判准</h3><ul>{topic.content.judging_criteria.map(text => <li key={text}>{text}</li>)}</ul>
              <h3>论证方向</h3><ul>{topic.content.strategy_options.map(text => <li key={text}>{text}</li>)}</ul>
              <details><summary>编辑题解结构化内容</summary><label className="sr-only" htmlFor="topic-json">题解 JSON</label><textarea id="topic-json" value={topicText} onChange={e => setTopicText(e.target.value)} disabled={busy} spellCheck={false} />
                <button className="secondary" disabled={busy} onClick={() => act(saveTopic)}>保存题解修改</button></details>
              <div className="card-footer"><span>自审不能代替人工批准</span><button disabled={busy || topic.status === "APPROVED"} onClick={() => act(approveTopic)}>确认题解</button></div>
            </section> : <section className="card empty"><div className="empty-symbol">论</div><h2>好的框架，始于清晰的题解</h2><p>生成题解后，你将在这里检查讨论范围、核心争议与判准。</p><div className="empty-tags"><span>定义与范围</span><span>核心争议</span><span>比较判准</span></div></section>}
            {working && <section className="card">
              <div className="section-heading"><div><span className="section-number">03</span><h2>框架工作区</h2></div><span className="pill">编辑版本 {working.edit_version}</span></div>
              <h3 className="thesis">{working.case.thesis}</h3>
              {working.case.arguments.map((argument, index) => <article className="argument" key={argument.id}>
                <span className="argument-index">论点 {index + 1}</span><h3>{argument.title}</h3><p>{argument.core_claim}</p><p className="muted">{argument.explanation}</p>
                <Mechanism nodes={argument.reasoning_nodes} /><h4>现实影响</h4><p>{argument.impact}</p>
                <div className="evidence"><h4>待查证据</h4>{argument.evidence_needs.map(need => <p key={need.id}>{need.question}<small>{need.acceptable_source}</small></p>)}</div>
                {argument.attack_defense.map((item, i) => <div className="defense" key={i}><h4>攻防</h4><p>对方：{item.opposing_claim}</p><p>回应：{item.response}</p><p>比较：{item.weighing}</p></div>)}
              </article>)}
              <h3>比较与权衡</h3><p>{working.case.weighing}</p>
              <details><summary>编辑框架结构化内容</summary><label className="sr-only" htmlFor="case-json">框架 JSON</label><textarea id="case-json" value={caseText} onChange={e => setCaseText(e.target.value)} disabled={busy} spellCheck={false} /><button className="secondary" disabled={busy} onClick={() => act(saveCase)}>保存框架修改</button></details>
              <h3>整体策略</h3><p>{working.case.overall_strategy}</p>
              <button className="secondary" onClick={() => act(downloadCandidate)} disabled={busy}>下载待审核框架</button>
              <div className="card-footer"><span>请由你审核；候选不会自动转正式版本</span><button disabled={busy || !!revision} onClick={() => act(confirmCase)}>确认框架版本</button></div>
            </section>}
            {notes.length > 0 && <section className="card"><h3>待核验与自审遗留问题</h3><ul>{notes.map((text, i) => <li key={i}>{text}</li>)}</ul></section>}
          </div>
          <aside className="context-column">
            <section className="card guide"><span className="eyebrow">WORKFLOW</span><h2>下一步</h2><p>{!topic ? "从题解开始，明确我们究竟在比较什么。" : topic.status !== "APPROVED" ? "检查题解；有修改先保存，再确认当前版本。" : !working ? "用已经确认的题解，展开论点与机理。" : !revision ? "检查框架候选，保存修改并确认正式版本。" : "闭环已完成。导出你的正式版本。"}</p>
              <button className="full" disabled={busy || topic?.status !== "APPROVED"} onClick={() => act(build)}>生成框架 <span>→</span></button>
              {revision && <button className="secondary full" disabled={busy} onClick={() => act(download)}>导出 Markdown · v{revision.revision_number}</button>}
            </section>
            <section className="card compact"><h3>运行记录</h3><div className="record"><span>模型</span><strong>{model}</strong></div><div className="record"><span>方法版本</span><strong>0.1.0 · DRAFT</strong></div><div className="record"><span>任务状态</span><strong>{job?.status || "尚未开始"}</strong></div><div className="record"><span>当前步骤</span><strong>{job?.current_step || "—"}</strong></div><p className="footnote">本页面只供本机单用户测试；生产 API 仍要求可信身份。</p></section>
            <section className="experiment-note"><h3>方法是否带来增量？</h3><p>离线程序将同一份确认题解交给同一模型，以相同工作流对比有 / 无 Skill。当前不展示未经评审的质量分数。</p><code>python -m app.experiments</code></section>
          </aside>
        </div>
        <footer>辩论工坊 · 让每一步论证都可检查、可确认、可追溯</footer>
      </div>
    </main>
  </div>;
}
