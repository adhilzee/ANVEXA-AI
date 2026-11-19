from __future__ import annotations

import io
from typing import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.models.document import Claim, Document, DocumentVersion
from backend.app.models.enums import ProcessingStatus, ReportFormat, Verdict
from backend.app.models.user import User
from backend.app.models.verification import ReferenceIssue, VerificationResult
from backend.app.services.document_storage.storage_service import StorageBackend
from backend.app.services.report_generator.generator import (
    generate_csv_report_data,
    generate_pdf_report_data,
    generate_verification_report,
    sanitize_pdf_text,
)


class MockStorageBackend(StorageBackend):
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> str:
        self.files[key] = data
        return key

    def read(self, key: str) -> bytes:
        return self.files[key]

    def delete(self, key: str) -> None:
        self.files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.files

    def get_path(self, key: str) -> str:
        return f"/mock/{key}"


@pytest.fixture
def report_db_session() -> Iterator[Session]:
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


def test_generate_csv_and_pdf_reports(report_db_session: Session):
    storage = MockStorageBackend()
    user = User(email="test@anvexa.ai", full_name="User", hashed_password="pw")
    report_db_session.add(user)
    report_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="Audit Paper",
        filename="paper.pdf",
        storage_path="key",
        file_hash="g" * 64,
        file_type="application/pdf",
        file_size=1000,
    )
    report_db_session.add(doc)
    report_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    report_db_session.add(ver)
    report_db_session.flush()

    claim = Claim(
        document_id=doc.id,
        document_version_id=ver.id,
        original_text="Method improved accuracy by 25%.",
    )
    report_db_session.add(claim)
    report_db_session.flush()

    res = VerificationResult(
        claim_id=claim.id,
        document_version_id=ver.id,
        verdict=Verdict.SUPPORTED,
        explanation="Supported by literature.",
        confidence_score=0.92,
        model_provider="ai",
        model_name="test",
    )
    report_db_session.add(res)
    report_db_session.commit()

    # Generate CSV Report
    csv_report = generate_verification_report(
        document_id=doc.id,
        user_id=user.id,
        report_format=ReportFormat.CSV,
        db=report_db_session,
        storage=storage,
    )
    assert csv_report.format == ReportFormat.CSV
    assert csv_report.status == ProcessingStatus.COMPLETED
    assert csv_report.storage_key in storage.files
    csv_data = storage.read(csv_report.storage_key).decode("utf-8")
    assert "Audit Paper" in csv_data
    assert "Method improved accuracy by 25%" in csv_data

    # Generate PDF Report
    pdf_report = generate_verification_report(
        document_id=doc.id,
        user_id=user.id,
        report_format=ReportFormat.PDF,
        db=report_db_session,
        storage=storage,
    )
    assert pdf_report.format == ReportFormat.PDF
    pdf_bytes = storage.read(pdf_report.storage_key)
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_report_layout_wrapping_and_brackets(report_db_session: Session):
    import pypdf
    import io

    # 1. Test math symbol transliteration/sanitization
    math_text = "The objective function satisfies L = ∑ x_i where x ∈ S and tolerance ≤ 0.001."
    sanitized = sanitize_pdf_text(math_text)
    assert "?" not in sanitized
    assert "sum" in sanitized
    assert "in" in sanitized
    assert "<=" in sanitized

    # 2. Test PDF layout, wrapping, and bracket formatting
    storage = MockStorageBackend()
    user = User(email="author@anvexa.ai", full_name="Author", hashed_password="pw")
    report_db_session.add(user)
    report_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="Mathematical Analysis of Optimization",
        filename="math_opt.pdf",
        storage_path="key_math",
        file_hash="m" * 64,
        file_type="application/pdf",
        file_size=2000,
    )
    report_db_session.add(doc)
    report_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    report_db_session.add(ver)
    report_db_session.flush()

    # Long claim text exceeding 90 characters to test text wrapping
    long_claim_text = (
        "The proposed deep neural architecture with multi-head attention achieves state-of-the-art "
        "performance on benchmarks while maintaining computational efficiency where error rate E ≤ 0.05."
    )
    long_explanation = (
        "Fully supported by literature: 3 independent studies confirm the convergence rate and empirical accuracy "
        "across all evaluated datasets with high statistical significance."
    )

    claim = Claim(
        document_id=doc.id,
        document_version_id=ver.id,
        page_number=4,
        original_text=long_claim_text,
    )
    report_db_session.add(claim)
    report_db_session.flush()

    res = VerificationResult(
        claim_id=claim.id,
        document_version_id=ver.id,
        verdict=Verdict.CONTRADICTORY,
        explanation=long_explanation,
        confidence_score=0.88,
        model_provider="ai",
        model_name="test",
    )
    report_db_session.add(res)
    report_db_session.commit()

    pdf_data = generate_pdf_report_data(doc, ver, [claim], {claim.id: res}, [])
    assert pdf_data.startswith(b"%PDF-1.4")

    # Read and parse PDF structure using pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf_data))
    assert len(reader.pages) >= 1
    extracted_text = reader.pages[0].extract_text()

    # Verify bracket formatting has matching square brackets [Page 4]
    assert "[Page 4]" in extracted_text
    assert "CONTRADICTORY" in extracted_text

    # Verify no '?' rendered for math symbols
    assert "?" not in extracted_text

    # Verify text wrapping: text is not truncated with ellipsis '...' at 90 chars
    assert "multi-head attention achieves" in extracted_text
    assert "convergence rate and empirical accuracy" in extracted_text


def test_pdf_report_single_digit_page_bracket_and_evidence_count(report_db_session: Session):
    import pypdf

    user = User(email="author@anvexa.ai", full_name="Author", hashed_password="pw")
    report_db_session.add(user)
    report_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="Sample Paper",
        filename="sample.pdf",
        storage_path="key2",
        file_hash="h" * 64,
        file_type="application/pdf",
        file_size=1200,
    )
    report_db_session.add(doc)
    report_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    report_db_session.add(ver)
    report_db_session.flush()

    # Claim on single-digit page 9
    claim = Claim(
        document_id=doc.id,
        document_version_id=ver.id,
        page_number=9,
        original_text="The speculative approach yielded unverified results on external benchmarks.",
    )
    report_db_session.add(claim)
    report_db_session.flush()

    # Result with 0 supporting, 0 contradicting, 1 neutral
    res = VerificationResult(
        claim_id=claim.id,
        document_version_id=ver.id,
        verdict=Verdict.UNSUPPORTED,
        explanation="No corroborating evidence passages met the relevance threshold.",
        confidence_score=0.50,
        model_provider="ai",
        model_name="test",
    )
    # Mock property counts for testing rendering
    report_db_session.add(res)
    report_db_session.commit()

    pdf_data = generate_pdf_report_data(doc, ver, [claim], {claim.id: res}, [])
    reader = pypdf.PdfReader(io.BytesIO(pdf_data))
    text = reader.pages[0].extract_text()

    # 1. Matching square brackets for single digit [Page 9]
    assert "[Page 9]" in text
    assert "UNSUPPORTED" in text
    assert "[Page 9 UNSUPPORTED" not in text

    # 2. Evidence count explicitly renders '0 contradicting', never omitted
    assert "0 supporting, 0 contradicting, 0 neutral" in text or "0 supporting, 0 contradicting" in text
    assert "0 supporting, contradicting" not in text


def test_pdf_report_page_bracket_standardization():
    from backend.app.services.report_generator.generator import _build_pdf_document
    import pypdf

    # Test that _build_pdf_document standardizes (Page 16 or (Page 16) typos into [Page 16]
    sample_lines = [
        "Claim #1 (Page 16 CONTRADICTORY (Confidence: 85%)",
        "Claim #2 (Page 16) SUPPORTED (Confidence: 92%)",
        "Claim #3 [Page 16] UNSUPPORTED (Confidence: 50%)",
    ]
    pdf_bytes = _build_pdf_document(sample_lines)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    extracted = reader.pages[0].extract_text()

    # All claim headers must have standardized [Page 16] format
    assert "[Page 16]" in extracted
    assert "(Page 16" not in extracted
    assert "(Page 16)" not in extracted
