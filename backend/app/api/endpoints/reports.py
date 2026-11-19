from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    oauth2_scheme,
    verify_resource_ownership,
)
from backend.app.core.config import get_settings
from backend.app.core.security import decode_access_token
from backend.app.database.session import get_db
from backend.app.models.document import Document
from backend.app.models.user import User
from backend.app.models.verification import Report
from backend.app.schemas.report import GenerateReportRequest, ReportResponse
from backend.app.services.document_service import get_storage_backend
from backend.app.services.report_generator.generator import generate_verification_report

router = APIRouter(tags=["reports"])


@router.post(
    "/documents/{document_id}/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate verification audit report (PDF or CSV)",
)
def create_report(
    document_id: UUID,
    request: GenerateReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_resource_ownership(doc.user_id, current_user)

    report = generate_verification_report(
        document_id=doc.id,
        user_id=current_user.id,
        report_format=request.format,
        db=db,
    )
    return report


@router.get(
    "/reports/{report_id}",
    response_model=ReportResponse,
    summary="Get report metadata",
)
def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    verify_resource_ownership(report.owner_id, current_user)
    return report


@router.get(
    "/reports/{report_id}/download",
    summary="Download generated report file",
)
def download_report(
    report_id: UUID,
    token: str | None = Query(default=None, description="Optional JWT token in query param"),
    bearer_token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    auth_token = bearer_token or token
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(auth_token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValueError("Missing sub claim")
        current_user = db.get(User, UUID(user_id_str))
        if current_user is None:
            raise ValueError("User not found")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    verify_resource_ownership(report.owner_id, current_user)

    if not report.storage_key:
        raise HTTPException(status_code=400, detail="Report file not ready")

    settings = get_settings()
    storage = get_storage_backend(settings)

    try:
        content = storage.read(report.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Report file not found in storage") from exc

    media_type = "text/csv" if report.format.value == "csv" else "application/pdf"
    filename = f"report_{report.document_id}_{report.id}.{report.format.value}"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
