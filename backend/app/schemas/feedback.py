from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreateRequest(BaseModel):
    claim_id: UUID
    verification_result_id: UUID
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    claim_id: UUID
    verification_result_id: UUID
    rating: int
    comment: str | None = None
    created_at: datetime
