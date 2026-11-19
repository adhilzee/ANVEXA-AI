from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models.document import Citation, Claim, ClaimCitation, DocumentPage, DocumentVersion
from backend.app.models.enums import CitationStyle
from backend.app.services.citation_detector.detector import (
    ParsedBibliographyEntry,
    detect_in_text_citations,
    parse_bibliography_section,
)

logger = logging.getLogger(__name__)


def process_citation_detection(
    document_version_id: UUID,
    db: Session,
    bibliography_text: str | None = None,
) -> list[Citation]:
    """Detect bibliography entries and persist Citation entities for the document version."""
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

    # If bibliography text is not provided, look in the last few pages or parse from text
    if not bibliography_text:
        combined = "\n\n".join([p.extracted_text for p in pages])
        from backend.app.services.document_parser.parser import _detect_sections
        _, bibliography_text = _detect_sections(combined)

    # If still empty, check last page
    if not bibliography_text and pages:
        bibliography_text = pages[-1].extracted_text

    entries: list[ParsedBibliographyEntry] = parse_bibliography_section(bibliography_text or "")

    # Clear previous citations for this document version
    db.execute(
        delete(Citation).where(Citation.document_version_id == version.id)
    )
    db.flush()

    citations: list[Citation] = []
    for entry in entries:
        cit = Citation(
            document_id=version.document_id,
            document_version_id=version.id,
            reference_number=entry.reference_number,
            citation_type=entry.style,
            citation_text=entry.raw_text,
            publication_title=entry.title,
            authors=entry.authors,
            publication_year=entry.year,
            doi=entry.doi,
            url=entry.url,
            is_bibliography_entry=True,
        )
        db.add(cit)
        citations.append(cit)

    db.flush()
    logger.info("Created %d citations for version %s", len(citations), version.id)
    return citations


def link_claims_to_citations(
    claims: list[Claim],
    citations: list[Citation],
    db: Session,
) -> list[ClaimCitation]:
    """Match in-text citation markers in claims to bibliography citations."""
    links: list[ClaimCitation] = []

    # Map reference numbers to citations
    numeric_map: dict[str, Citation] = {}
    for cit in citations:
        if cit.reference_number:
            numeric_map[str(cit.reference_number)] = cit

    for claim in claims:
        text_to_search = f"{claim.original_text} {claim.context_text or ''}"
        detected = detect_in_text_citations(text_to_search)

        for det in detected:
            if det.citation_type == CitationStyle.NUMERIC:
                for key in det.keys:
                    matched_cit = numeric_map.get(key)
                    if matched_cit:
                        link = ClaimCitation(
                            claim_id=claim.id,
                            citation_id=matched_cit.id,
                            citation_text=det.raw_text,
                            page_number=claim.page_number,
                            character_offset=det.start_char,
                            mapping_method="numeric_bracket",
                        )
                        db.add(link)
                        links.append(link)
            elif det.citation_type == CitationStyle.AUTHOR_YEAR:
                # Match by author name / year
                for cit in citations:
                    if cit.publication_year and str(cit.publication_year) in det.raw_text:
                        for auth in cit.authors:
                            if auth.lower() in det.raw_text.lower():
                                link = ClaimCitation(
                                    claim_id=claim.id,
                                    citation_id=cit.id,
                                    citation_text=det.raw_text,
                                    page_number=claim.page_number,
                                    character_offset=det.start_char,
                                    mapping_method="author_year",
                                )
                                db.add(link)
                                links.append(link)
                                break

    db.flush()
    logger.info("Created %d claim-citation links", len(links))
    return links
