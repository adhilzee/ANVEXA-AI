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
    source_id: str = ""


@dataclass
class ClaimVerdictDecision:
    verdict: Verdict
    confidence_score: float
    confidence_label: ConfidenceLabel
    explanation: str
    evidence_evaluations: list[EvidenceEvaluation]
    retrieved_count: int = 0
    supporting_count: int = 0
    contradicting_count: int = 0
    neutral_count: int = 0


def evaluate_evidence_passage(
    claim_text: str,
    passage_text: str,
    passage_id: str = "",
    relevance_score: float | None = None,
    source_id: str = "",
) -> EvidenceEvaluation:
    """Evaluate whether an evidence passage supports, contradicts, or is neutral towards a claim."""
    relevance = relevance_score if relevance_score is not None else score_passage_relevance(claim_text, passage_text)

    # Check for direct contradiction keywords
    contradiction_found = any(p.search(passage_text) for p in CONTRADICTION_PATTERNS)
    support_found = any(p.search(passage_text) for p in SUPPORTING_PATTERNS)

    if contradiction_found and relevance >= 0.20:
        relation = EvidenceRelation.CONTRADICTING
        rationale = f"Passage exhibits contradictory assertions or negative findings regarding the claim (relevance: {relevance:.2f})."
    elif support_found and relevance >= 0.30:
        relation = EvidenceRelation.SUPPORTING
        rationale = f"Passage provides corroborating empirical evidence consistent with the claim (relevance: {relevance:.2f})."
    elif relevance >= 0.45:
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
        source_id=source_id,
    )


def determine_verdict(
    claim_text: str,
    evaluations: list[EvidenceEvaluation],
    is_source_retracted: bool = False,
    has_broken_reference: bool = False,
    requires_external_verification: bool = True,
) -> ClaimVerdictDecision:
    """Determine final claim verdict, confidence score, and traceable rationale."""
    from backend.app.services.claim_extractor.extractor import is_first_person_setup, is_speculative_future_work

    if is_source_retracted:
        return ClaimVerdictDecision(
            verdict=Verdict.CONTRADICTORY,
            confidence_score=0.95,
            confidence_label=ConfidenceLabel.HIGH,
            explanation="Claim relies on a formally retracted publication. The asserted scientific premise is invalid.",
            evidence_evaluations=evaluations,
            retrieved_count=len(evaluations),
            supporting_count=0,
            contradicting_count=len(evaluations),
            neutral_count=0,
        )

    if not requires_external_verification or is_first_person_setup(claim_text) or is_speculative_future_work(claim_text):
        # Pure first-person experimental setup sentences and speculative/future-work sentences
        # are author design choices or prospectives excluded from external literature contradiction checks.
        supporting = [e for e in evaluations if e.relation == EvidenceRelation.SUPPORTING]
        neutral = [e for e in evaluations if e.relation in (EvidenceRelation.NEUTRAL, EvidenceRelation.CONTRADICTING)]
        if supporting:
            max_rel = max((e.relevance_score for e in supporting), default=0.7)
            conf_score = min(0.95, round(max_rel + 0.10, 2))
            explanation = "Statement corroborated by cited reference."
        elif is_speculative_future_work(claim_text):
            conf_score = 0.85
            explanation = "Prospective or speculative future-work statement (excluded from external literature contradiction checks)."
        else:
            conf_score = 0.85
            explanation = "Internal author-specified experimental setup / implementation parameter (excluded from external literature contradiction checks)."
        return ClaimVerdictDecision(
            verdict=Verdict.SUPPORTED,
            confidence_score=conf_score,
            confidence_label=ConfidenceLabel.HIGH if conf_score >= 0.80 else ConfidenceLabel.MEDIUM,
            explanation=explanation,
            evidence_evaluations=evaluations,
            retrieved_count=len(evaluations),
            supporting_count=len(supporting),
            contradicting_count=0,
            neutral_count=len(neutral),
        )

    if has_broken_reference and not evaluations:
        return ClaimVerdictDecision(
            verdict=Verdict.UNSUPPORTED,
            confidence_score=0.85,
            confidence_label=ConfidenceLabel.HIGH,
            explanation="Claim references a citation with a broken or non-existent DOI. No supporting academic record exists.",
            evidence_evaluations=evaluations,
            retrieved_count=0,
            supporting_count=0,
            contradicting_count=0,
            neutral_count=0,
        )

    if not evaluations:
        return ClaimVerdictDecision(
            verdict=Verdict.NEEDS_REVIEW,
            confidence_score=0.40,
            confidence_label=ConfidenceLabel.LOW,
            explanation="No external research evidence passages could be retrieved for this claim.",
            evidence_evaluations=[],
            retrieved_count=0,
            supporting_count=0,
            contradicting_count=0,
            neutral_count=0,
        )

    supporting = [e for e in evaluations if e.relation == EvidenceRelation.SUPPORTING]
    contradicting = [e for e in evaluations if e.relation == EvidenceRelation.CONTRADICTING]
    neutral = [e for e in evaluations if e.relation == EvidenceRelation.NEUTRAL]

    distinct_sources = {e.source_id for e in supporting if e.source_id}
    is_independent = len(distinct_sources) >= 2
    if is_independent:
        source_desc = f"{len(supporting)} passages across {len(distinct_sources)} independent sources"
    elif len(distinct_sources) == 1:
        source_desc = f"{len(supporting)} passage(s) from cited source"
    else:
        source_desc = f"{len(supporting)} supporting passage(s)"

    # Compute aggregate confidence based on max relevance
    max_relevance = max((e.relevance_score for e in evaluations), default=0.0)

    if contradicting:
        verdict = Verdict.CONTRADICTORY
        conf_score = min(0.95, round(max_relevance + 0.15, 2))
        explanation = f"Contradictory findings detected in {len(contradicting)} evidence passage(s). The claim's premise conflicts with published literature."
    elif len(supporting) >= 2:
        avg_rel = sum(e.relevance_score for e in supporting) / len(supporting)
        conf_score = min(0.98, round(0.65 * max_relevance + 0.25 * avg_rel + 0.10, 2))

        # Check thresholds for full vs moderate support (strictly require >= 80% for "Fully supported")
        if conf_score >= 0.80 and max_relevance >= 0.65:
            verdict = Verdict.SUPPORTED
            explanation = f"Fully supported by {source_desc} with strong contextual corroboration ({conf_score * 100:.0f}% confidence)."
        elif conf_score >= 0.55:
            verdict = Verdict.SUPPORTED
            explanation = f"Supported with moderate confidence ({conf_score * 100:.0f}%): {source_desc} corroborate the premise, with empirical parameters showing contextual alignment."
        else:
            verdict = Verdict.PARTLY_SUPPORTED
            explanation = f"Partially supported ({conf_score * 100:.0f}% confidence): {source_desc} show thematic overlap, but lack strong empirical corroboration."
    elif len(supporting) == 1:
        conf_score = round(max_relevance, 2)
        if conf_score >= 0.75:
            verdict = Verdict.SUPPORTED
            explanation = f"Supported by primary cited evidence passage with high contextual relevance ({conf_score * 100:.0f}% confidence)."
        elif conf_score >= 0.55:
            verdict = Verdict.SUPPORTED
            explanation = f"Supported with moderate confidence ({conf_score * 100:.0f}%): 1 primary cited evidence passage identified with relevant thematic findings."
        else:
            verdict = Verdict.PARTLY_SUPPORTED
            explanation = f"Partially supported ({conf_score * 100:.0f}% confidence): 1 related evidence passage identified, but specific empirical parameters require manual verification."
    else:
        verdict = Verdict.UNSUPPORTED
        conf_score = 0.50
        if neutral:
            explanation = f"Retrieved literature does not confirm the specific claim assertion ({len(neutral)} neutral contextual passage(s) reviewed)."
        else:
            explanation = "Retrieved literature does not confirm the specific claim assertion. No corroborating evidence passages met the relevance threshold."

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
        retrieved_count=len(evaluations),
        supporting_count=len(supporting),
        contradicting_count=len(contradicting),
        neutral_count=len(neutral),
    )
