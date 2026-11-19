from __future__ import annotations

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, verify_resource_ownership
from backend.app.database.session import get_db
from backend.app.models.document import Claim, ClaimCitation, Document, DocumentVersion
from backend.app.models.enums import ClaimType
from backend.app.models.user import User
from backend.app.schemas.claim import (
    ClaimCitationItem,
    ClaimDetailResponse,
    ClaimListResponse,
    ClaimResponse,
)

router = APIRouter(tags=["claims"])


@router.get(
    "/documents/{document_id}/claims",
    response_model=ClaimListResponse,
    summary="List extracted claims for a document",
)
def list_document_claims(
    document_id: UUID,
    claim_type: ClaimType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_resource_ownership(doc.user_id, current_user)

    query = select(Claim).where(Claim.document_id == document_id)

    if claim_type:
        query = query.where(Claim.claim_type == claim_type)
    if search:
        query = query.where(Claim.original_text.ilike(f"%{search}%"))

    # Count
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0

    query = query.order_by(Claim.page_number.asc(), Claim.paragraph_number.asc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    claims = db.execute(query).scalars().all()
    total_pages = max(1, math.ceil(total / per_page))

    return ClaimListResponse(
        claims=[ClaimResponse.model_validate(c) for c in claims],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get(
    "/claims/{claim_id}",
    response_model=ClaimDetailResponse,
    summary="Get claim details with citation links",
)
def get_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    doc = db.get(Document, claim.document_id)
    if doc:
        verify_resource_ownership(doc.user_id, current_user)

    citation_links = db.execute(
        select(ClaimCitation).where(ClaimCitation.claim_id == claim.id)
    ).scalars().all()

    return ClaimDetailResponse(
        id=claim.id,
        document_id=claim.document_id,
        document_version_id=claim.document_version_id,
        page_id=claim.page_id,
        page_number=claim.page_number,
        paragraph_number=claim.paragraph_number,
        original_text=claim.original_text,
        normalized_text=claim.normalized_text,
        context_text=claim.context_text,
        claim_type=claim.claim_type,
        requires_external_verification=claim.requires_external_verification,
        extraction_method=claim.extraction_method,
        extraction_status=claim.extraction_status,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        citation_links=[ClaimCitationItem.model_validate(cl) for cl in citation_links],
    )
