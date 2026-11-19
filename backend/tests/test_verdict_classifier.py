from __future__ import annotations

import pytest

from backend.app.models.enums import ConfidenceLabel, EvidenceRelation, Verdict
from backend.app.services.verdict_classifier.classifier import (
    EvidenceEvaluation,
    determine_verdict,
    evaluate_evidence_passage,
)


def test_evaluate_evidence_passage_supporting():
    claim = "The treatment improved patient recovery times by 30%."
    passage = "Clinical trial results confirms that the treatment demonstrates significant improvement in recovery times."
    eval_item = evaluate_evidence_passage(claim, passage, "pass-1")
    assert eval_item.relation == EvidenceRelation.SUPPORTING
    assert eval_item.relevance_score > 0.3


def test_evaluate_evidence_passage_contradicting():
    claim = "The treatment improved patient recovery times."
    passage = "Contrary to expectations, the trial failed to find any significant difference in recovery times compared to placebo."
    eval_item = evaluate_evidence_passage(claim, passage, "pass-2")
    assert eval_item.relation == EvidenceRelation.CONTRADICTING


def test_determine_verdict_retracted_source():
    decision = determine_verdict("Some assertion", [], is_source_retracted=True)
    assert decision.verdict == Verdict.CONTRADICTORY
    assert decision.confidence_label == ConfidenceLabel.HIGH
    assert "retracted" in decision.explanation


def test_determine_verdict_broken_reference():
    decision = determine_verdict("Some assertion", [], has_broken_reference=True)
    assert decision.verdict == Verdict.UNSUPPORTED
    assert decision.confidence_label == ConfidenceLabel.HIGH
    assert "broken" in decision.explanation


def test_determine_verdict_supported():
    evals = [
        EvidenceEvaluation(passage_id="1", relation=EvidenceRelation.SUPPORTING, relevance_score=0.85, rationale="Corroborates"),
        EvidenceEvaluation(passage_id="2", relation=EvidenceRelation.SUPPORTING, relevance_score=0.75, rationale="Supports"),
    ]
    decision = determine_verdict("Claim text", evals)
    assert decision.verdict == Verdict.SUPPORTED
    assert decision.confidence_score > 0.8


def test_determine_verdict_contradictory():
    evals = [
        EvidenceEvaluation(passage_id="1", relation=EvidenceRelation.CONTRADICTING, relevance_score=0.80, rationale="Refutes"),
    ]
    decision = determine_verdict("Claim text", evals)
    assert decision.verdict == Verdict.CONTRADICTORY
