from __future__ import annotations

from backend.app.services.claim_extractor.extractor import (
    ExtractedClaim,
    classify_claim_type,
    extract_claims_from_paragraph,
    split_sentences,
)
from backend.app.services.claim_extractor.service import process_claim_extraction

__all__ = [
    "ExtractedClaim",
    "classify_claim_type",
    "extract_claims_from_paragraph",
    "process_claim_extraction",
    "split_sentences",
]
