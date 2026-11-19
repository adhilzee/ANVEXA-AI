from __future__ import annotations

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
