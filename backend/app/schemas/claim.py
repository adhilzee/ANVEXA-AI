from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import ClaimType, ExtractionStatus


class ClaimCitationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    citation_id: UUID
    citation_text: str
    mapping_method: str = "explicit"
    page_number: int | None = None
    character_offset: int | None = None


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_version_id: UUID
    page_id: UUID | None = None
    page_number: int | None = None
    paragraph_number: int | None = None
    original_text: str
    normalized_text: str | None = None
    context_text: str | None = None
    claim_type: ClaimType
    requires_external_verification: bool
    extraction_method: str | None = None
    extraction_status: ExtractionStatus
    created_at: datetime
    updated_at: datetime


class ClaimDetailResponse(ClaimResponse):
    citation_links: list[ClaimCitationItem] = Field(default_factory=list)


class ClaimListResponse(BaseModel):
    claims: list[ClaimResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class ClaimFilterParams(BaseModel):
    claim_type: ClaimType | None = None
    requires_verification: bool | None = None
    page_number: int | None = None
    search: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)
