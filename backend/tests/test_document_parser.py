from __future__ import annotations

import io
from typing import Iterator
import uuid
import zipfile

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.models.document import Document
from backend.app.models.enums import DocumentStatus
from backend.app.models.user import User
from backend.app.services.document_parser.parser import (
    dehyphenate_text,
    normalize_text,
    parse_docx,
    parse_document,
    parse_pdf,
    strip_abstract_front_matter,
)
from backend.app.services.document_parser.service import process_document_parsing
from backend.app.services.document_storage.storage_service import StorageBackend


class MockStorageBackend(StorageBackend):
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> str:
        self.files[key] = data
        return key

    def read(self, key: str) -> bytes:
        if key not in self.files:
            raise FileNotFoundError(f"File {key} not found")
        return self.files[key]

    def delete(self, key: str) -> None:
        self.files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.files

    def get_path(self, key: str) -> str:
        return f"/mock/{key}"


@pytest.fixture
def parser_db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(conn, _rec):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        yield session

    engine.dispose()


def test_parse_pdf_minimal():
    sample_text = b"%PDF-1.4\nAcademic paper text on verification.\n%%EOF"
    doc = parse_pdf(sample_text)
    assert doc.metadata["format"] == "pdf"
    assert len(doc.pages) >= 1
    assert "Academic" in doc.full_text


def test_parse_docx_structure():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>Introduction</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Deep learning models achieved 95% accuracy in claim extraction.</w:t></w:r></w:p>"
            "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>"
            "<w:p><w:r><w:t>References</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>[1] Smith, J. (2021). Verification. Journal of AI, 12, 100-110.</w:t></w:r></w:p>"
            "</w:body>"
            "</w:document>",
        )
    docx_bytes = buf.getvalue()
    parsed = parse_docx(docx_bytes)

    assert parsed.metadata["format"] == "docx"
    assert len(parsed.pages) >= 2
    assert "Introduction" in parsed.pages[0].text
    assert parsed.bibliography_text != ""


def test_process_document_parsing_service(parser_db_session: Session):
    storage = MockStorageBackend()
    user = User(
        email="researcher@anvexa.ai",
        full_name="Dr. Jane Doe",
        hashed_password="pw",
    )
    parser_db_session.add(user)
    parser_db_session.flush()

    raw_content = b"%PDF-1.4\nSection 1. Introduction.\nResults showed a 40% reduction in errors.\n%%EOF"
    storage_key = "test_doc.pdf"
    storage.save(storage_key, raw_content)

    doc = Document(
        user_id=user.id,
        title="Test Document",
        filename="test_doc.pdf",
        storage_path=storage_key,
        file_hash="a" * 64,
        file_type="application/pdf",
        file_size=len(raw_content),
        processing_status=DocumentStatus.UPLOADED,
    )
    parser_db_session.add(doc)
    parser_db_session.commit()

    version, pages = process_document_parsing(doc.id, parser_db_session, storage=storage)
    assert version.document_id == doc.id
    assert len(pages) >= 1
    assert "Section 1" in pages[0].extracted_text


def test_dehyphenate_text_preserves_compound_words():
    raw_text = (
        "Models were evaluated on down- stream tasks to test their knowl- edge. "
        "The state-of-the-art pre-trained architecture achieved 98.5% accuracy."
    )
    cleaned = dehyphenate_text(raw_text)
    assert "downstream" in cleaned
    assert "knowledge" in cleaned
    assert "down- stream" not in cleaned
    assert "knowl- edge" not in cleaned
    # Ensure legitimate hyphenated compound words stay intact
    assert "state-of-the-art" in cleaned
    assert "pre-trained" in cleaned


def test_strip_abstract_front_matter_in_parser():
    header_text = (
        "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks "
        "Patrick Lewis†‡, Ethan Perez⋆, plewis@fb.com Abstract "
        "Large pre-trained language models have been shown to store factual knowledge."
    )
    stripped = strip_abstract_front_matter(header_text)
    assert stripped.startswith("Large pre-trained language models")
    assert "Patrick Lewis" not in stripped
    assert "plewis@fb.com" not in stripped
    assert "Abstract" not in stripped
