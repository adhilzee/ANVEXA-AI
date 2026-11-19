from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.document import Citation, Claim, DocumentVersion
from backend.app.models.research import EvidencePassage, ResearchSource, SourceVersion
from backend.app.services.evidence_engine.engine import (
    chunk_text_into_passages,
    score_passage_relevance,
)

logger = logging.getLogger(__name__)


def process_evidence_chunking(
    document_version_id: UUID,
    db: Session,
) -> list[EvidencePassage]:
    """Chunk all retrieved sources associated with the document into EvidencePassage entities."""
    version = db.execute(
        select(DocumentVersion).where(DocumentVersion.id == document_version_id)
    ).scalar_one_or_none()
    if version is None:
        raise ValueError(f"DocumentVersion {document_version_id} not found")

    # Find all sources linked to citations for this document
    citations = db.execute(
        select(Citation).where(Citation.document_version_id == version.id)
    ).scalars().all()

    source_ids = {c.research_source_id for c in citations if c.research_source_id is not None}
    passages: list[EvidencePassage] = []

    for sid in source_ids:
        src_version = db.execute(
            select(SourceVersion).where(SourceVersion.source_id == sid)
        ).scalars().first()

        if src_version is None:
            continue

        # Check existing passages
        existing = db.execute(
            select(EvidencePassage).where(EvidencePassage.source_version_id == src_version.id)
        ).scalars().all()
        if existing:
            passages.extend(existing)
            continue

        # Get full text or abstract
        full_text = src_version.metadata_json.get("full_text") or src_version.metadata_json.get("abstract") or ""
        chunks = chunk_text_into_passages(full_text)

        for idx, chunk in enumerate(chunks):
            passage = EvidencePassage(
                source_id=sid,
                source_version_id=src_version.id,
                passage_index=idx,
                passage_text=chunk,
                section_name="Abstract/Body",
                page_number=1,
            )
            db.add(passage)
            passages.append(passage)

    db.flush()
    logger.info("Indexed %d evidence passages for version %s", len(passages), version.id)
    return passages


def retrieve_relevant_passages_for_claim(
    claim: Claim,
    db: Session,
    top_k: int = 5,
) -> list[tuple[EvidencePassage, float]]:
    """Retrieve top-K most relevant evidence passages for a specific claim."""
    query_text = f"{claim.original_text} {claim.context_text or ''}"

    # First priority: check evidence passages from cited sources linked to this claim
    from backend.app.models.document import ClaimCitation
    claim_citations = db.execute(
        select(ClaimCitation).where(ClaimCitation.claim_id == claim.id)
    ).scalars().all()

    cited_source_ids = set()
    for cc in claim_citations:
        cit = db.get(Citation, cc.citation_id)
        if cit and cit.research_source_id:
            cited_source_ids.add(cit.research_source_id)

    # Get available passages
    all_passages = db.execute(select(EvidencePassage)).scalars().all()
    if not all_passages:
        return []

    scored_passages: list[tuple[EvidencePassage, float]] = []
    for p in all_passages:
        score = score_passage_relevance(query_text, p.passage_text)
        # Boost passages from the citation linked directly to this claim
        if p.source_id in cited_source_ids:
            score = min(1.0, score + 0.25)
        scored_passages.append((p, score))

    scored_passages.sort(key=lambda x: x[1], reverse=True)
    return scored_passages[:top_k]
