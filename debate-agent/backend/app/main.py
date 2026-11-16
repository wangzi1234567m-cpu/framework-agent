"""P1 API shell; no route may mutate business state before authentication exists."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.agents.skills import SkillError
from app.api.p1 import router
from app.core.database import database_url
from app.schemas.api import ErrorResponse
from app.services.mvp import BusinessError


app = FastAPI(title="Debate Agent", version="0.1.0")
app.include_router(router)


@app.exception_handler(BusinessError)
async def handle_business_error(request: Request, exc: BusinessError) -> JSONResponse:
    error = ErrorResponse(error_code=exc.code, message="Business precondition was not met", request_id=uuid4())
    return JSONResponse(status_code=exc.status_code, content=error.model_dump(mode="json"))


@app.exception_handler(SkillError)
async def handle_skill_error(request: Request, exc: SkillError) -> JSONResponse:
    error = ErrorResponse(error_code="SKILL_UNAVAILABLE", message="No approved writing skill is available", request_id=uuid4())
    return JSONResponse(status_code=503, content=error.model_dump(mode="json"))


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    error = ErrorResponse(
        error_code=str(exc.detail),
        message="Request could not be completed",
        request_id=uuid4(),
    )
    return JSONResponse(status_code=exc.status_code, content=error.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    error = ErrorResponse(error_code="INVALID_REQUEST", message="Invalid request body or path", request_id=uuid4())
    return JSONResponse(status_code=422, content=error.model_dump(mode="json"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    try:
        engine = create_engine(database_url(), pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except (RuntimeError, SQLAlchemyError, ValueError):
        raise HTTPException(status_code=503, detail="DATABASE_UNAVAILABLE") from None
    return {"status": "ok"}
