from __future__ import annotations

from backend.app.services.citation_detector.detector import (
    DetectedInTextCitation,
    ParsedBibliographyEntry,
    detect_in_text_citations,
    extract_doi,
    extract_url,
    extract_year,
    parse_bibliography_entry,
    parse_bibliography_section,
)
from backend.app.services.citation_detector.service import (
    link_claims_to_citations,
    process_citation_detection,
)

__all__ = [
    "DetectedInTextCitation",
    "ParsedBibliographyEntry",
    "detect_in_text_citations",
    "extract_doi",
    "extract_url",
    "extract_year",
    "link_claims_to_citations",
    "parse_bibliography_entry",
    "parse_bibliography_section",
    "process_citation_detection",
]
