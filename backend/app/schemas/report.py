from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.models.enums import ProcessingStatus, ReportFormat


class GenerateReportRequest(BaseModel):
    format: ReportFormat = ReportFormat.PDF


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    document_id: UUID
    document_version_id: UUID
    format: ReportFormat
    status: ProcessingStatus
    storage_key: str | None = None
    error_message: str | None = None
    generated_at: datetime | None = None
    created_at: datetime
