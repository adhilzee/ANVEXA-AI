from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.models.document import Claim, Document, DocumentPage, DocumentVersion
from backend.app.models.enums import ClaimType, DocumentStatus
from backend.app.models.user import User
from backend.app.services.claim_extractor.extractor import (
    classify_claim_type,
    extract_claims_from_paragraph,
    split_sentences,
)
from backend.app.services.claim_extractor.service import process_claim_extraction


@pytest.fixture
def claim_db_session() -> Iterator[Session]:
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


def test_split_sentences_preserves_academic_abbreviations():
    text = "Smith et al. conducted the trial. The mean score was 8.4 (e.g. higher than baseline). Further tests confirmed this."
    sentences = split_sentences(text)
    assert len(sentences) == 3
    assert "Smith et al. conducted the trial." in sentences[0]


def test_classify_claim_types():
    assert classify_claim_type("The treatment resulted in a 42.5% reduction in symptoms.")[0] == ClaimType.NUMERICAL
    assert classify_claim_type("The correlation was statistically significant with p < 0.001.")[0] == ClaimType.STATISTICAL
    assert classify_claim_type("Algorithm A outperformed baseline models across all benchmarks.")[0] == ClaimType.COMPARATIVE
    assert classify_claim_type("Exposure to pollutant X causes cellular degradation.")[0] == ClaimType.CAUSAL
    assert classify_claim_type("Between 2015 and 2020, incidence rates declined steadily.")[0] == ClaimType.TEMPORAL
    assert classify_claim_type("Our architecture consists of three convolutional layers.")[0] == ClaimType.DESCRIPTIVE


def test_extract_claims_from_paragraph():
    para = (
        "In this study, the experimental vaccine demonstrated 94.1% efficacy against infection. "
        "The difference between groups was statistically significant (p < 0.01). "
        "Table 1 outlines the demographic breakdown."
    )
    claims = extract_claims_from_paragraph(para, page_number=2, paragraph_number=1)
    assert len(claims) == 2
    # Ensure "Table 1 outlines..." was filtered out by skip pattern
    assert all("Table 1" not in c.original_text for c in claims)
    assert claims[0].claim_type == ClaimType.NUMERICAL


def test_process_claim_extraction_service(claim_db_session: Session):
    user = User(email="test@anvexa.ai", full_name="User", hashed_password="pw")
    claim_db_session.add(user)
    claim_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="Paper",
        filename="paper.pdf",
        storage_path="key",
        file_hash="b" * 64,
        file_type="application/pdf",
        file_size=1000,
        processing_status=DocumentStatus.VALIDATING,
    )
    claim_db_session.add(doc)
    claim_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    claim_db_session.add(ver)
    claim_db_session.flush()

    page = DocumentPage(
        document_id=doc.id,
        document_version_id=ver.id,
        page_number=1,
        extracted_text="The proposed method outperformed existing techniques by 18% in precision.",
        metadata_json={
            "paragraphs": [
                "The proposed method outperformed existing techniques by 18% in precision. Results were replicated across three independent trials."
            ]
        },
    )
    claim_db_session.add(page)
    claim_db_session.commit()

    claims = process_claim_extraction(ver.id, claim_db_session)
    assert len(claims) >= 1
    assert claims[0].requires_external_verification is True
    assert claims[0].document_id == doc.id
