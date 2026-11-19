from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.audit import AuditLog
from backend.app.models.enums import ReviewAction, UserRole, Verdict
from backend.app.models.research import EvidencePassage
from backend.app.models.user import User
from backend.app.models.verification import ReviewHistory, VerificationResult
from backend.app.schemas.review import ReviewCreateRequest

logger = logging.getLogger(__name__)


def submit_human_review(
    result_id: UUID,
    reviewer: User,
    request: ReviewCreateRequest,
    db: Session,
) -> ReviewHistory:
    """Submit a reviewer evaluation for a verification result."""
    # Ensure user has reviewer or admin role
    if reviewer.role not in (UserRole.REVIEWER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only reviewers and administrators can submit reviews",
        )

    result = db.get(VerificationResult, result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification result not found",
        )

    # Create ReviewHistory
    review = ReviewHistory(
        verification_result_id=result.id,
        reviewer_id=reviewer.id,
        action=request.action,
        original_ai_verdict=result.verdict,
        human_verdict=request.human_verdict,
        reviewer_comment=request.reviewer_comment,
        is_resolved=request.is_resolved,
    )
    db.add(review)
    db.flush()

    # Link additional evidence passages if supplied
    if request.additional_evidence_passage_ids:
        passages = db.execute(
            select(EvidencePassage).where(
                EvidencePassage.id.in_(request.additional_evidence_passage_ids)
            )
        ).scalars().all()
        review.additional_evidence.extend(passages)

    # If action is CHANGE_VERDICT or ACCEPT_AI, optionally update active result
    if request.action == ReviewAction.CHANGE_VERDICT:
        result.verdict = request.human_verdict

    # Record AuditLog
    audit = AuditLog(
        user_id=reviewer.id,
        action="submit_review",
        resource_type="verification_result",
        resource_id=result.id,
        details={
            "action": request.action.value,
            "original_verdict": review.original_ai_verdict.value,
            "human_verdict": request.human_verdict.value,
            "is_resolved": request.is_resolved,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(review)

    logger.info("Review submitted for result %s by reviewer %s", result.id, reviewer.id)
    return review


def list_reviews_for_document(
    document_id: UUID,
    db: Session,
) -> list[ReviewHistory]:
    """Retrieve all review history records for claims within a document."""
    from backend.app.models.document import Claim
    reviews = db.execute(
        select(ReviewHistory)
        .join(VerificationResult)
        .join(Claim)
        .where(Claim.document_id == document_id)
        .order_by(ReviewHistory.reviewed_at.desc())
    ).scalars().all()
    return list(reviews)
