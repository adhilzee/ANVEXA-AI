from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.models.enums import ClaimType

NUMERICAL_REGEX = re.compile(
    r"\b(?:\d+(?:\.\d+)?%|\d+\.\d+|\b\d{2,}\b|p\s*[<=]\s*0?\.\d+|CI\b|\b\d+\s*(?:mg|ml|kg|km|meters|hours|days|years|samples|participants)\b)",
    re.IGNORECASE,
)

STATISTICAL_REGEX = re.compile(
    r"\b(?:statistically\s+significant|p-value|confidence\s+interval|standard\s+deviation|mean\s*[=±]|median|t-test|anova|chi-square|correlation|regression\s+coefficient|odds\s+ratio|hazard\s+ratio|r\s*=\s*0?\.\d+)\b",
    re.IGNORECASE,
)

COMPARATIVE_REGEX = re.compile(
    r"\b(?:outperformed|higher\s+than|lower\s+than|greater\s+than|less\s+than|superior\s+to|inferior\s+to|doubled|tripled|reduced\s+by|increased\s+by|decreased\s+by|more\s+effective|faster\s+than)\b",
    re.IGNORECASE,
)

CAUSAL_REGEX = re.compile(
    r"\b(?:causes?|caused|causing|leads?\s+to|led\s+to|results?\s+in|resulted\s+in|induces?|induced|triggers?|triggered|contributes?\s+to|produces?|prevented|prevents?)\b",
    re.IGNORECASE,
)

TEMPORAL_REGEX = re.compile(
    r"\b(?:between\s+\d{4}\s+and\s+\d{4}|from\s+\d{4}\s+to\s+\d{4}|during\s+the\s+period|over\s+a\s+\d+[- ](?:year|month|day)\s+period|in\s+(?:19\d{2}|20\d{2})|since\s+\d{4})\b",
    re.IGNORECASE,
)

SKIP_PATTERNS = [
    re.compile(r"^table\s+\d+", re.IGNORECASE),
    re.compile(r"^figure\s+\d+", re.IGNORECASE),
    re.compile(r"^fig\.\s*\d+", re.IGNORECASE),
    re.compile(r"the\s+rest\s+of\s+this\s+paper\s+is\s+organized", re.IGNORECASE),
    re.compile(r"section\s+\d+\s+describes", re.IGNORECASE),
    re.compile(r"in\s+section\s+\d+", re.IGNORECASE),
]


@dataclass
class ExtractedClaim:
    original_text: str
    normalized_text: str
    context_text: str
    claim_type: ClaimType
    requires_external_verification: bool
    page_number: int
    paragraph_number: int
    extraction_method: str = "rule_based_nlp"


def split_sentences(text: str) -> list[str]:
    """Split text into sentences while respecting common academic abbreviations (e.g., et al., i.e., e.g., fig.)."""
    cleaned = text.replace("et al.", "et_al_dot").replace("i.e.", "i_e_dot").replace("e.g.", "e_g_dot").replace("Fig.", "Fig_dot")
    raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    results = []
    for s in raw_sentences:
        restored = s.replace("et_al_dot", "et al.").replace("i_e_dot", "i.e.").replace("e_g_dot", "e.g.").replace("Fig_dot", "Fig.")
        restored = restored.strip()
        if len(restored) > 15:
            results.append(restored)
    return results


def classify_claim_type(sentence: str) -> tuple[ClaimType, bool]:
    """Determine the primary ClaimType and whether external verification is required."""
    is_statistical = bool(STATISTICAL_REGEX.search(sentence))
    is_numerical = bool(NUMERICAL_REGEX.search(sentence))
    is_comparative = bool(COMPARATIVE_REGEX.search(sentence))
    is_causal = bool(CAUSAL_REGEX.search(sentence))
    is_temporal = bool(TEMPORAL_REGEX.search(sentence))

    if is_statistical:
        return ClaimType.STATISTICAL, True
    if is_temporal:
        return ClaimType.TEMPORAL, True
    if is_numerical:
        return ClaimType.NUMERICAL, True
    if is_comparative:
        return ClaimType.COMPARATIVE, True
    if is_causal:
        return ClaimType.CAUSAL, True

    # Check if sentence makes empirical assertion or cites work
    has_citation = bool(re.search(r"\[\d+\]|\([A-Za-z]+.*,\s*\d{4}\)", sentence))
    if has_citation:
        return ClaimType.DESCRIPTIVE, True

    # Check for general descriptive assertion verbs
    descriptive_keywords = [
        "demonstrate", "show", "found that", "observed", "conclude", "indicated",
        "consist", "propose", "present", "describe", "architecture", "design", "evaluate"
    ]
    if any(term in sentence.lower() for term in descriptive_keywords):
        return ClaimType.DESCRIPTIVE, True

    return ClaimType.OTHER, False


def is_valid_claim_candidate(sentence: str) -> bool:
    """Filter out non-claim boilerplate sentences."""
    if len(sentence) < 25 or len(sentence) > 600:
        return False
    for pat in SKIP_PATTERNS:
        if pat.search(sentence):
            return False
    return True


def extract_claims_from_paragraph(
    paragraph: str,
    page_number: int,
    paragraph_number: int,
) -> list[ExtractedClaim]:
    """Extract and classify candidate claims from a single paragraph."""
    sentences = split_sentences(paragraph)
    claims: list[ExtractedClaim] = []

    for idx, sentence in enumerate(sentences):
        if not is_valid_claim_candidate(sentence):
            continue

        claim_type, requires_verif = classify_claim_type(sentence)

        # Build context from previous and next sentences
        context_parts = []
        if idx > 0:
            context_parts.append(sentences[idx - 1])
        context_parts.append(sentence)
        if idx < len(sentences) - 1:
            context_parts.append(sentences[idx + 1])
        context = " ".join(context_parts)

        # Normalize text
        normalized = " ".join(sentence.split())

        # Include claims that require verification or have substantial claim types
        if requires_verif or claim_type != ClaimType.OTHER:
            claims.append(
                ExtractedClaim(
                    original_text=sentence,
                    normalized_text=normalized,
                    context_text=context,
                    claim_type=claim_type,
                    requires_external_verification=requires_verif,
                    page_number=page_number,
                    paragraph_number=paragraph_number,
                    extraction_method="rule_based_academic_extractor",
                )
            )

    return claims
