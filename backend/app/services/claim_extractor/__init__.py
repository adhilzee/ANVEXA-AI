from __future__ import annotations

from backend.app.services.claim_extractor.extractor import (
    ExtractedClaim,
    classify_claim_type,
    dehyphenate_text,
    extract_claims_from_paragraph,
    is_first_person_setup,
    is_references_heading,
    is_speculative_future_work,
    split_sentences,
    strip_abstract_front_matter,
    strip_section_heading,
    truncate_at_references,
)
from backend.app.services.claim_extractor.service import process_claim_extraction

__all__ = [
    "ExtractedClaim",
    "classify_claim_type",
    "dehyphenate_text",
    "extract_claims_from_paragraph",
    "is_first_person_setup",
    "is_references_heading",
    "is_speculative_future_work",
    "process_claim_extraction",
    "split_sentences",
    "strip_abstract_front_matter",
    "strip_section_heading",
    "truncate_at_references",
]
