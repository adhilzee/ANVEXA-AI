from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.models.audit import AuditLog
from backend.app.models.document import Claim, Document, DocumentVersion
from backend.app.models.enums import ReviewAction, UserRole, Verdict
from backend.app.models.user import User
from backend.app.models.verification import ReviewHistory, VerificationResult
from backend.app.schemas.review import ReviewCreateRequest
from backend.app.services.human_review.service import (
    list_reviews_for_document,
    submit_human_review,
)


@pytest.fixture
def review_db_session() -> Iterator[Session]:
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


def test_submit_human_review_and_audit(review_db_session: Session):
    reviewer = User(
        email="reviewer@anvexa.ai",
        full_name="Dr. Expert Reviewer",
        hashed_password="pw",
        role=UserRole.REVIEWER,
    )
    author = User(
        email="author@anvexa.ai",
        full_name="Author",
        hashed_password="pw",
        role=UserRole.USER,
    )
    review_db_session.add_all([reviewer, author])
    review_db_session.flush()

    doc = Document(
        user_id=author.id,
        title="Sample Document",
        filename="sample.pdf",
        storage_path="key",
        file_hash="f" * 64,
        file_type="application/pdf",
        file_size=1000,
    )
    review_db_session.add(doc)
    review_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    review_db_session.add(ver)
    review_db_session.flush()

    claim = Claim(
        document_id=doc.id,
        document_version_id=ver.id,
        original_text="Proposed model achieved 98% accuracy.",
    )
    review_db_session.add(claim)
    review_db_session.flush()

    res = VerificationResult(
        claim_id=claim.id,
        document_version_id=ver.id,
        verdict=Verdict.SUPPORTED,
        explanation="AI verified supported.",
        model_provider="ai",
        model_name="test",
    )
    review_db_session.add(res)
    review_db_session.commit()

    req = ReviewCreateRequest(
        action=ReviewAction.CHANGE_VERDICT,
        human_verdict=Verdict.PARTLY_SUPPORTED,
        reviewer_comment="Accuracy is dataset specific.",
        is_resolved=True,
    )

    review = submit_human_review(res.id, reviewer, req, review_db_session)
    assert review.action == ReviewAction.CHANGE_VERDICT
    assert review.human_verdict == Verdict.PARTLY_SUPPORTED
    assert res.verdict == Verdict.PARTLY_SUPPORTED

    # Check audit log
    audit_entries = review_db_session.query(AuditLog).all()
    assert len(audit_entries) >= 1
    assert audit_entries[0].action == "submit_review"

    # List reviews for document
    reviews_list = list_reviews_for_document(doc.id, review_db_session)
    assert len(reviews_list) == 1
