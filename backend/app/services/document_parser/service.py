from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models.document import Document, DocumentPage, DocumentVersion
from backend.app.models.enums import DocumentStatus
from backend.app.services.document_parser.parser import ParsedDocument, parse_document
from backend.app.services.document_service import get_storage_backend
from backend.app.services.document_storage.storage_service import StorageBackend

logger = logging.getLogger(__name__)


def process_document_parsing(
    document_id: UUID,
    db: Session,
    storage: StorageBackend | None = None,
    settings: Settings | None = None,
) -> tuple[DocumentVersion, list[DocumentPage]]:
    """Fetch stored document, parse pages, create/update DocumentVersion and DocumentPages."""
    if settings is None:
        settings = get_settings()
    if storage is None:
        storage = get_storage_backend(settings)

    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    # Read bytes from storage backend
    file_bytes = storage.read(doc.storage_path)
    parsed: ParsedDocument = parse_document(file_bytes, doc.filename)

    # Ensure DocumentVersion exists
    version = db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == 1,
        )
    ).scalar_one_or_none()

    if version is None:
        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            storage_key=doc.storage_path,
            content_sha256=doc.file_hash,
        )
        db.add(version)
        db.flush()

    # Clear any previous pages for this version
    db.execute(
        delete(DocumentPage).where(DocumentPage.document_version_id == version.id)
    )
    db.flush()

    # Create DocumentPage entries
    pages: list[DocumentPage] = []
    for p in parsed.pages:
        meta = dict(p.metadata)
        meta["paragraph_count"] = len(p.paragraphs)
        meta["paragraphs"] = p.paragraphs
        page_rec = DocumentPage(
            document_id=doc.id,
            document_version_id=version.id,
            page_number=p.page_number,
            extracted_text=p.text,
            metadata_json=meta,
        )
        db.add(page_rec)
        pages.append(page_rec)

    db.flush()
    logger.info("Parsed %d pages for document %s", len(pages), doc.id)
    return version, pages
