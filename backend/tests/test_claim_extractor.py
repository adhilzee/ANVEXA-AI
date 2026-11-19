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
    dehyphenate_text,
    extract_claims_from_paragraph,
    is_first_person_setup,
    is_references_heading,
    is_speculative_future_work,
    is_valid_claim_candidate,
    split_sentences,
    strip_abstract_front_matter,
    strip_section_heading,
    truncate_at_references,
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


def test_extract_claims_dehyphenates_line_breaks():
    paragraph = (
        "Large pre-trained language models store knowl- edge in parameters and "
        "achieve state-of-the-art results when fine-tuned on down- stream NLP tasks."
    )
    claims = extract_claims_from_paragraph(paragraph, page_number=1, paragraph_number=2)
    assert len(claims) >= 1
    claim_text = claims[0].original_text
    # Verify line-wrap words are normalized
    assert "downstream" in claim_text
    assert "knowledge" in claim_text
    assert "down- stream" not in claim_text
    assert "knowl- edge" not in claim_text
    # Verify legitimate hyphenated words stay intact
    assert "state-of-the-art" in claim_text
    assert "pre-trained" in claim_text


def test_extract_claims_strips_front_matter_header_before_abstract():
    raw_opening_block = (
        "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks "
        "Patrick Lewis†‡, Ethan Perez⋆, Aleksandra Piktus†, Fabio Petroni†, Vladimir Karpukhin†, "
        "Naman Goyal†, Heinrich Küttler†, Mike Lewis†, Wen-tau Yih†, Tim Rocktäschel†‡, "
        "Sebastian Riedel†‡, Douwe Kiela† †Facebook AI Research; ‡University College London; "
        "⋆New York University; plewis@fb.com Abstract Large pre-trained language models have been "
        "shown to store factual knowledge in their parameters, and achieve state-of-the-art results "
        "when fine-tuned on down- stream NLP tasks."
    )
    claims = extract_claims_from_paragraph(raw_opening_block, page_number=1, paragraph_number=1)
    assert len(claims) >= 1
    first_claim = claims[0].original_text
    # Ensure title, authors, affiliations, email, and "Abstract" are stripped
    assert first_claim.startswith("Large pre-trained language models")
    assert "Patrick Lewis" not in first_claim
    assert "plewis@fb.com" not in first_claim
    assert "Facebook AI Research" not in first_claim
    assert "Abstract" not in first_claim
    assert "downstream" in first_claim
    assert "state-of-the-art" in first_claim


def test_strip_section_headings_from_claims():
    cases = [
        (
            "2.5 Decoding At test time, RAG-Sequence and RAG-Token require different ways to decode.",
            "At test time, RAG-Sequence and RAG-Token require different ways to decode."
        ),
        (
            "3.1 Open-domain Question Answering Open-domain question answering (QA) is an important application.",
            "Open-domain question answering (QA) is an important application."
        ),
        (
            "1 Introduction Pre-trained neural language models have been shown to store factual knowledge.",
            "Pre-trained neural language models have been shown to store factual knowledge."
        ),
    ]
    for raw, expected in cases:
        assert strip_section_heading(raw) == expected

    # Test integrated in extract_claims_from_paragraph
    paragraph = "2.5 Decoding At test time, RAG-Sequence and RAG-Token require different ways to decode."
    claims = extract_claims_from_paragraph(paragraph, page_number=2, paragraph_number=1)
    assert len(claims) >= 1
    assert not claims[0].original_text.startswith("2.5 Decoding")
    assert claims[0].original_text.startswith("At test time")


def test_first_person_experimental_setup_claims():
    # Experimental setup sentences should be detected as internal setup parameters
    setup_sentences = [
        "We consider k in {5, 10} for retrieval across all tasks.",
        "We use the document encoder from DPR [26].",
        "Following Lewis et al., we use a learning rate of 1e-4.",
        "In our experiments, we train with AdamW optimizer.",
    ]
    for s in setup_sentences:
        assert is_first_person_setup(s) is True
        claim_type, requires_verif = classify_claim_type(s)
        # Excluded from requiring external verification
        assert requires_verif is False

    # Empirical assertion sentences must NOT be flagged as pure setup
    assert is_first_person_setup("Algorithm A outperformed baseline models across all benchmarks.") is False
    assert is_first_person_setup("Exposure to pollutant X causes cellular degradation.") is False

    # Test verdict determination excludes setup sentences from contradiction
    from backend.app.services.verdict_classifier.classifier import determine_verdict, EvidenceEvaluation
    from backend.app.models.enums import EvidenceRelation, Verdict

    eval_contradicting = [
        EvidenceEvaluation(
            passage_id="p1",
            relation=EvidenceRelation.CONTRADICTING,
            relevance_score=0.75,
            rationale="Unrelated paper uses different parameter.",
            source_id="s1",
        )
    ]
    decision = determine_verdict(
        claim_text="We consider k in {5, 10} for retrieval.",
        evaluations=eval_contradicting,
        requires_external_verification=False,
    )
    # Must NOT be marked CONTRADICTORY
    assert decision.verdict == Verdict.SUPPORTED
    assert decision.contradicting_count == 0


def test_strip_unnumbered_title_case_subheadings():
    cases = [
        (
            "General-Purpose Architectures for NLP Much previous work has explored parametric models.",
            "Much previous work has explored parametric models."
        ),
        (
            "Learned Retrieval Pre-trained neural language models store factual knowledge.",
            "Pre-trained neural language models store factual knowledge."
        ),
        (
            "Memory-based Architectures In contrast to parametric models, memory systems store facts.",
            "In contrast to parametric models, memory systems store facts."
        ),
    ]
    for raw, expected in cases:
        assert strip_section_heading(raw) == expected


def test_dehyphenate_preserves_pre_trained():
    # PDF line wraps splitting hyphenated compounds
    text = "Large pre- trained models were evaluated on down- stream benchmarks with state- of- the- art accuracy."
    cleaned = dehyphenate_text(text)
    assert "pre-trained" in cleaned
    assert "pre- trained" not in cleaned
    assert "pretrained" not in cleaned
    assert "state-of-the-art" in cleaned
    assert "downstream" in cleaned


def test_filter_speculative_future_work_sentences():
    speculative_cases = [
        "We leave joint training of the retriever and generator for future work.",
        "Applying retrieval mechanisms is a promising future work.",
        "Such parametric models may work well in other scientific domains.",
        "We speculate that scaling model parameters might perform well on long-form QA.",
    ]
    for s in speculative_cases:
        assert is_speculative_future_work(s) is True
        claim_type, requires_verif = classify_claim_type(s)
        assert requires_verif is False

    # Integrated claim extraction: speculative sentences are filtered out
    paragraph = (
        "Pre-trained neural language models have been shown to store factual knowledge. "
        "We leave joint training of the retriever and generator for future work. "
        "Applying retrieval to dialogue is a promising future work."
    )
    claims = extract_claims_from_paragraph(paragraph, page_number=1, paragraph_number=1)
    # Only empirical factual claim is extracted; future-work sentences are excluded
    assert len(claims) == 1
    assert "store factual knowledge" in claims[0].original_text
    assert not any("future work" in c.original_text for c in claims)
    # Verdict classifier integration: speculative sentence is excluded from external literature contradiction
    from backend.app.services.verdict_classifier.classifier import determine_verdict
    decision = determine_verdict(
        claim_text="We leave joint training for future work.",
        evaluations=[],
        requires_external_verification=False,
    )
    assert "excluded from external literature contradiction checks" in decision.explanation


def test_exclude_references_and_table_blocks_from_claim_extraction():
    # 1. References heading truncation: text after References is discarded
    para_with_ref = (
        "The proposed dual-encoder architecture achieves 88.4% top-1 accuracy on question answering benchmarks.\n\n"
        "References\n"
        "[66] Thomas Wolf, Lysandre Debut, Victor Sanh, Julien Chaumond, Clement Delangue. "
        "HuggingFace's Transformers: State-of-the-art Natural Language Processing. ArXiv, abs/1910.03771, 2019.\n"
        "doi: 10.18653/v1/D19-1253.\n"
        "URL https://github.com/huggingface/transformers."
    )
    claims = extract_claims_from_paragraph(para_with_ref, page_number=5, paragraph_number=2)
    # Only the empirical claim before References is extracted
    assert len(claims) == 1
    assert "88.4% top-1 accuracy" in claims[0].original_text
    assert not any("Thomas Wolf" in c.original_text for c in claims)
    assert not any("10.18653" in c.original_text for c in claims)
    assert not any("abs/1910" in c.original_text for c in claims)

    # 2. Paragraph that starts with References heading
    ref_para = (
        "References\n"
        "[1] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones. "
        "Attention Is All You Need. NeurIPS 2017."
    )
    assert extract_claims_from_paragraph(ref_para, page_number=6, paragraph_number=1) == []

    # 3. Citation lines starting with [number], doi:, or ArXiv are filtered out
    citation_candidates = [
        "[66] Thomas Wolf et al. HuggingFace's Transformers: State-of-the-art NLP library.",
        "ArXiv, abs/1910.03771, 2019. Published in EMNLP System Demonstrations.",
        "doi: 10.18653/v1/D19-1253. Official publication record from ACL Anthology.",
        "URL https://github.com/huggingface/transformers. Open source implementation.",
    ]
    for cit in citation_candidates:
        assert is_valid_claim_candidate(cit) is False

    # 4. Dense tabular/numeric lines (>35% digits/numbers) are filtered out
    table_rows = [
        "Natural Questions 79169 8758 3611 TriviaQA 78785 8837 1109 CuratedTREC 1484 257 694",
        "Layer 1 0.45 0.88 0.12 0.99 Layer 2 0.77 0.65 0.44 0.93 Layer 3 0.82 0.91 0.15 0.89",
    ]
    for row in table_rows:
        assert is_valid_claim_candidate(row) is False

    # Legitimate empirical claims with numbers are NOT filtered
    legitimate_claims = [
        "Algorithm A achieved 94.5% accuracy, outperforming the baseline by 3.2%.",
        "The treatment resulted in a 42.5% reduction in symptoms (p < 0.001).",
    ]
    for legit in legitimate_claims:
        assert is_valid_claim_candidate(legit) is True


def test_process_claim_extraction_stops_at_references(claim_db_session: Session):
    user = User(email="prof@anvexa.ai", full_name="Prof", hashed_password="pw")
    claim_db_session.add(user)
    claim_db_session.flush()

    doc = Document(
        user_id=user.id,
        title="Stop References Paper",
        filename="paper.pdf",
        storage_path="key3",
        file_hash="k" * 64,
        file_type="application/pdf",
        file_size=1500,
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

    # Page 1: Empirical claims
    page1 = DocumentPage(
        document_id=doc.id,
        document_version_id=ver.id,
        page_number=1,
        extracted_text="RAG models achieve 91.2% accuracy on TriviaQA benchmarks.",
        metadata_json={"paragraphs": ["RAG models achieve 91.2% accuracy on TriviaQA benchmarks."]},
    )
    # Page 2: References heading and subsequent bibliography paragraphs
    page2 = DocumentPage(
        document_id=doc.id,
        document_version_id=ver.id,
        page_number=2,
        extracted_text="References\n[1] Lewis et al. Retrieval-Augmented Generation.",
        metadata_json={
            "paragraphs": [
                "References",
                "[1] Patrick Lewis et al. Retrieval-Augmented Generation for NLP Tasks. NeurIPS 2020.",
                "[2] Vladimir Karpukhin et al. Dense Passage Retrieval. EMNLP 2020."
            ]
        },
    )
    claim_db_session.add_all([page1, page2])
    claim_db_session.commit()

    claims = process_claim_extraction(ver.id, claim_db_session)
    # Only Page 1 claim is extracted; Page 2 references are completely excluded
    assert len(claims) == 1
    assert "91.2% accuracy" in claims[0].original_text
    assert claims[0].page_number == 1
    assert not any("Lewis et al" in c.original_text for c in claims)
