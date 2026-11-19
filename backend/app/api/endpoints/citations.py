from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, verify_resource_ownership
from backend.app.database.session import get_db
from backend.app.models.document import Citation, Document, DocumentVersion
from backend.app.models.user import User
from backend.app.models.verification import ReferenceIssue
from backend.app.schemas.citation import (
    CitationListResponse,
    CitationResponse,
    ReferenceIssueListResponse,
    ReferenceIssueResponse,
)

router = APIRouter(tags=["citations"])


@router.get(
    "/documents/{document_id}/citations",
    response_model=CitationListResponse,
    summary="List bibliography citations for a document",
)
def list_document_citations(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_resource_ownership(doc.user_id, current_user)

    citations = db.execute(
        select(Citation)
        .where(Citation.document_id == document_id)
        .order_by(Citation.created_at.asc())
    ).scalars().all()

    return CitationListResponse(
        citations=[CitationResponse.model_validate(c) for c in citations],
        total=len(citations),
    )


@router.get(
    "/documents/{document_id}/reference-issues",
    response_model=ReferenceIssueListResponse,
    summary="List detected reference issues (retractions, broken DOIs, etc.)",
)
def list_document_reference_issues(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_resource_ownership(doc.user_id, current_user)

    version = db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == 1,
        )
    ).scalar_one_or_none()

    if version is None:
        return ReferenceIssueListResponse(issues=[], total=0)

    issues = db.execute(
        select(ReferenceIssue)
        .where(ReferenceIssue.document_version_id == version.id)
        .order_by(ReferenceIssue.created_at.asc())
    ).scalars().all()

    return ReferenceIssueListResponse(
        issues=[ReferenceIssueResponse.model_validate(i) for i in issues],
        total=len(issues),
    )
