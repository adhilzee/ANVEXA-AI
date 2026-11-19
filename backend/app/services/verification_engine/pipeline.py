from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models.document import Document, DocumentVersion
from backend.app.models.enums import DocumentStatus, ProcessingJobType, ProcessingStatus
from backend.app.models.verification import ProcessingJob
from backend.app.services.citation_detector.service import (
    link_claims_to_citations,
    process_citation_detection,
)
from backend.app.services.claim_extractor.service import process_claim_extraction
from backend.app.services.document_parser.service import process_document_parsing
from backend.app.services.document_service import get_storage_backend
from backend.app.services.document_storage.storage_service import StorageBackend
from backend.app.services.evidence_engine.service import process_evidence_chunking
from backend.app.services.source_retriever.service import process_source_retrieval
from backend.app.services.verification_engine.verifier import process_claim_verification

logger = logging.getLogger(__name__)


def create_or_update_job(
    db: Session,
    owner_id: UUID,
    document_id: UUID,
    document_version_id: UUID | None,
    job_type: ProcessingJobType,
    status: ProcessingStatus,
    progress: int,
    error_message: str | None = None,
) -> ProcessingJob:
    """Create or update a ProcessingJob record."""
    job = db.execute(
        select(ProcessingJob).where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.job_type == job_type,
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if job is None:
        job = ProcessingJob(
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            job_type=job_type,
            status=status,
            progress=progress,
            attempt_count=1,
            started_at=now if status == ProcessingStatus.RUNNING else None,
            completed_at=now if status in (ProcessingStatus.COMPLETED, ProcessingStatus.FAILED) else None,
            error_message=error_message,
        )
        db.add(job)
    else:
        job.status = status
        job.progress = progress
        job.document_version_id = document_version_id or job.document_version_id
        if status == ProcessingStatus.RUNNING and not job.started_at:
            job.started_at = now
        if status in (ProcessingStatus.COMPLETED, ProcessingStatus.FAILED):
            job.completed_at = now
        if error_message:
            job.error_message = error_message
        job.attempt_count += 1

    db.flush()
    return job


def run_verification_pipeline(
    document_id: UUID,
    user_id: UUID,
    db: Session,
    storage: StorageBackend | None = None,
    settings: Settings | None = None,
) -> Document:
    """Execute the comprehensive end-to-end academic verification pipeline."""
    if settings is None:
        settings = get_settings()
    if storage is None:
        storage = get_storage_backend(settings)

    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    # Update document status to processing
    doc.processing_status = DocumentStatus.PROCESSING
    db.commit()

    version: DocumentVersion | None = None

    try:
        # Step 1: Parse Document
        create_or_update_job(
            db, user_id, doc.id, None,
            ProcessingJobType.PARSE_DOCUMENT,
            ProcessingStatus.RUNNING, 10
        )
        version, pages = process_document_parsing(doc.id, db, storage, settings)
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.PARSE_DOCUMENT,
            ProcessingStatus.COMPLETED, 100
        )
        db.commit()

        # Step 2: Detect Citations
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.DETECT_CITATIONS,
            ProcessingStatus.RUNNING, 25
        )
        citations = process_citation_detection(version.id, db)
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.DETECT_CITATIONS,
            ProcessingStatus.COMPLETED, 100
        )
        db.commit()

        # Step 3: Extract Claims & Link to Citations
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.EXTRACT_CLAIMS,
            ProcessingStatus.RUNNING, 45
        )
        claims = process_claim_extraction(version.id, db)
        link_claims_to_citations(claims, citations, db)
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.EXTRACT_CLAIMS,
            ProcessingStatus.COMPLETED, 100
        )
        db.commit()

        # Step 4: Retrieve Sources & Reference Issues
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.RETRIEVE_SOURCES,
            ProcessingStatus.RUNNING, 65
        )
        sources, issues = process_source_retrieval(version.id, db)
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.RETRIEVE_SOURCES,
            ProcessingStatus.COMPLETED, 100
        )
        db.commit()

        # Step 5: Process Evidence & Chunking
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.PROCESS_EVIDENCE,
            ProcessingStatus.RUNNING, 80
        )
        passages = process_evidence_chunking(version.id, db)
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.PROCESS_EVIDENCE,
            ProcessingStatus.COMPLETED, 100
        )
        db.commit()

        # Step 6: Verify Claims
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.VERIFY_CLAIMS,
            ProcessingStatus.RUNNING, 90
        )
        results = process_claim_verification(version.id, db)
        create_or_update_job(
            db, user_id, doc.id, version.id,
            ProcessingJobType.VERIFY_CLAIMS,
            ProcessingStatus.COMPLETED, 100
        )

        doc.processing_status = DocumentStatus.COMPLETED
        db.commit()
        logger.info("Pipeline completed successfully for document %s", doc.id)

    except Exception as exc:
        db.rollback()
        logger.exception("Pipeline failed for document %s: %s", doc.id, exc)
        doc.processing_status = DocumentStatus.FAILED
        create_or_update_job(
            db, user_id, doc.id, version.id if version else None,
            ProcessingJobType.VERIFY_CLAIMS,
            ProcessingStatus.FAILED, 0,
            error_message=str(exc)
        )
        db.commit()
        raise

    return doc
