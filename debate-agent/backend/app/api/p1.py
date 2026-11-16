"""P1 HTTP handlers; production business routes fail closed without trusted authentication."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.agents.skills import SkillRegistry
from app.core.database import session_factory, session_scope
from app.schemas.api import (
    CreateProject, CreateRevision, DecideTopic, JobAccepted, JobView, ProjectView,
    ReviseTopic, SaveWorkingCopy, StartFramework, StartGeneration,
)
from app.schemas.domain import ArchivedWorkingCopy, CaseRevision, TopicAnalysis, WorkingCopy
from app.services.export import render_revision_markdown
from app.services.mvp import MVPService


def require_actor() -> UUID:
    # Replace only with a verified authentication provider, never a caller-supplied UUID.
    raise HTTPException(status_code=503, detail="AUTH_NOT_CONFIGURED")


router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_actor)])
SKILLS = SkillRegistry(Path(__file__).resolve().parents[2] / "knowledge" / "skills")


def get_service() -> Iterator[MVPService]:
    try:
        factory = session_factory()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="DATABASE_UNAVAILABLE") from None
    with session_scope(factory) as session:
        yield MVPService(session, SKILLS)


@router.post("/projects", response_model=ProjectView, status_code=201)
def create_project(command: CreateProject, actor: UUID = Depends(require_actor),
                   service: MVPService = Depends(get_service)) -> ProjectView:
    return service.create_project(actor, command)


@router.get("/projects/{project_id}", response_model=ProjectView)
def get_project(project_id: UUID, actor: UUID = Depends(require_actor),
                service: MVPService = Depends(get_service)) -> ProjectView:
    return service.get_project(actor, project_id)


@router.post("/projects/{project_id}/topic-analysis-runs", response_model=JobAccepted, status_code=202)
def analyze_topic(project_id: UUID, command: StartGeneration, actor: UUID = Depends(require_actor),
                  service: MVPService = Depends(get_service)) -> JobAccepted:
    return service.start_topic(actor, project_id, command)


@router.get("/projects/{project_id}/topic-analyses/current", response_model=TopicAnalysis)
def current_topic(project_id: UUID, actor: UUID = Depends(require_actor),
                  service: MVPService = Depends(get_service)) -> TopicAnalysis:
    return service.current_topic(actor, project_id)


@router.get("/topic-analyses/{topic_id}", response_model=TopicAnalysis)
def get_topic(topic_id: UUID, actor: UUID = Depends(require_actor),
              service: MVPService = Depends(get_service)) -> TopicAnalysis:
    return service.get_topic(actor, topic_id)


@router.post("/topic-analyses/{topic_id}/revisions", response_model=TopicAnalysis, status_code=201)
def revise_topic(topic_id: UUID, command: ReviseTopic, actor: UUID = Depends(require_actor),
                 service: MVPService = Depends(get_service)) -> TopicAnalysis:
    return service.revise_topic(actor, topic_id, command)


@router.post("/topic-analyses/{topic_id}/approval", response_model=TopicAnalysis)
def decide_topic(topic_id: UUID, command: DecideTopic, actor: UUID = Depends(require_actor),
                 service: MVPService = Depends(get_service)) -> TopicAnalysis:
    return service.decide_topic(actor, topic_id, command)


@router.post("/projects/{project_id}/framework-runs", response_model=JobAccepted, status_code=202)
def build_framework(project_id: UUID, command: StartFramework, actor: UUID = Depends(require_actor),
                    service: MVPService = Depends(get_service)) -> JobAccepted:
    return service.start_framework(actor, project_id, command)


@router.get("/projects/{project_id}/working-copy", response_model=WorkingCopy)
def project_working(project_id: UUID, actor: UUID = Depends(require_actor),
                    service: MVPService = Depends(get_service)) -> WorkingCopy:
    return service.project_working(actor, project_id)


@router.get("/projects/{project_id}/working-copy-archives", response_model=list[ArchivedWorkingCopy])
def list_working_archives(project_id: UUID, limit: int = Query(default=100, ge=1, le=100),
                          offset: int = Query(default=0, ge=0), actor: UUID = Depends(require_actor),
                          service: MVPService = Depends(get_service)) -> list[ArchivedWorkingCopy]:
    return service.list_working_archives(actor, project_id, limit, offset)


@router.get("/cases/{case_id}", response_model=WorkingCopy)
def get_working_copy(case_id: UUID, actor: UUID = Depends(require_actor),
                     service: MVPService = Depends(get_service)) -> WorkingCopy:
    return service.get_working(actor, case_id)


@router.patch("/cases/{case_id}/working-copy", response_model=WorkingCopy)
def save_working_copy(case_id: UUID, command: SaveWorkingCopy, actor: UUID = Depends(require_actor),
                      service: MVPService = Depends(get_service)) -> WorkingCopy:
    return service.save_working(actor, case_id, command)


@router.post("/cases/{case_id}/revisions", response_model=CaseRevision, status_code=201)
def create_revision(case_id: UUID, command: CreateRevision, actor: UUID = Depends(require_actor),
                    service: MVPService = Depends(get_service)) -> CaseRevision:
    return service.create_revision(actor, case_id, command)


@router.get("/case-revisions/{revision_id}", response_model=CaseRevision)
def get_revision(revision_id: UUID, actor: UUID = Depends(require_actor),
                 service: MVPService = Depends(get_service)) -> CaseRevision:
    return service.get_revision(actor, revision_id)


@router.get("/case-revisions/{revision_id}/export")
def export_revision(revision_id: UUID, format: str = "markdown", actor: UUID = Depends(require_actor),
                    service: MVPService = Depends(get_service)) -> PlainTextResponse:
    if format != "markdown":
        raise HTTPException(status_code=422, detail="UNSUPPORTED_EXPORT_FORMAT")
    return PlainTextResponse(render_revision_markdown(service.get_revision(actor, revision_id)),
                             media_type="text/markdown; charset=utf-8")


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: UUID, actor: UUID = Depends(require_actor),
            service: MVPService = Depends(get_service)) -> JobView:
    return service.get_job(actor, job_id)
