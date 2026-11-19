from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models.document import Claim, ClaimCitation, Citation, DocumentVersion
from backend.app.models.enums import ReferenceIssueType, Verdict, VerificationStatus
from backend.app.models.research import EvidencePassage, ResearchSource
from backend.app.models.verification import ReferenceIssue, VerificationEvidence, VerificationResult
from backend.app.services.evidence_engine.service import retrieve_relevant_passages_for_claim
from backend.app.services.verdict_classifier.classifier import (
    EvidenceEvaluation,
    determine_verdict,
    evaluate_evidence_passage,
)

logger = logging.getLogger(__name__)


def verify_single_claim(
    claim: Claim,
    db: Session,
) -> VerificationResult:
    """Perform evidence-traceable verification for a single claim and persist result."""
    # Check if cited reference is retracted or broken
    claim_citations = db.execute(
        select(ClaimCitation).where(ClaimCitation.claim_id == claim.id)
    ).scalars().all()

    is_retracted = False
    has_broken_ref = False

    for cc in claim_citations:
        cit = db.get(Citation, cc.citation_id)
        if cit:
            # Check reference issues
            issues = db.execute(
                select(ReferenceIssue).where(ReferenceIssue.citation_id == cit.id)
            ).scalars().all()
            for issue in issues:
                if issue.issue_type == ReferenceIssueType.RETRACTED_SOURCE:
                    is_retracted = True
                elif issue.issue_type == ReferenceIssueType.BROKEN_DOI:
                    has_broken_ref = True

    # Retrieve relevant evidence passages
    scored_passages = retrieve_relevant_passages_for_claim(claim, db, top_k=5)

    evaluations: list[EvidenceEvaluation] = []
    passage_map: dict[str, EvidencePassage] = {}

    for passage, rel_score in scored_passages:
        eval_item = evaluate_evidence_passage(
            claim_text=f"{claim.original_text} {claim.context_text or ''}",
            passage_text=passage.passage_text,
            passage_id=str(passage.id),
        )
        evaluations.append(eval_item)
        passage_map[str(passage.id)] = passage

    decision = determine_verdict(
        claim_text=claim.original_text,
        evaluations=evaluations,
        is_source_retracted=is_retracted,
        has_broken_reference=has_broken_ref,
    )

    # Persist VerificationResult
    result = VerificationResult(
        claim_id=claim.id,
        document_version_id=claim.document_version_id,
        verdict=decision.verdict,
        explanation=decision.explanation,
        confidence=decision.confidence_label,
        confidence_score=decision.confidence_score,
        verification_status=VerificationStatus.COMPLETED,
        model_provider="anvexa_ai_engine",
        model_name="hybrid_evidence_classifier",
        model_version="1.0.0",
    )
    db.add(result)
    db.flush()

    # Link VerificationEvidence
    for eval_item in decision.evidence_evaluations:
        passage = passage_map.get(eval_item.passage_id)
        if passage:
            evidence_rec = VerificationEvidence(
                verification_result_id=result.id,
                evidence_passage_id=passage.id,
                relation=eval_item.relation,
                relevance_score=eval_item.relevance_score,
                rationale=eval_item.rationale,
            )
            db.add(evidence_rec)

    db.flush()
    return result


def process_claim_verification(
    document_version_id: UUID,
    db: Session,
) -> list[VerificationResult]:
    """Verify all claims for a given document version."""
    version = db.execute(
        select(DocumentVersion).where(DocumentVersion.id == document_version_id)
    ).scalar_one_or_none()
    if version is None:
        raise ValueError(f"DocumentVersion {document_version_id} not found")

    claims = db.execute(
        select(Claim).where(Claim.document_version_id == version.id)
    ).scalars().all()

    # Clear previous verification results for this document version
    existing_results = db.execute(
        select(VerificationResult).where(VerificationResult.document_version_id == version.id)
    ).scalars().all()
    for res in existing_results:
        db.delete(res)
    db.flush()

    results: list[VerificationResult] = []
    for claim in claims:
        res = verify_single_claim(claim, db)
        results.append(res)

    db.flush()
    logger.info("Generated %d verification results for version %s", len(results), version.id)
    return results
