from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.core.embedding import EMBEDDING_DIMENSION
from backend.app.database.base import Base
from backend.app.models.document import Citation, Claim, ClaimCitation, Document, DocumentVersion
from backend.app.models.enums import ClaimType, DocumentStatus, SourceVersionType
from backend.app.models.research import ResearchSource, SourceVersion
from backend.app.models.user import User
from backend.app.services.evidence_engine.engine import (
    chunk_text_into_passages,
    compute_cosine_similarity,
    compute_pseudo_embedding,
    score_passage_relevance,
)
from backend.app.services.evidence_engine.service import (
    process_evidence_chunking,
    retrieve_relevant_passages_for_claim,
)


@pytest.fixture
def evidence_db_session() -> Iterator[Session]:
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


def test_chunk_text_into_passages():
    text = (
        "Sentence one describes the setting. Sentence two presents the hypothesis. "
        "Sentence three details the methodology. Sentence four lists the key findings. "
        "Sentence five summarizes the conclusions."
    )
    passages = chunk_text_into_passages(text, max_words=15, overlap_words=3)
    assert len(passages) >= 2
    assert all(len(p.split()) > 0 for p in passages)


def test_compute_pseudo_embedding_properties():
    vec1 = compute_pseudo_embedding("Academic verification of research claims.")
    vec2 = compute_pseudo_embedding("Academic verification of research claims.")
    vec3 = compute_pseudo_embedding("Totally unrelated culinary recipe for pasta.")

    assert len(vec1) == EMBEDDING_DIMENSION
    assert vec1 == vec2  # Deterministic

    sim_identical = compute_cosine_similarity(vec1, vec2)
    sim_different = compute_cosine_similarity(vec1, vec3)

    assert sim_identical > 0.99
    assert sim_different < sim_identical


def test_score_passage_relevance():
    query = "Deep neural networks achieve high accuracy on image recognition."
    relevant = "Experiments demonstrate that deep neural networks attain 98% accuracy on image recognition benchmarks."
    irrelevant = "The economic impact of agricultural tariffs in the 19th century."

    score_rel = score_passage_relevance(query, relevant)
    score_irrel = score_passage_relevance(query, irrelevant)

    assert score_rel > score_irrel
    assert score_rel > 0.4


def test_process_evidence_chunking_and_retrieval(evidence_db_session: Session):
    user = User(email="test@anvexa.ai", full_name="User", hashed_password="pw")
    evidence_db_session.add(user)
    evidence_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="Doc",
        filename="doc.pdf",
        storage_path="key",
        file_hash="e" * 64,
        file_type="application/pdf",
        file_size=1000,
        processing_status=DocumentStatus.VALIDATING,
    )
    evidence_db_session.add(doc)
    evidence_db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    evidence_db_session.add(ver)
    evidence_db_session.flush()

    src = ResearchSource(
        title="Deep Learning Breakthroughs",
        abstract="Deep neural networks achieved state-of-the-art results on benchmark tasks with 95% accuracy.",
    )
    evidence_db_session.add(src)
    evidence_db_session.flush()

    src_ver = SourceVersion(
        source_id=src.id,
        version_type=SourceVersionType.PUBLISHED,
        content_sha256="hash",
        metadata_json={"abstract": src.abstract},
    )
    evidence_db_session.add(src_ver)
    evidence_db_session.flush()

    cit = Citation(
        document_id=doc.id,
        document_version_id=ver.id,
        research_source_id=src.id,
        citation_text="Deep Learning Breakthroughs",
    )
    evidence_db_session.add(cit)
    evidence_db_session.flush()

    claim = Claim(
        document_id=doc.id,
        document_version_id=ver.id,
        original_text="Deep neural networks achieved 95% accuracy on benchmark tasks.",
        claim_type=ClaimType.NUMERICAL,
        requires_external_verification=True,
    )
    evidence_db_session.add(claim)
    evidence_db_session.flush()

    link = ClaimCitation(
        claim_id=claim.id,
        citation_id=cit.id,
        citation_text="[1]",
    )
    evidence_db_session.add(link)
    evidence_db_session.commit()

    passages = process_evidence_chunking(ver.id, evidence_db_session)
    assert len(passages) >= 1

    retrieved = retrieve_relevant_passages_for_claim(claim, evidence_db_session, top_k=3)
    assert len(retrieved) >= 1
    top_passage, score = retrieved[0]
    assert score > 0.5
    assert "accuracy" in top_passage.passage_text
