from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.database.session import get_db
from backend.app.models.audit import UserFeedback
from backend.app.models.document import Claim
from backend.app.models.user import User
from backend.app.models.verification import VerificationResult
from backend.app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse

router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit user feedback on verification result",
)
def submit_feedback(
    request: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    claim = db.get(Claim, request.claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    result = db.get(VerificationResult, request.verification_result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Verification result not found")

    fb = UserFeedback(
        user_id=current_user.id,
        claim_id=claim.id,
        verification_result_id=result.id,
        rating=request.rating,
        comment=request.comment,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    return fb


@router.get(
    "/claims/{claim_id}/feedback",
    response_model=list[FeedbackResponse],
    summary="List feedback for a claim",
)
def get_claim_feedback(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    feedback_items = db.execute(
        select(UserFeedback)
        .where(UserFeedback.claim_id == claim_id)
        .order_by(UserFeedback.created_at.desc())
    ).scalars().all()

    return list(feedback_items)
