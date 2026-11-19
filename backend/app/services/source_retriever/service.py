from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.models.document import Citation, DocumentVersion
from backend.app.models.enums import ReferenceIssueType, RetrievalStatus, SourceVersionType
from backend.app.models.research import ResearchSource, SourceVersion
from backend.app.models.verification import ReferenceIssue
from backend.app.services.source_retriever.retriever import (
    audit_citation_for_issues,
    fetch_source_metadata,
)

logger = logging.getLogger(__name__)


def process_source_retrieval(
    document_version_id: UUID,
    db: Session,
) -> tuple[list[ResearchSource], list[ReferenceIssue]]:
    """Retrieve metadata for all citations in the document version and detect reference issues."""
    version = db.execute(
        select(DocumentVersion).where(DocumentVersion.id == document_version_id)
    ).scalar_one_or_none()
    if version is None:
        raise ValueError(f"DocumentVersion {document_version_id} not found")

    citations = db.execute(
        select(Citation).where(Citation.document_version_id == version.id)
    ).scalars().all()

    # Clear previous reference issues for this version
    db.execute(
        delete(ReferenceIssue).where(ReferenceIssue.document_version_id == version.id)
    )
    db.flush()

    retrieved_sources: list[ResearchSource] = []
    created_issues: list[ReferenceIssue] = []
    seen_dois: set[str] = set()
    sources_by_doi: dict[str, ResearchSource] = {}

    for cit in citations:
        raw_doi = cit.doi.strip() if cit.doi else None
        doi_key = raw_doi.lower() if raw_doi else None

        # Check duplicate reference
        if doi_key:
            if doi_key in seen_dois:
                dup_issue = ReferenceIssue(
                    document_version_id=version.id,
                    citation_id=cit.id,
                    issue_type=ReferenceIssueType.DUPLICATE_REFERENCE,
                    certainty=backend.app.models.enums.IssueCertainty.CONFIRMED,
                    description=f"Duplicate reference entry found for DOI: {raw_doi}",
                    details={"doi": raw_doi},
                )
                db.add(dup_issue)
                created_issues.append(dup_issue)
            else:
                seen_dois.add(doi_key)

        # Check existing ResearchSource in memory cache and database (case-insensitive)
        source_rec = None
        if doi_key:
            source_rec = sources_by_doi.get(doi_key)
            if source_rec is None:
                source_rec = db.execute(
                    select(ResearchSource).where(
                        func.lower(ResearchSource.doi) == doi_key
                    )
                ).scalars().first()
            if source_rec is not None:
                sources_by_doi[doi_key] = source_rec
                if source_rec.doi:
                    sources_by_doi[source_rec.doi.strip().lower()] = source_rec

        if source_rec is None:
            source_data = fetch_source_metadata(
                doi=cit.doi,
                citation_title=cit.publication_title,
                authors=cit.authors,
                publication_year=cit.publication_year,
                citation_text=cit.citation_text,
            )

            # Re-check in case metadata resolution normalized to an existing DOI
            clean_meta_doi = source_data.doi.strip().lower() if source_data.doi else None
            if clean_meta_doi:
                source_rec = sources_by_doi.get(clean_meta_doi)
                if source_rec is None:
                    source_rec = db.execute(
                        select(ResearchSource).where(
                            func.lower(ResearchSource.doi) == clean_meta_doi
                        )
                    ).scalars().first()
                if source_rec is not None:
                    sources_by_doi[clean_meta_doi] = source_rec
                    if doi_key:
                        sources_by_doi[doi_key] = source_rec

            if source_rec is None:
                source_rec = ResearchSource(
                    doi=source_data.doi,
                    title=source_data.title,
                    authors=source_data.authors,
                    publication_year=source_data.publication_year,
                    journal=source_data.journal,
                    source_url=source_data.source_url,
                    abstract=source_data.abstract,
                    retrieval_status=source_data.retrieval_status,
                    is_retracted=source_data.is_retracted,
                    metadata_json=source_data.metadata,
                )
                db.add(source_rec)
                db.flush()

                if source_data.doi:
                    sources_by_doi[source_data.doi.strip().lower()] = source_rec
                if doi_key:
                    sources_by_doi[doi_key] = source_rec

                # Create default SourceVersion
                full_text = source_data.full_text or source_data.abstract or ""
                content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
                src_version = SourceVersion(
                    source_id=source_rec.id,
                    version_type=SourceVersionType.PUBLISHED,
                    version_url=source_rec.source_url,
                    content_sha256=content_hash,
                    full_text_available=bool(full_text),
                    metadata_json={"abstract": source_data.abstract, "full_text": full_text},
                )
                db.add(src_version)
                db.flush()
            else:
                from backend.app.services.source_retriever.retriever import RetrievedSourceData
                source_data = RetrievedSourceData(
                    doi=source_rec.doi,
                    title=source_rec.title,
                    authors=source_rec.authors,
                    publication_year=source_rec.publication_year,
                    journal=source_rec.journal,
                    source_url=source_rec.source_url,
                    abstract=source_rec.abstract,
                    retrieval_status=source_rec.retrieval_status,
                    is_retracted=source_rec.is_retracted,
                )
        else:
            from backend.app.services.source_retriever.retriever import RetrievedSourceData
            source_data = RetrievedSourceData(
                doi=source_rec.doi,
                title=source_rec.title,
                authors=source_rec.authors,
                publication_year=source_rec.publication_year,
                journal=source_rec.journal,
                source_url=source_rec.source_url,
                abstract=source_rec.abstract,
                retrieval_status=source_rec.retrieval_status,
                is_retracted=source_rec.is_retracted,
            )

        cit.research_source_id = source_rec.id
        db.add(cit)
        retrieved_sources.append(source_rec)

        # Audit citation for issues
        issues = audit_citation_for_issues(
            citation_text=cit.citation_text,
            cited_year=cit.publication_year,
            cited_doi=cit.doi,
            source=source_data,
        )

        for issue_item in issues:
            issue_rec = ReferenceIssue(
                document_version_id=version.id,
                citation_id=cit.id,
                source_id=source_rec.id,
                issue_type=issue_item.issue_type,
                certainty=issue_item.certainty,
                description=issue_item.description,
                details=issue_item.details,
            )
            db.add(issue_rec)
            created_issues.append(issue_rec)

    db.flush()
    logger.info(
        "Retrieved %d sources and detected %d reference issues for version %s",
        len(retrieved_sources),
        len(created_issues),
        version.id,
    )
    return retrieved_sources, created_issues
