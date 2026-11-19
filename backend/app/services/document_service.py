"""Document management service — upload, list, retrieve, delete operations."""

from __future__ import annotations

import hashlib
import logging
import math
import mimetypes
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from starlette import status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models.audit import UserFeedback
from backend.app.models.document import (
    Claim,
    ClaimCitation,
    Citation,
    Document,
    DocumentPage,
    DocumentVersion,
)
from backend.app.models.enums import DocumentStatus, Verdict
from backend.app.models.research import EvidencePassage, ResearchSource
from backend.app.models.user import User
from backend.app.models.verification import (
    ProcessingJob,
    ReferenceIssue,
    Report,
    ReviewHistory,
    VerificationEvidence,
    VerificationResult,
    review_evidence,
)
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentQueryParams,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    PaginationMeta,
)
from backend.app.services.document_storage.local_storage import LocalStorageBackend
from backend.app.services.document_storage.storage_service import (
    StorageBackend,
    StorageError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File-type magic bytes signatures
# ---------------------------------------------------------------------------

# PDF: starts with %PDF
PDF_MAGIC = b"%PDF"

# DOCX: a ZIP archive starting with PK\x03\x04
ZIP_MAGIC = b"PK\x03\x04"

# Allowed MIME types mapped from extensions
EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_file_extension(filename: str, allowed: list[str]) -> str:
    """Return the lowercased extension if allowed, else raise 422."""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed)}",
        )
    return ext


def validate_file_content(data: bytes, extension: str) -> None:
    """Validate file magic bytes match the claimed extension."""
    if not data:
        raise HTTPException(
            status_code=422,
            detail="Uploaded file is empty",
        )

    if extension == ".pdf":
        if not data[:4].startswith(PDF_MAGIC):
            raise HTTPException(
                status_code=422,
                detail="File content does not match PDF format",
            )
    elif extension == ".docx":
        if not data[:4].startswith(ZIP_MAGIC):
            raise HTTPException(
                status_code=422,
                detail="File content does not match DOCX format",
            )


def validate_file_size(size: int, max_size: int) -> None:
    """Reject files exceeding the configured max size."""
    if size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File size ({size} bytes) exceeds maximum allowed ({max_mb:.0f} MB)",
        )


def compute_sha256(data: bytes) -> str:
    """Return hex-encoded SHA-256 hash of *data*."""
    return hashlib.sha256(data).hexdigest()


def validate_mime_type(filename: str, extension: str) -> str:
    """Determine MIME type from extension; fall back to mapping."""
    guessed, _ = mimetypes.guess_type(filename)
    expected = EXTENSION_MIME_MAP.get(extension)
    return guessed or expected or "application/octet-stream"


# ---------------------------------------------------------------------------
# Storage singleton (lazily initialised)
# ---------------------------------------------------------------------------

_storage_backend: StorageBackend | None = None


def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Return (and cache) the storage backend."""
    global _storage_backend
    if _storage_backend is None:
        if settings is None:
            settings = get_settings()
        _storage_backend = LocalStorageBackend(settings.document_storage_path)
    return _storage_backend


def reset_storage_backend() -> None:
    """Reset cached backend — useful for testing."""
    global _storage_backend
    _storage_backend = None


def set_storage_backend(backend: StorageBackend) -> None:
    """Inject a custom storage backend — useful for testing."""
    global _storage_backend
    _storage_backend = backend


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DuplicateDocumentError(HTTPException):
    """Raised when a file with identical SHA-256 hash already exists for the user."""

    def __init__(self, existing_id: UUID | str, status_value: str = "completed"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate document detected. Existing document ID: {existing_id}",
            headers={
                "X-Existing-Document-Id": str(existing_id),
                "X-Existing-Document-Status": str(status_value),
            },
        )
        self.existing_document_id = str(existing_id)
        self.status = str(status_value)


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


def upload_document(
    file: UploadFile,
    current_user: User,
    db: Session,
    settings: Settings | None = None,
) -> DocumentUploadResponse:
    """Validate, store, and persist an uploaded document."""
    if settings is None:
        settings = get_settings()

    # 1. Read file content
    data = file.file.read()
    file.file.seek(0)

    # 2. Extension validation
    filename = file.filename or "untitled"
    ext = validate_file_extension(filename, settings.allowed_file_extensions)

    # 3. Content validation (magic bytes)
    validate_file_content(data, ext)

    # 4. Size validation
    validate_file_size(len(data), settings.max_upload_size_bytes)

    # 5. Compute SHA-256 hash
    file_hash = compute_sha256(data)

    # 6. Duplicate detection (same user + same hash)
    existing = db.execute(
        select(Document).where(
            Document.user_id == current_user.id,
            Document.file_hash == file_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        status_val = (
            existing.processing_status.value
            if hasattr(existing.processing_status, "value")
            else str(existing.processing_status)
        )
        raise DuplicateDocumentError(
            existing_id=existing.id,
            status_value=status_val,
        )

    # 7. Generate unique storage key
    storage_key = f"{uuid4().hex}{ext}"

    # 8. Store file
    storage = get_storage_backend(settings)
    try:
        storage_path = storage.save(storage_key, data)
    except StorageError as exc:
        logger.error("Storage failure during upload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is temporarily unavailable",
        ) from exc

    # 9. Determine MIME / file_type
    mime = validate_mime_type(filename, ext)

    # 10. Create database record
    now = datetime.now(timezone.utc)
    doc = Document(
        user_id=current_user.id,
        title=os.path.splitext(filename)[0],
        filename=filename,
        storage_path=storage_key,  # Store key, NOT full path
        file_hash=file_hash,
        file_type=mime,
        file_size=len(data),
        processing_status=DocumentStatus.UPLOADED,
        uploaded_at=now,
    )

    try:
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except IntegrityError:
        db.rollback()
        # Clean up stored file
        try:
            storage.delete(storage_key)
        except StorageError:
            pass
        existing_dup = db.execute(
            select(Document).where(
                Document.user_id == current_user.id,
                Document.file_hash == file_hash,
            )
        ).scalar_one_or_none()
        if existing_dup is not None:
            status_val = (
                existing_dup.processing_status.value
                if hasattr(existing_dup.processing_status, "value")
                else str(existing_dup.processing_status)
            )
            raise DuplicateDocumentError(
                existing_id=existing_dup.id,
                status_value=status_val,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate document detected",
        )
    except Exception:
        db.rollback()
        try:
            storage.delete(storage_key)
        except StorageError:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save document record",
        )

    logger.info(
        "Document uploaded: id=%s user=%s filename=%s",
        doc.id,
        current_user.id,
        filename,
    )

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        file_hash=doc.file_hash,
        processing_status=doc.processing_status,
        status=doc.processing_status.value,
        uploaded_at=doc.uploaded_at,
        message="Document uploaded successfully",
    )


def list_user_documents(
    current_user: User,
    params: DocumentQueryParams,
    db: Session,
) -> DocumentListResponse:
    """Return paginated, filtered, searchable document list for the user sorted newest-first."""
    query = select(Document).where(Document.user_id == current_user.id)

    # Filters
    if params.search:
        query = query.where(Document.filename.ilike(f"%{params.search}%"))
    if params.file_type:
        query = query.where(Document.file_type.ilike(f"%{params.file_type}%"))
    if params.status:
        query = query.where(Document.processing_status == params.status)

    # Count total (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    # Sorting: order by created_at desc (newest-first)
    if params.sort_order == "asc":
        query = query.order_by(Document.created_at.asc(), Document.uploaded_at.asc())
    else:
        query = query.order_by(Document.created_at.desc(), Document.uploaded_at.desc())

    # Pagination
    offset = (params.page - 1) * params.per_page
    query = query.offset(offset).limit(params.per_page)

    documents = list(db.execute(query).scalars().all())
    total_pages = max(1, math.ceil(total / params.per_page))

    # Enrich document records with verification score and total claims
    doc_responses: list[DocumentResponse] = []
    for d in documents:
        claims_count = 0
        score = 0.0
        latest_version = d.versions[-1] if d.versions else None
        if latest_version:
            claims_count = db.execute(
                select(func.count(Claim.id)).where(Claim.document_version_id == latest_version.id)
            ).scalar() or 0

            results = db.execute(
                select(VerificationResult).where(
                    VerificationResult.document_version_id == latest_version.id
                )
            ).scalars().all()

            supported_count = sum(
                1 for r in results if r.verdict in (Verdict.SUPPORTED, Verdict.PARTLY_SUPPORTED)
            )
            score = round((supported_count / claims_count * 100.0), 1) if claims_count > 0 else 0.0

        status_val = (
            d.processing_status.value
            if hasattr(d.processing_status, "value")
            else str(d.processing_status)
        )

        doc_responses.append(
            DocumentResponse(
                id=d.id,
                user_id=d.user_id,
                title=d.title,
                filename=d.filename,
                file_type=d.file_type,
                file_size=d.file_size,
                file_hash=d.file_hash,
                processing_status=d.processing_status,
                status=status_val,
                verification_score=score,
                total_claims=claims_count,
                uploaded_at=d.uploaded_at,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
        )

    return DocumentListResponse(
        documents=doc_responses,
        pagination=PaginationMeta(
            total=total,
            page=params.page,
            per_page=params.per_page,
            total_pages=total_pages,
        ),
    )


def get_user_document(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> DocumentResponse:
    """Retrieve a single document with ownership enforcement and verification metrics."""
    doc = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Ownership check — admins can access any document
    from backend.app.api.dependencies import verify_resource_ownership
    verify_resource_ownership(doc.user_id, current_user)

    claims_count = 0
    score = 0.0
    latest_version = doc.versions[-1] if doc.versions else None
    if latest_version:
        claims_count = db.execute(
            select(func.count(Claim.id)).where(Claim.document_version_id == latest_version.id)
        ).scalar() or 0

        results = db.execute(
            select(VerificationResult).where(
                VerificationResult.document_version_id == latest_version.id
            )
        ).scalars().all()

        supported_count = sum(
            1 for r in results if r.verdict in (Verdict.SUPPORTED, Verdict.PARTLY_SUPPORTED)
        )
        score = round((supported_count / claims_count * 100.0), 1) if claims_count > 0 else 0.0

    status_val = (
        doc.processing_status.value
        if hasattr(doc.processing_status, "value")
        else str(doc.processing_status)
    )

    return DocumentResponse(
        id=doc.id,
        user_id=doc.user_id,
        title=doc.title,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        file_hash=doc.file_hash,
        processing_status=doc.processing_status,
        status=status_val,
        verification_score=score,
        total_claims=claims_count,
        uploaded_at=doc.uploaded_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def get_document_status(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> DocumentStatusResponse:
    """Return lightweight processing status for a document."""
    doc = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    from backend.app.api.dependencies import verify_resource_ownership
    verify_resource_ownership(doc.user_id, current_user)

    return DocumentStatusResponse(
        id=doc.id,
        processing_status=doc.processing_status,
    )


def delete_user_document(
    document_id: UUID,
    current_user: User,
    db: Session,
    settings: Settings | None = None,
) -> dict[str, str]:
    """Delete a document record and its stored file, cleanly cascading all related entities."""
    doc = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    from backend.app.api.dependencies import verify_resource_ownership
    verify_resource_ownership(doc.user_id, current_user)

    storage_key = doc.storage_path

    try:
        # 1. Gather all DocumentVersion IDs for this document
        version_ids = list(
            db.execute(
                select(DocumentVersion.id).where(DocumentVersion.document_id == document_id)
            ).scalars().all()
        )

        # 2. Gather all Claim IDs
        claim_conds = [Claim.document_id == document_id]
        if version_ids:
            claim_conds.append(Claim.document_version_id.in_(version_ids))
        claim_ids = list(
            db.execute(select(Claim.id).where(or_(*claim_conds))).scalars().all()
        )

        # 3. Gather all Citation IDs
        citation_conds = [Citation.document_id == document_id]
        if version_ids:
            citation_conds.append(Citation.document_version_id.in_(version_ids))
        citation_ids = list(
            db.execute(select(Citation.id).where(or_(*citation_conds))).scalars().all()
        )

        # 4. Gather all VerificationResult IDs
        vr_conds = []
        if claim_ids:
            vr_conds.append(VerificationResult.claim_id.in_(claim_ids))
        if version_ids:
            vr_conds.append(VerificationResult.document_version_id.in_(version_ids))
        result_ids = []
        if vr_conds:
            result_ids = list(
                db.execute(select(VerificationResult.id).where(or_(*vr_conds))).scalars().all()
            )

        # 5. Delete UserFeedback (references verification_results.id with RESTRICT and claims.id)
        uf_conds = []
        if result_ids:
            uf_conds.append(UserFeedback.verification_result_id.in_(result_ids))
        if claim_ids:
            uf_conds.append(UserFeedback.claim_id.in_(claim_ids))
        if uf_conds:
            db.execute(delete(UserFeedback).where(or_(*uf_conds)))

        # 6. Delete ReviewHistory and review_evidence
        if result_ids:
            rh_ids = list(
                db.execute(
                    select(ReviewHistory.id).where(
                        ReviewHistory.verification_result_id.in_(result_ids)
                    )
                ).scalars().all()
            )
            if rh_ids:
                db.execute(
                    delete(review_evidence).where(
                        review_evidence.c.review_id.in_(rh_ids)
                    )
                )
                db.execute(delete(ReviewHistory).where(ReviewHistory.id.in_(rh_ids)))

        # 7. Collect EvidencePassage IDs from VerificationEvidence before deletion
        evidence_passage_ids: list[UUID] = []
        if result_ids:
            evidence_passage_ids = list(
                db.execute(
                    select(VerificationEvidence.evidence_passage_id).where(
                        VerificationEvidence.verification_result_id.in_(result_ids)
                    )
                ).scalars().all()
            )
            db.execute(
                delete(VerificationEvidence).where(
                    VerificationEvidence.verification_result_id.in_(result_ids)
                )
            )

        # 8. Delete VerificationResult
        if result_ids:
            db.execute(delete(VerificationResult).where(VerificationResult.id.in_(result_ids)))

        # 9. Delete ReferenceIssue
        if version_ids:
            db.execute(
                delete(ReferenceIssue).where(
                    ReferenceIssue.document_version_id.in_(version_ids)
                )
            )

        # 10. Delete ClaimCitation
        cc_conds = []
        if claim_ids:
            cc_conds.append(ClaimCitation.claim_id.in_(claim_ids))
        if citation_ids:
            cc_conds.append(ClaimCitation.citation_id.in_(citation_ids))
        if cc_conds:
            db.execute(delete(ClaimCitation).where(or_(*cc_conds)))

        # 11. Delete Claim
        if claim_ids:
            db.execute(delete(Claim).where(Claim.id.in_(claim_ids)))

        # 12. Delete Citation and collect research_sources
        source_ids_to_check: list[UUID] = []
        if citation_ids:
            source_ids_to_check = [
                s
                for s in db.execute(
                    select(Citation.research_source_id).where(
                        Citation.id.in_(citation_ids),
                        Citation.research_source_id.isnot(None),
                    )
                ).scalars().all()
                if s is not None
            ]
            db.execute(delete(Citation).where(Citation.id.in_(citation_ids)))

        # 13. Delete DocumentPage
        if version_ids:
            db.execute(
                delete(DocumentPage).where(
                    DocumentPage.document_version_id.in_(version_ids)
                )
            )

        # 14. Delete Report and ProcessingJob
        db.execute(delete(Report).where(Report.document_id == document_id))
        db.execute(delete(ProcessingJob).where(ProcessingJob.document_id == document_id))

        # 15. Delete DocumentVersion
        if version_ids:
            db.execute(delete(DocumentVersion).where(DocumentVersion.document_id == document_id))

        # 16. Clean unused evidence passages and sources
        if evidence_passage_ids:
            used_passages = set(
                db.execute(
                    select(VerificationEvidence.evidence_passage_id).where(
                        VerificationEvidence.evidence_passage_id.in_(evidence_passage_ids)
                    )
                ).scalars().all()
            )
            unused_pids = [p for p in evidence_passage_ids if p not in used_passages]
            if unused_pids:
                db.execute(delete(EvidencePassage).where(EvidencePassage.id.in_(unused_pids)))

        if source_ids_to_check:
            used_sources = set(
                db.execute(
                    select(Citation.research_source_id).where(
                        Citation.research_source_id.in_(source_ids_to_check)
                    )
                ).scalars().all()
            )
            unused_sids = [s for s in source_ids_to_check if s not in used_sources]
            if unused_sids:
                db.execute(delete(ResearchSource).where(ResearchSource.id.in_(unused_sids)))

        # 17. Delete Document record
        db.delete(doc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to delete document %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document record: {str(exc)}",
        ) from exc

    # 18. Delete file (best-effort)
    if settings is None:
        settings = get_settings()
    storage = get_storage_backend(settings)
    try:
        storage.delete(storage_key)
    except StorageError as exc:
        logger.warning("Failed to delete file for document %s: %s", document_id, exc)

    logger.info("Document deleted: id=%s user=%s", document_id, current_user.id)
    return {"message": f"Document {document_id} deleted successfully"}
