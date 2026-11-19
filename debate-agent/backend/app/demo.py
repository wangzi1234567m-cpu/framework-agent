"""Isolated localhost-only workbench API. Never deploy this application."""

from __future__ import annotations

import asyncio
import tempfile
from contextlib import asynccontextmanager
from contextlib import ExitStack
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agents.mock import SKILL_ROOT, SyntheticModel, synthetic_pair
from app.agents.skills import SkillError, SkillRegistry
from app.api.p1 import get_service, require_actor, router
from app.core.database import Base, session_scope
from app.main import handle_business_error, handle_http_error, handle_skill_error, handle_validation_error
from app.schemas.api import CreateProject
from app.services.mvp import BusinessError, MVPService
from app.services.export import render_case_markdown
from app.models.p1 import ApprovalRecord, GenerationJobRecord, ProjectRecord
from app.workflow.runner import JobRunner

ACTOR = UUID("00000000-0000-4000-8000-000000000001")
ALLOWED_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"}


class DemoService(MVPService):
    def _model_version(self) -> str:
        return "mock-v1"

    def create_project(self, actor: UUID, command: CreateProject):
        fixture = synthetic_pair("TOPIC")["request"]
        if (command.motion, command.side) != (fixture["motion"], fixture["side"]):
            raise BusinessError("MOCK_SUPPORTS_SYNTHETIC_MOTION_ONLY", 422)
        return super().create_project(actor, command)


def create_demo_app(*, real: bool = False, database_path: Path | None = None, model_factory=None) -> FastAPI:
    if real and (database_path is None or model_factory is None):
        raise ValueError("Real local workbench requires an explicit database and model factory")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with ExitStack() as stack:
            path = database_path if real else Path(stack.enter_context(
                tempfile.TemporaryDirectory(prefix="debate-agent-demo-")
            )) / "demo.sqlite"
            path.parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(f"sqlite:///{path}",
                                   connect_args={"check_same_thread": False})
            # Local sandbox only. Production databases must use Alembic migrations.
            Base.metadata.create_all(engine)
            app.state.sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
            app.state.lock = asyncio.Lock()
            app.state.worker = asyncio.create_task(work()) if real else None
            try:
                yield
            finally:
                if app.state.worker is not None:
                    app.state.worker.cancel()
                    await asyncio.gather(app.state.worker, return_exceptions=True)
                engine.dispose()

    demo = FastAPI(title=f"Debate Agent LOCAL {'REAL' if real else 'MOCK'} ONLY", lifespan=lifespan)
    skills = SkillRegistry(SKILL_ROOT)
    demo.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_ORIGINS),
                        allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])

    @demo.middleware("http")
    async def localhost_only(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        peer = request.client.host if request.client else ""
        origin = request.headers.get("origin")
        if host not in {"localhost", "127.0.0.1"} or peer not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse(status_code=403, content={"error_code": "LOCALHOST_ONLY"})
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return JSONResponse(status_code=403, content={"error_code": "ORIGIN_DENIED"})
        return await call_next(request)

    class LocalRealService(MVPService):
        def _model_version(self):
            return model_factory("TOPIC").model

    def service():
        with session_scope(demo.state.sessions) as session:
            yield (LocalRealService if real else DemoService)(session, skills, allow_draft=True)

    # Overrides belong to this separate application, not app.main.app.
    demo.dependency_overrides[require_actor] = lambda: ACTOR
    demo.dependency_overrides[get_service] = service
    demo.include_router(router)
    demo.add_exception_handler(BusinessError, handle_business_error)
    demo.add_exception_handler(SkillError, handle_skill_error)
    demo.add_exception_handler(HTTPException, handle_http_error)
    demo.add_exception_handler(RequestValidationError, handle_validation_error)

    @demo.get("/demo/config")
    def config():
        if real:
            return {"mode": "REAL", "model": model_factory("TOPIC").model,
                    "notice": "真实 DeepSeek 调用，会计费；本机持久库，题解及框架均需人工审核。",
                    "project": {"motion": "当代生态文化的发展，离不开传统文化的滋养/更需要面向未来开拓创新",
                                "side": "正方", "format": "4v4", "duration_seconds": 240,
                                "competition_context": "赛制细则待确认；240秒仅指一辩陈词，不限制备赛框架稿篇幅。",
                                "user_requirements": "题解至少1000汉字，完整框架约3500至6000汉字，优先完整结构而非凑字数。正方支持离不开传统文化的滋养，反方支持更需要面向未来开拓创新。背景→判准→分工论点→机理→案例/证据需求→诠释回扣→攻防比较。文学表达只属于审美，不替代证明。禁止伪造数据、出处；无检索时保留待核验。"}}
        request = synthetic_pair("TOPIC")["request"]
        return {"mode": "MOCK", "notice": "合成数据，不代表真实模型效果；重启后数据清空。",
                "project": {key: value for key, value in request.items() if key != "context"}}

    async def drain():
        async with demo.state.lock:
            runner = JobRunner(demo.state.sessions, skills, model_factory if real else SyntheticModel,
                               "local-real" if real else "local-mock", allow_draft=True)
            processed = await runner.run_once()
            return {"processed": processed}

    async def work():
        while True:
            await drain()
            await asyncio.sleep(1)

    @demo.post("/demo/run-next")
    async def run_next():
        if not real:
            return await drain()
        if demo.state.worker is None or demo.state.worker.done():
            demo.state.worker = asyncio.create_task(work())
        return {"scheduled": True}

    @demo.get("/demo/session")
    def latest_session():
        with session_scope(demo.state.sessions) as session:
            project = session.scalar(select(ProjectRecord).where(ProjectRecord.owner_id == ACTOR)
                                     .order_by(ProjectRecord.created_at.desc()).limit(1))
            job = session.scalar(select(GenerationJobRecord).where(GenerationJobRecord.project_id == project.id)
                                 .order_by(GenerationJobRecord.created_at.desc()).limit(1)) if project else None
            approval = session.scalar(select(ApprovalRecord).where(
                ApprovalRecord.target_id == project.current_approved_topic_id
            ).order_by(ApprovalRecord.created_at.desc()).limit(1)) if project and project.current_approved_topic_id else None
            return {"project_id": str(project.id) if project else None,
                    "job_id": str(job.id) if job else None,
                    "test_confirmation": bool(approval and approval.comment.startswith("AUTOMATED_TEST_ONLY")),
                    "uncertainty_notes": (job.output_snapshot or {}).get("uncertainty_notes", []) if job else []}

    @demo.get("/demo/projects/{project_id}/candidate-export")
    def candidate_export(project_id: UUID):
        with session_scope(demo.state.sessions) as session:
            service = MVPService(session, skills, allow_draft=True)
            working = service.project_working(ACTOR, project_id)
            topic = service.get_topic(ACTOR, working.approved_topic_analysis_id)
            job = session.scalar(select(GenerationJobRecord).where(
                GenerationJobRecord.project_id == project_id, GenerationJobRecord.job_type == "FRAMEWORK"
            ).order_by(GenerationJobRecord.created_at.desc()).limit(1))
            notes = (job.output_snapshot or {}).get("uncertainty_notes", []) if job else []
            text = "# 待用户审核的框架候选（非正式版本）\n\n"
            approval = session.scalar(select(ApprovalRecord).where(
                ApprovalRecord.target_id == working.approved_topic_analysis_id
            ).order_by(ApprovalRecord.created_at.desc()).limit(1))
            if approval and approval.comment.startswith("AUTOMATED_TEST_ONLY"):
                text += "> 题解确认仅为自动流程测试，不代表用户审核；题解和框架均需你复核。\n\n"
            text += "## 背景与人群\n" + topic.content.background + "\n" + topic.content.target_audience + "\n\n"
            text += render_case_markdown(working.case)
            text += "\n## 待核验与自审遗留\n" + "\n".join(f"- {note}" for note in notes)
            return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")

    return demo


app = create_demo_app()
