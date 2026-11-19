from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import ReviewAction, Verdict


class ReviewCreateRequest(BaseModel):
    action: ReviewAction
    human_verdict: Verdict
    reviewer_comment: str | None = None
    is_resolved: bool = False
    additional_evidence_passage_ids: list[UUID] = Field(default_factory=list)


class ReviewHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    verification_result_id: UUID
    reviewer_id: UUID
    action: ReviewAction
    original_ai_verdict: Verdict
    human_verdict: Verdict
    reviewer_comment: str | None = None
    is_resolved: bool
    reviewed_at: datetime
