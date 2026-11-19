from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models.document import Claim, DocumentPage, DocumentVersion
from backend.app.models.enums import ExtractionStatus
from backend.app.models.verification import VerificationResult
from backend.app.services.claim_extractor.extractor import (
    ExtractedClaim,
    extract_claims_from_paragraph,
    is_references_heading,
    truncate_at_references,
)

logger = logging.getLogger(__name__)


def process_claim_extraction(
    document_version_id: UUID,
    db: Session,
) -> list[Claim]:
    """Extract claims from all DocumentPages for the specified version and persist them."""
    version = db.execute(
        select(DocumentVersion).where(DocumentVersion.id == document_version_id)
    ).scalar_one_or_none()
    if version is None:
        raise ValueError(f"DocumentVersion {document_version_id} not found")

    pages = db.execute(
        select(DocumentPage)
        .where(DocumentPage.document_version_id == version.id)
        .order_by(DocumentPage.page_number)
    ).scalars().all()

    # Clear previous verification results and claims for this version to avoid orphaned results
    old_results = db.execute(
        select(VerificationResult).where(VerificationResult.document_version_id == version.id)
    ).scalars().all()
    for old_res in old_results:
        db.delete(old_res)
    db.execute(
        delete(Claim).where(Claim.document_version_id == version.id)
    )
    db.flush()

    persisted_claims: list[Claim] = []
    reached_references = False

    for page in pages:
        if reached_references:
            break

        paras = page.metadata_json.get("paragraphs")
        if not paras or not isinstance(paras, list):
            # Fallback to splitting extracted_text
            paras = [p.strip() for p in page.extracted_text.split("\n\n") if p.strip()]

        for para_idx, para in enumerate(paras, start=1):
            if is_references_heading(para):
                reached_references = True
                break

            clean_para, has_ref = truncate_at_references(para)
            if has_ref:
                reached_references = True

            if clean_para:
                extracted: list[ExtractedClaim] = extract_claims_from_paragraph(
                    clean_para,
                    page_number=page.page_number,
                    paragraph_number=para_idx,
                )

                for item in extracted:
                    claim = Claim(
                        document_id=version.document_id,
                        document_version_id=version.id,
                        page_id=page.id,
                        page_number=item.page_number,
                        paragraph_number=item.paragraph_number,
                        original_text=item.original_text,
                        normalized_text=item.normalized_text,
                        context_text=item.context_text,
                        claim_type=item.claim_type,
                        requires_external_verification=item.requires_external_verification,
                        extraction_method=item.extraction_method,
                        extraction_status=ExtractionStatus.COMPLETED,
                    )
                    db.add(claim)
                    persisted_claims.append(claim)

            if reached_references:
                break

    db.flush()
    logger.info("Extracted %d claims for version %s", len(persisted_claims), version.id)
    return persisted_claims
