from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import (
    ConfidenceLabel,
    EvidenceRelation,
    ProcessingJobType,
    ProcessingStatus,
    Verdict,
    VerificationStatus,
)
from backend.app.schemas.source import EvidencePassageResponse


class VerificationEvidenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    verification_result_id: UUID
    evidence_passage_id: UUID
    relation: EvidenceRelation
    relevance_score: float | None = None
    rationale: str | None = None
    passage: EvidencePassageResponse | None = None


class VerificationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_id: UUID
    document_version_id: UUID
    verdict: Verdict
    explanation: str
    confidence: ConfidenceLabel | None = None
    confidence_score: float | None = None
    verification_status: VerificationStatus
    model_provider: str
    model_name: str
    model_version: str | None = None
    verified_at: datetime
    evidence: list[VerificationEvidenceItem] = Field(default_factory=list)


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID | None = None
    document_version_id: UUID | None = None
    job_type: ProcessingJobType
    status: ProcessingStatus
    progress: int
    attempt_count: int
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class DocumentVerificationSummary(BaseModel):
    document_id: UUID
    total_claims: int
    verified_claims: int
    pending_claims: int
    verdict_distribution: dict[str, int]
    reference_issues_count: int
    confidence_breakdown: dict[str, int]
    verification_score: float  # e.g. % supported claims
    status: str
