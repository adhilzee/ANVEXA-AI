from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, verify_resource_ownership
from backend.app.database.session import get_db
from backend.app.models.document import Claim, Document, DocumentVersion
from backend.app.models.enums import DocumentStatus, Verdict
from backend.app.models.user import User
from backend.app.models.verification import ProcessingJob, ReferenceIssue, VerificationResult
from backend.app.schemas.verification import (
    DocumentVerificationSummary,
    ProcessingJobResponse,
    VerificationResultResponse,
)
from backend.app.services.verification_engine.pipeline import run_verification_pipeline

router = APIRouter(tags=["verification"])


@router.post(
    "/documents/{document_id}/verify",
    response_model=dict[str, str],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger document verification pipeline",
)
def trigger_verification(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger the complete verification pipeline for an uploaded document."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_resource_ownership(doc.user_id, current_user)

    # Run pipeline
    run_verification_pipeline(document_id=doc.id, user_id=current_user.id, db=db)

    return {"message": "Verification pipeline executed successfully", "document_id": str(doc.id)}


@router.get(
    "/documents/{document_id}/verification-summary",
    response_model=DocumentVerificationSummary,
    summary="Get document verification statistics and summary",
)
def get_verification_summary(
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
        return DocumentVerificationSummary(
            document_id=doc.id,
            total_claims=0,
            verified_claims=0,
            pending_claims=0,
            verdict_distribution={},
            reference_issues_count=0,
            confidence_breakdown={},
            verification_score=0.0,
            status=doc.processing_status.value,
        )

    claims = db.execute(
        select(Claim).where(Claim.document_version_id == version.id)
    ).scalars().all()

    results = db.execute(
        select(VerificationResult).where(VerificationResult.document_version_id == version.id)
    ).scalars().all()

    issues_count = len(
        db.execute(
            select(ReferenceIssue).where(ReferenceIssue.document_version_id == version.id)
        ).scalars().all()
    )

    verdict_dist: dict[str, int] = {}
    conf_dist: dict[str, int] = {}
    supported_count = 0

    for r in results:
        v_name = r.verdict.value
        verdict_dist[v_name] = verdict_dist.get(v_name, 0) + 1
        if r.verdict in (Verdict.SUPPORTED, Verdict.PARTLY_SUPPORTED):
            supported_count += 1
        if r.confidence:
            c_name = r.confidence.value
            conf_dist[c_name] = conf_dist.get(c_name, 0) + 1

    total_claims = len(claims)
    verified_claims = len(results)
    score = (supported_count / total_claims * 100.0) if total_claims > 0 else 0.0

    return DocumentVerificationSummary(
        document_id=doc.id,
        total_claims=total_claims,
        verified_claims=verified_claims,
        pending_claims=max(0, total_claims - verified_claims),
        verdict_distribution=verdict_dist,
        reference_issues_count=issues_count,
        confidence_breakdown=conf_dist,
        verification_score=round(score, 1),
        status=doc.processing_status.value,
    )


@router.get(
    "/documents/{document_id}/jobs",
    response_model=list[ProcessingJobResponse],
    summary="List processing jobs and progress for document",
)
def get_document_jobs(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_resource_ownership(doc.user_id, current_user)

    jobs = db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.asc())
    ).scalars().all()

    return list(jobs)


@router.get(
    "/documents/{document_id}/verification-results",
    response_model=list[VerificationResultResponse],
    summary="List verification results for document",
)
def list_verification_results(
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
        return []

    results = db.execute(
        select(VerificationResult)
        .where(VerificationResult.document_version_id == version.id)
        .order_by(VerificationResult.created_at.asc())
    ).scalars().all()

    return list(results)
