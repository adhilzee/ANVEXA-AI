from __future__ import annotations

from backend.app.services.evidence_engine.engine import (
    CandidatePassage,
    chunk_text_into_passages,
    compute_cosine_similarity,
    compute_lexical_similarity,
    compute_pseudo_embedding,
    score_passage_relevance,
)
from backend.app.services.evidence_engine.service import (
    process_evidence_chunking,
    retrieve_relevant_passages_for_claim,
)

__all__ = [
    "CandidatePassage",
    "chunk_text_into_passages",
    "compute_cosine_similarity",
    "compute_lexical_similarity",
    "compute_pseudo_embedding",
    "process_evidence_chunking",
    "retrieve_relevant_passages_for_claim",
    "score_passage_relevance",
]
