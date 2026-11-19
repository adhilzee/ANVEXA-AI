from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import RetrievalStatus, SourceVersionType


class EvidencePassageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    source_version_id: UUID
    passage_index: int
    passage_text: str
    section_name: str | None = None
    page_number: int | None = None
    location: str | None = None
    relevance_score: float | None = None


class SourceVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    version_type: SourceVersionType
    version_url: str | None = None
    published_at: datetime | None = None
    full_text_available: bool


class ResearchSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doi: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    journal: str | None = None
    source_url: str | None = None
    abstract: str | None = None
    retrieval_status: RetrievalStatus
    is_retracted: bool
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
