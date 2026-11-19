from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.models.enums import ConfidenceLabel, EvidenceRelation, Verdict
from backend.app.services.evidence_engine.engine import score_passage_relevance

CONTRADICTION_PATTERNS = [
    re.compile(r"\b(?:contrary to|failed to (?:replicate|show|find)|no significant (?:difference|effect|correlation)|did not (?:increase|decrease|improve|observe)|no evidence (?:of|for)|inconsistent with|disproved|refuted)\b", re.IGNORECASE),
    re.compile(r"\b(?:opposite|in contrast|discrepancy|contradict(?:s|ed|ing)?)\b", re.IGNORECASE),
]

SUPPORTING_PATTERNS = [
    re.compile(r"\b(?:consistent with|confirms?|demonstrates?|proves?|supports?|in agreement with|corroborates?|verif(?:y|ies|ied)|statistically significant increase|positive correlation)\b", re.IGNORECASE),
]


@dataclass
class EvidenceEvaluation:
    passage_id: str
    relation: EvidenceRelation
    relevance_score: float
    rationale: str


@dataclass
class ClaimVerdictDecision:
    verdict: Verdict
    confidence_score: float
    confidence_label: ConfidenceLabel
    explanation: str
    evidence_evaluations: list[EvidenceEvaluation]


def evaluate_evidence_passage(
    claim_text: str,
    passage_text: str,
    passage_id: str = "",
) -> EvidenceEvaluation:
    """Evaluate whether an evidence passage supports, contradicts, or is neutral towards a claim."""
    relevance = score_passage_relevance(claim_text, passage_text)

    # Check for direct contradiction keywords
    contradiction_found = any(p.search(passage_text) for p in CONTRADICTION_PATTERNS)
    support_found = any(p.search(passage_text) for p in SUPPORTING_PATTERNS)

    if contradiction_found and relevance > 0.3:
        relation = EvidenceRelation.CONTRADICTING
        rationale = f"Passage exhibits contradictory assertions or negative findings regarding the claim (relevance: {relevance:.2f})."
    elif support_found and relevance > 0.3:
        relation = EvidenceRelation.SUPPORTING
        rationale = f"Passage provides corroborating empirical evidence consistent with the claim (relevance: {relevance:.2f})."
    elif relevance > 0.45:
        relation = EvidenceRelation.SUPPORTING
        rationale = f"Substantive thematic and contextual overlap supporting the claim proposition (relevance: {relevance:.2f})."
    else:
        relation = EvidenceRelation.NEUTRAL
        rationale = f"Passage provides general context but insufficient direct evidence (relevance: {relevance:.2f})."

    return EvidenceEvaluation(
        passage_id=passage_id,
        relation=relation,
        relevance_score=relevance,
        rationale=rationale,
    )


def determine_verdict(
    claim_text: str,
    evaluations: list[EvidenceEvaluation],
    is_source_retracted: bool = False,
    has_broken_reference: bool = False,
) -> ClaimVerdictDecision:
    """Determine final claim verdict, confidence score, and traceable rationale."""
    if is_source_retracted:
        return ClaimVerdictDecision(
            verdict=Verdict.CONTRADICTORY,
            confidence_score=0.95,
            confidence_label=ConfidenceLabel.HIGH,
            explanation="Claim relies on a formally retracted publication. The asserted scientific premise is invalid.",
            evidence_evaluations=evaluations,
        )

    if has_broken_reference and not evaluations:
        return ClaimVerdictDecision(
            verdict=Verdict.UNSUPPORTED,
            confidence_score=0.85,
            confidence_label=ConfidenceLabel.HIGH,
            explanation="Claim references a citation with a broken or non-existent DOI. No supporting academic record exists.",
            evidence_evaluations=evaluations,
        )

    if not evaluations:
        return ClaimVerdictDecision(
            verdict=Verdict.NEEDS_REVIEW,
            confidence_score=0.40,
            confidence_label=ConfidenceLabel.LOW,
            explanation="No external research evidence passages could be retrieved for this claim.",
            evidence_evaluations=[],
        )

    supporting = [e for e in evaluations if e.relation == EvidenceRelation.SUPPORTING]
    contradicting = [e for e in evaluations if e.relation == EvidenceRelation.CONTRADICTING]

    # Compute aggregate confidence based on max relevance
    max_relevance = max((e.relevance_score for e in evaluations), default=0.0)

    if contradicting:
        verdict = Verdict.CONTRADICTORY
        conf_score = min(0.95, max_relevance + 0.15)
        explanation = f"Contradictory findings detected in {len(contradicting)} evidence passage(s). The claim's premise conflicts with published literature."
    elif len(supporting) >= 2:
        verdict = Verdict.SUPPORTED
        conf_score = min(0.98, max_relevance + 0.20)
        explanation = f"Fully supported by {len(supporting)} independent evidence passages with strong contextual corroboration."
    elif len(supporting) == 1:
        if max_relevance > 0.6:
            verdict = Verdict.SUPPORTED
            conf_score = round(max_relevance, 2)
            explanation = "Supported by primary cited evidence passage with high contextual relevance."
        else:
            verdict = Verdict.PARTLY_SUPPORTED
            conf_score = round(max_relevance, 2)
            explanation = "Partially supported: related evidence was identified, but specific empirical parameters require manual verification."
    else:
        verdict = Verdict.UNSUPPORTED
        conf_score = 0.60
        explanation = "Retrieved literature does not confirm the specific claim assertion."

    # Map confidence score to label
    if conf_score >= 0.80:
        conf_label = ConfidenceLabel.HIGH
    elif conf_score >= 0.55:
        conf_label = ConfidenceLabel.MEDIUM
    else:
        conf_label = ConfidenceLabel.LOW

    return ClaimVerdictDecision(
        verdict=verdict,
        confidence_score=conf_score,
        confidence_label=conf_label,
        explanation=explanation,
        evidence_evaluations=evaluations,
    )
