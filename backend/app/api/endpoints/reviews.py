from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, require_role, verify_resource_ownership
from backend.app.database.session import get_db
from backend.app.models.document import Document
from backend.app.models.enums import UserRole
from backend.app.models.user import User
from backend.app.schemas.review import ReviewCreateRequest, ReviewHistoryResponse
from backend.app.services.human_review.service import (
    list_reviews_for_document,
    submit_human_review,
)

router = APIRouter(tags=["reviews"])


@router.post(
    "/verification-results/{result_id}/review",
    response_model=ReviewHistoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit human review evaluation for verification result (Reviewer/Admin only)",
)
def create_review(
    result_id: UUID,
    request: ReviewCreateRequest,
    current_user: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    review = submit_human_review(result_id, current_user, request, db)
    return review


@router.get(
    "/documents/{document_id}/reviews",
    response_model=list[ReviewHistoryResponse],
    summary="List all review records for a document",
)
def get_document_reviews(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_resource_ownership(doc.user_id, current_user)
    return list_reviews_for_document(document_id, db)
