"""Workflow boundaries: leased jobs and transactional candidate acceptance."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.schemas.agent import FrameworkResponse, TopicResponse
class JobStore(Protocol):
    def claim_next(self) -> tuple[UUID, int, dict[str, Any]] | None:
        """Atomically lease a queued job; return job ID, fencing attempt and snapshot."""
        ...


class CandidateSink(Protocol):
    def accept_topic(self, job_id: UUID, worker_id: str, attempt: int, result: TopicResponse) -> UUID:
        """Store a pending version after verifying the latest project state."""
        ...

    def accept_framework(self, job_id: UUID, worker_id: str, attempt: int, result: FrameworkResponse) -> UUID:
        """Verify current approval/edit version, then persist candidate and ref map."""
        ...
