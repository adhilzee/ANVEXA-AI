from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.models.document import Citation, Document, DocumentVersion
from backend.app.models.enums import DocumentStatus, ReferenceIssueType
from backend.app.models.user import User
from backend.app.services.source_retriever.retriever import (
    audit_citation_for_issues,
    check_doi_retraction,
    fetch_source_metadata,
    validate_doi_format,
)
from backend.app.services.source_retriever.service import process_source_retrieval


@pytest.fixture
def source_db_session() -> Iterator[Session]:
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


def test_validate_doi_format():
    assert validate_doi_format("10.1038/nature12345") is True
    assert validate_doi_format("10.1016/j.cell.2021.05.001") is True
    assert validate_doi_format("10.1038/nature12345.") is True
    assert validate_doi_format("10.1038/nature12345\n") is True
    assert validate_doi_format("invalid-doi-format") is False
    assert validate_doi_format("http://doi.org") is False
    assert validate_doi_format("10.9999/broken.doi.never.existed.404") is False


def test_fetch_source_metadata_fallback_for_broken_or_missing_doi():
    # Broken DOI should fall back to search URL using title instead of broken doi.org link
    source_broken = fetch_source_metadata("not-a-real-doi", "Nonexistent Citation Paper")
    assert ("semanticscholar.org" in source_broken.source_url or "scholar.google.com" in source_broken.source_url)
    assert "Nonexistent+Citation+Paper" in source_broken.source_url

    # Missing DOI should also fall back to search URL using title
    source_no_doi = fetch_source_metadata(None, "Paper Without DOI")
    assert ("semanticscholar.org" in source_no_doi.source_url or "scholar.google.com" in source_no_doi.source_url)
    assert "Paper+Without+DOI" in source_no_doi.source_url

    # Valid DOI should retain direct doi.org link
    source_valid = fetch_source_metadata("10.1038/nature14539", "Deep Learning")
    assert source_valid.source_url == "https://doi.org/10.1038/nature14539"


def test_check_doi_resolves():
    from backend.app.core.doi_utils import check_doi_resolves
    assert check_doi_resolves("10.1038/nature14539") is True
    assert check_doi_resolves("10.9999/broken.doi.never.existed.404") is False
    assert check_doi_resolves("10.5555/anvexa.demo.001") is False
    assert check_doi_resolves("10.18653/v1/") is False
    assert check_doi_resolves("not-a-real-doi") is False
    assert check_doi_resolves(None) is False


def test_check_doi_retraction():
    retracted_doi = "10.1016/s0140-6736(97)11096-0"
    valid_doi = "10.1038/nature14539"
    assert check_doi_retraction(retracted_doi) is True
    assert check_doi_retraction(valid_doi) is False


def test_audit_citation_for_retraction_issue():
    retracted_doi = "10.1016/s0140-6736(97)11096-0"
    source = fetch_source_metadata(retracted_doi, "Retracted Paper")
    issues = audit_citation_for_issues("Reference text", 1998, retracted_doi, source)
    assert any(i.issue_type == ReferenceIssueType.RETRACTED_SOURCE for i in issues)


def test_audit_citation_for_broken_doi():
    broken_doi = "not-a-real-doi"
    source = fetch_source_metadata(broken_doi, "Broken Source")
    issues = audit_citation_for_issues("Reference text", 2020, broken_doi, source)
    assert any(i.issue_type == ReferenceIssueType.BROKEN_DOI for i in issues)


def test_audit_citation_for_metadata_mismatch():
    valid_doi = "10.1038/nature14539"
    source = fetch_source_metadata(valid_doi, "Deep learning")
    # State conflicting year (e.g. 2005 instead of 2021/2015)
    issues = audit_citation_for_issues("Reference text", 1995, valid_doi, source)
    assert any(i.issue_type == ReferenceIssueType.METADATA_MISMATCH for i in issues)


def test_process_source_retrieval_service(source_db_session: Session):
    user = User(email="test@anvexa.ai", full_name="User", hashed_password="pw")
    source_db_session.add(user)
    source_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="Doc",
        filename="doc.pdf",
        storage_path="key",
        file_hash="d" * 64,
        file_type="application/pdf",
        file_size=1000,
        processing_status=DocumentStatus.VALIDATING,
    )
    source_db_session.add(doc)
    source_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    source_db_session.add(ver)
    source_db_session.flush()

    cit1 = Citation(
        document_id=doc.id,
        document_version_id=ver.id,
        reference_number="1",
        citation_text="Retracted MMR study 10.1016/s0140-6736(97)11096-0",
        doi="10.1016/s0140-6736(97)11096-0",
        publication_title="MMR Study",
    )
    cit2 = Citation(
        document_id=doc.id,
        document_version_id=ver.id,
        reference_number="2",
        citation_text="Valid study 10.1038/nature14539",
        doi="10.1038/nature14539",
        publication_title="Deep Learning",
    )
    source_db_session.add_all([cit1, cit2])
    source_db_session.commit()

    sources, issues = process_source_retrieval(ver.id, source_db_session)
    assert len(sources) == 2
    # Ensure retracted issue was flagged
    assert any(i.issue_type == ReferenceIssueType.RETRACTED_SOURCE for i in issues)
