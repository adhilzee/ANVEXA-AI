from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.models.document import Claim, Document, DocumentPage, DocumentVersion
from backend.app.models.enums import CitationStyle, ClaimType, DocumentStatus
from backend.app.models.user import User
from backend.app.services.citation_detector.detector import (
    detect_in_text_citations,
    extract_doi,
    extract_year,
    parse_bibliography_entry,
    parse_bibliography_section,
    parse_numeric_keys,
)
from backend.app.services.citation_detector.service import (
    link_claims_to_citations,
    process_citation_detection,
)


@pytest.fixture
def citation_db_session() -> Iterator[Session]:
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


def test_parse_numeric_keys():
    assert parse_numeric_keys("1, 3-5, 8") == ["1", "3", "4", "5", "8"]
    assert parse_numeric_keys("12") == ["12"]


def test_detect_in_text_citations():
    text = "Recent studies [1, 2] and later findings [3-5] confirmed this trend. As shown by (Vaswani et al., 2017), attention is all you need."
    detected = detect_in_text_citations(text)
    assert len(detected) == 3

    assert detected[0].citation_type == CitationStyle.NUMERIC
    assert detected[0].keys == ["1", "2"]

    assert detected[1].citation_type == CitationStyle.NUMERIC
    assert detected[1].keys == ["3", "4", "5"]

    assert detected[2].citation_type == CitationStyle.AUTHOR_YEAR
    assert "Vaswani" in detected[2].keys[0]


def test_extract_doi():
    cit = "Vaswani, A. et al. Attention is All You Need. NeurIPS 2017. doi: 10.1000/182"
    assert extract_doi(cit) == "10.1000/182"
    assert extract_doi("No DOI present") is None


def test_parse_bibliography_section():
    bib_text = (
        "[1] LeCun, Y., Bengio, Y., & Hinton, G. Deep learning. Nature, 521(7553), 436-444, 2015. https://doi.org/10.1038/nature14539\n"
        "[2] Vaswani, A. et al. Attention is all you need. Advances in Neural Information Processing Systems, 2017.\n"
    )
    entries = parse_bibliography_section(bib_text)
    assert len(entries) == 2
    assert entries[0].reference_number == "1"
    assert entries[0].year == 2015
    assert entries[0].doi == "10.1038/nature14539"
    assert entries[1].reference_number == "2"


def test_process_and_link_citations_service(citation_db_session: Session):
    user = User(email="author@anvexa.ai", full_name="Author", hashed_password="pw")
    citation_db_session.add(user)
    citation_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="AI Paper",
        filename="paper.pdf",
        storage_path="key",
        file_hash="c" * 64,
        file_type="application/pdf",
        file_size=1000,
        processing_status=DocumentStatus.VALIDATING,
    )
    citation_db_session.add(doc)
    citation_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    citation_db_session.add(ver)
    citation_db_session.flush()

    bib = (
        "[1] Smith, A. (2020). Large Scale Evidence Verification. 10.1016/j.ai.2020.01\n"
        "[2] Jones, B. (2019). Semantic Verification. 10.1016/j.ai.2019.05\n"
    )

    page = DocumentPage(
        document_id=doc.id,
        document_version_id=ver.id,
        page_number=1,
        extracted_text="Previous methods achieved 80% accuracy [1].",
        metadata_json={},
    )
    citation_db_session.add(page)
    citation_db_session.flush()

    claim = Claim(
        document_id=doc.id,
        document_version_id=ver.id,
        page_id=page.id,
        page_number=1,
        paragraph_number=1,
        original_text="Previous methods achieved 80% accuracy [1].",
        claim_type=ClaimType.NUMERICAL,
        requires_external_verification=True,
    )
    citation_db_session.add(claim)
    citation_db_session.commit()

    citations = process_citation_detection(ver.id, citation_db_session, bibliography_text=bib)
    assert len(citations) == 2

    links = link_claims_to_citations([claim], citations, citation_db_session)
    assert len(links) == 1
    assert links[0].claim_id == claim.id
    assert links[0].citation_id == citations[0].id
