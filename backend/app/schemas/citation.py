from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import CitationStyle, IssueCertainty, ReferenceIssueType


class CitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_version_id: UUID
    research_source_id: UUID | None = None
    reference_number: str | None = None
    citation_type: CitationStyle
    citation_text: str
    publication_title: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    doi: str | None = None
    url: str | None = None
    page_number: int | None = None
    is_bibliography_entry: bool
    created_at: datetime
    updated_at: datetime


class CitationListResponse(BaseModel):
    citations: list[CitationResponse]
    total: int


class ReferenceIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_version_id: UUID
    citation_id: UUID | None = None
    source_id: UUID | None = None
    issue_type: ReferenceIssueType
    certainty: IssueCertainty
    description: str
    details: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ReferenceIssueListResponse(BaseModel):
    issues: list[ReferenceIssueResponse]
    total: int
