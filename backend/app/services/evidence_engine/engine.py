from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Sequence

from backend.app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL

# Stopwords for lexical matching
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having",
    "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "isn't", "it", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "shan't", "she", "should", "shouldn't", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "were", "weren't",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with", "won't", "would", "wouldn't",
    "you", "your", "yours", "yourself", "yourselves",
}


@dataclass
class CandidatePassage:
    passage_id: str
    passage_text: str
    relevance_score: float
    section_name: str | None = None
    page_number: int | None = None


def chunk_text_into_passages(
    text: str,
    max_words: int = 150,
    overlap_words: int = 25,
) -> list[str]:
    """Chunk text into coherent passages respecting sentence boundaries."""
    if not text.strip():
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    passages: list[str] = []
    current_words: list[str] = []

    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue

        if len(current_words) + len(words) > max_words and current_words:
            passages.append(" ".join(current_words))
            # Keep overlap
            overlap = current_words[-overlap_words:] if len(current_words) >= overlap_words else []
            current_words = list(overlap) + words
        else:
            current_words.extend(words)

    if current_words:
        passages.append(" ".join(current_words))

    return passages


def compute_pseudo_embedding(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Generate a deterministic 384-dimensional unit vector embedding.

    Provides stable cosine distance calculation across platforms without requiring
    heavy PyTorch or downloading 500MB neural weights in sandboxed environments.
    """
    clean_text = text.lower().strip()
    words = re.findall(r"\b[a-z0-9]+\b", clean_text)
    vector = [0.0] * dimension

    if not words:
        vector[0] = 1.0
        return vector

    for idx, word in enumerate(words):
        # Hash word to dimension index
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        dim_idx = h % dimension
        sign = 1.0 if ((h >> 8) % 2 == 0) else -1.0
        # Position weighting
        weight = 1.0 / math.sqrt(idx + 1)
        vector[dim_idx] += sign * weight

    # Normalize to unit vector for cosine similarity
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [round(v / norm, 6) for v in vector]
    else:
        vector[0] = 1.0

    return vector


def compute_lexical_similarity(query: str, passage: str) -> float:
    """Compute normalized token overlap / Jaccard similarity without stopwords."""
    q_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", query.lower())) - STOPWORDS
    p_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", passage.lower())) - STOPWORDS

    if not q_tokens or not p_tokens:
        return 0.0

    intersection = q_tokens.intersection(p_tokens)
    return len(intersection) / math.sqrt(len(q_tokens) * len(p_tokens))


def compute_cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return max(0.0, min(1.0, dot))


def score_passage_relevance(query: str, passage_text: str) -> float:
    """Compute hybrid relevance score combining lexical overlap and vector similarity."""
    lexical_score = compute_lexical_similarity(query, passage_text)
    vec_query = compute_pseudo_embedding(query)
    vec_passage = compute_pseudo_embedding(passage_text)
    vector_score = compute_cosine_similarity(vec_query, vec_passage)

    if lexical_score > 0:
        combined = 0.5 * vector_score + 0.5 * lexical_score
    else:
        combined = 0.4 * vector_score
    return round(min(1.0, max(0.0, combined)), 4)
