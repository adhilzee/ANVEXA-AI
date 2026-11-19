from __future__ import annotations

import pytest
from backend.app.models.enums import ConfidenceLabel, EvidenceRelation, Verdict
from backend.app.services.verdict_classifier.classifier import (
    EvidenceEvaluation,
    determine_verdict,
    evaluate_evidence_passage,
)
from backend.app.services.evidence_engine.engine import (
    compute_cosine_similarity,
    compute_pseudo_embedding,
    score_passage_relevance,
)


def test_cosine_similarity_orthogonal_is_zero():
    """Unrelated texts with orthogonal pseudo-embeddings should have zero or near-zero similarity."""
    q = "Deep learning transformers for natural language processing."
    irrel = "Agricultural grain commodity prices during the 19th century industrial revolution."
    
    vq = compute_pseudo_embedding(q)
    vi = compute_pseudo_embedding(irrel)
    sim = compute_cosine_similarity(vq, vi)
    
    # Cosine similarity must not be artificially elevated to 0.50
    assert sim < 0.20
    score = score_passage_relevance(q, irrel)
    assert score < 0.20


def test_moderate_confidence_never_says_fully_supported():
    """Claims with 60-79% confidence must not say 'Fully supported'."""
    evals = [
        EvidenceEvaluation(
            passage_id="pass-1",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.52,
            rationale="Contextual thematic alignment",
        ),
        EvidenceEvaluation(
            passage_id="pass-2",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.48,
            rationale="Corroborating finding",
        ),
    ]
    decision = determine_verdict("Claim with moderate empirical corroboration", evals)
    
    # Confidence should be medium (around 60-70%)
    assert 0.55 <= decision.confidence_score < 0.80
    assert decision.confidence_label == ConfidenceLabel.MEDIUM
    assert decision.verdict == Verdict.SUPPORTED
    
    # Crucial assertion: Must NOT claim 'Fully supported'
    assert "Fully supported" not in decision.explanation
    assert "moderate confidence" in decision.explanation
    assert f"{decision.confidence_score * 100:.0f}%" in decision.explanation


def test_high_confidence_uses_fully_supported():
    """High-confidence claims (>= 80%) with strong corroborating evidence may say 'Fully supported'."""
    evals = [
        EvidenceEvaluation(
            passage_id="pass-1",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.88,
            rationale="High empirical match",
            source_id="src-1",
        ),
        EvidenceEvaluation(
            passage_id="pass-2",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.82,
            rationale="Direct corroboration",
            source_id="src-2",
        ),
    ]
    decision = determine_verdict("Strong claim with robust empirical backing", evals)
    
    assert decision.confidence_score >= 0.80
    assert decision.confidence_label == ConfidenceLabel.HIGH
    assert decision.verdict == Verdict.SUPPORTED
    assert "Fully supported" in decision.explanation
    assert "2 independent sources" in decision.explanation
    assert decision.supporting_count == 2
    assert decision.contradicting_count == 0
    assert decision.neutral_count == 0
    assert decision.retrieved_count == 2


def test_independent_sources_vs_same_source():
    """Passages from the same source must NOT be described as independent sources."""
    evals = [
        EvidenceEvaluation(
            passage_id="pass-1",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.88,
            rationale="Passage 1",
            source_id="src-same",
        ),
        EvidenceEvaluation(
            passage_id="pass-2",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.85,
            rationale="Passage 2",
            source_id="src-same",
        ),
    ]
    decision = determine_verdict("Claim with multiple passages from one source", evals)
    assert decision.confidence_score >= 0.80
    assert "Fully supported" in decision.explanation
    # Must NOT claim 'independent sources' because both are from src-same
    assert "independent sources" not in decision.explanation
    assert "cited source" in decision.explanation


def test_breakdown_of_supporting_contradicting_neutral():
    """Separately counts supporting, contradicting, and neutral passages."""
    evals = [
        EvidenceEvaluation(
            passage_id="pass-1",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.70,
            rationale="Support",
            source_id="src-1",
        ),
        EvidenceEvaluation(
            passage_id="pass-2",
            relation=EvidenceRelation.CONTRADICTING,
            relevance_score=0.65,
            rationale="Contradiction",
            source_id="src-2",
        ),
        EvidenceEvaluation(
            passage_id="pass-3",
            relation=EvidenceRelation.NEUTRAL,
            relevance_score=0.25,
            rationale="Neutral context",
            source_id="src-3",
        ),
    ]
    decision = determine_verdict("Claim with mixed evidence", evals)
    assert decision.retrieved_count == 3
    assert decision.supporting_count == 1
    assert decision.contradicting_count == 1
    assert decision.neutral_count == 1
    assert decision.verdict == Verdict.CONTRADICTORY


def test_single_evidence_passage_count_in_explanation():
    """When only 1 passage supports, the explanation and verdict reflect 1 passage."""
    evals = [
        EvidenceEvaluation(
            passage_id="pass-single",
            relation=EvidenceRelation.SUPPORTING,
            relevance_score=0.62,
            rationale="Single corroboration",
        ),
    ]
    decision = determine_verdict("Claim with single cited source", evals)
    assert decision.confidence_score < 0.80
    assert "Fully supported" not in decision.explanation
    assert "1 primary cited evidence passage" in decision.explanation


def test_verification_evidence_source_url_resolution():
    """Verify that VerificationEvidence.source_url falls back to paper search URL
    when DOI is broken or missing, and keeps direct DOI when valid.
    """
    from backend.app.models.research import EvidencePassage, ResearchSource
    from backend.app.models.verification import VerificationEvidence

    # 1. Valid DOI source
    src_valid = ResearchSource(
        title="Attention is All You Need",
        doi="10.1038/nature14539",
        source_url="https://doi.org/10.1038/nature14539",
    )
    passage_valid = EvidencePassage(
        passage_text="Attention mechanisms improve performance.",
        source=src_valid,
    )
    ev_valid = VerificationEvidence(evidence_passage=passage_valid)
    assert ev_valid.source_url == "https://doi.org/10.1038/nature14539"
    assert ev_valid.is_search_fallback is False

    # 2. Broken DOI source
    src_broken = ResearchSource(
        title="Nonexistent Citation Entry for Integrity Testing",
        doi="10.9999/broken.doi.never.existed.404",
        source_url="https://doi.org/10.9999/broken.doi.never.existed.404",
    )
    passage_broken = EvidencePassage(
        passage_text="Sample text.",
        source=src_broken,
    )
    ev_broken = VerificationEvidence(evidence_passage=passage_broken)
    assert ("semanticscholar.org" in ev_broken.source_url or "scholar.google.com" in ev_broken.source_url)
    assert "Nonexistent+Citation+Entry" in ev_broken.source_url
    assert ev_broken.is_search_fallback is True

    # 3. Source without DOI or source_url
    src_nodoi = ResearchSource(
        title="Student use patterns for an AI revision assistant",
        doi=None,
        source_url=None,
    )
    passage_nodoi = EvidencePassage(
        passage_text="Student evaluation data.",
        source=src_nodoi,
    )
    ev_nodoi = VerificationEvidence(evidence_passage=passage_nodoi)
    assert ("semanticscholar.org" in ev_nodoi.source_url or "scholar.google.com" in ev_nodoi.source_url)
    assert "Student+use+patterns" in ev_nodoi.source_url
    assert ev_nodoi.is_search_fallback is True
