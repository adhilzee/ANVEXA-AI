from __future__ import annotations

from dataclasses import dataclass, field
import re

from backend.app.models.enums import CitationStyle

DOI_REGEX = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", re.IGNORECASE)
URL_REGEX = re.compile(r"https?://[^\s)\]\"'>]+", re.IGNORECASE)
YEAR_REGEX = re.compile(r"\b(19\d{2}|20\d{2})\b")

# Regex for numeric in-text citations: [1], [1, 2], [1-3], [1, 2, 5-7]
NUMERIC_IN_TEXT_REGEX = re.compile(r"\[([0-9\s,\-]+)\]")

# Regex for author-year in-text citations: (Smith, 2020), (Smith et al., 2019), (Smith & Jones, 2021)
AUTHOR_YEAR_IN_TEXT_REGEX = re.compile(
    r"\(([A-Z][a-zA-Z\s\.\-]+(?:et\s+al\.?|&|\band\b)?(?:[A-Z][a-zA-Z\s\.\-]*)?),\s*([12][0-9]{3}[a-z]?)\)"
)


@dataclass
class DetectedInTextCitation:
    raw_text: str
    citation_type: CitationStyle
    keys: list[str] = field(default_factory=list)  # e.g. ['1', '2'] or ['Smith, 2020']
    start_char: int = 0
    end_char: int = 0


@dataclass
class ParsedBibliographyEntry:
    raw_text: str
    reference_number: str | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    style: CitationStyle = CitationStyle.UNKNOWN


def parse_numeric_keys(inner: str) -> list[str]:
    """Expand numeric citation brackets like '1, 3-5' into ['1', '3', '4', '5']."""
    keys: list[str] = []
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            range_parts = p.split("-")
            if len(range_parts) == 2 and range_parts[0].strip().isdigit() and range_parts[1].strip().isdigit():
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
                if start <= end and end - start <= 50:
                    for num in range(start, end + 1):
                        keys.append(str(num))
                    continue
        if p.isdigit():
            keys.append(p)
    return keys


def detect_in_text_citations(text: str) -> list[DetectedInTextCitation]:
    """Find all in-text citation markers in the given passage."""
    results: list[DetectedInTextCitation] = []

    # 1. Numeric citations [1], [2, 3]
    for match in NUMERIC_IN_TEXT_REGEX.finditer(text):
        inner = match.group(1).strip()
        keys = parse_numeric_keys(inner)
        if keys:
            results.append(
                DetectedInTextCitation(
                    raw_text=match.group(0),
                    citation_type=CitationStyle.NUMERIC,
                    keys=keys,
                    start_char=match.start(),
                    end_char=match.end(),
                )
            )

    # 2. Author-year citations (Smith et al., 2020)
    for match in AUTHOR_YEAR_IN_TEXT_REGEX.finditer(text):
        author_part = match.group(1).strip()
        year_part = match.group(2).strip()
        results.append(
            DetectedInTextCitation(
                raw_text=match.group(0),
                citation_type=CitationStyle.AUTHOR_YEAR,
                keys=[f"{author_part}, {year_part}"],
                start_char=match.start(),
                end_char=match.end(),
            )
        )

    return results


def extract_doi(text: str) -> str | None:
    """Extract and normalize clean DOI."""
    match = DOI_REGEX.search(text)
    if match:
        doi = match.group(1).rstrip(".,;)>]")
        return doi.lower()
    return None


def extract_url(text: str) -> str | None:
    """Extract URL from citation string."""
    match = URL_REGEX.search(text)
    if match:
        return match.group(0).rstrip(".,;)>]")
    return None


def extract_year(text: str) -> int | None:
    """Find 4-digit publication year in citation."""
    matches = YEAR_REGEX.findall(text)
    if matches:
        return int(matches[-1])
    return None


def parse_bibliography_entry(raw_entry: str, index: int = 1) -> ParsedBibliographyEntry:
    """Parse a raw reference/bibliography line into structured attributes."""
    entry_clean = " ".join(raw_entry.split()).strip()
    doi = extract_doi(entry_clean)
    url = extract_url(entry_clean)
    year = extract_year(entry_clean)

    # Check for numeric label like [1] or 1.
    num_match = re.match(r"^\[?(\d+)\]?\.?\s*(.*)$", entry_clean)
    ref_num = None
    remaining_text = entry_clean
    style = CitationStyle.UNKNOWN

    if num_match:
        ref_num = num_match.group(1)
        remaining_text = num_match.group(2)
        style = CitationStyle.NUMERIC
    else:
        ref_num = str(index)

    # Simple heuristic to extract title and authors
    # Often formatted as: Author, A., Author, B. (Year). Title. Journal...
    # or Author, A. "Title". Journal, Year.
    title = None
    authors: list[str] = []

    # Look for quoted title
    quote_match = re.search(r"[\"“](.*?)[\"”]", remaining_text)
    if quote_match:
        title = quote_match.group(1).strip()
    else:
        # Split by periods
        sentence_parts = [s.strip() for s in remaining_text.split(".") if s.strip()]
        if len(sentence_parts) >= 2:
            # First part usually authors
            author_candidate = sentence_parts[0]
            authors_split = [a.strip() for a in re.split(r",|&|\band\b", author_candidate) if len(a.strip()) > 1]
            if authors_split:
                authors = authors_split[:5]
            # Second part usually title
            title = sentence_parts[1]
        elif sentence_parts:
            title = sentence_parts[0]

    if not title:
        title = entry_clean[:120]

    return ParsedBibliographyEntry(
        raw_text=entry_clean,
        reference_number=ref_num,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        url=url,
        style=style,
    )


def parse_bibliography_section(bib_text: str) -> list[ParsedBibliographyEntry]:
    """Parse entire bibliography text section into individual entries."""
    if not bib_text.strip():
        return []

    # Split entries: either numeric [1], [2] or blank lines
    lines = bib_text.split("\n")
    entries_raw: list[str] = []
    current_entry: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_entry:
                entries_raw.append(" ".join(current_entry))
                current_entry = []
            continue

        # Check if line starts with a new reference marker (e.g. [1], 1., or Author, Year)
        is_new_numeric = bool(re.match(r"^\[?\d+\]?\.?\s+[A-Za-z]", stripped))
        if is_new_numeric and current_entry:
            entries_raw.append(" ".join(current_entry))
            current_entry = [stripped]
        else:
            current_entry.append(stripped)

    if current_entry:
        entries_raw.append(" ".join(current_entry))

    results: list[ParsedBibliographyEntry] = []
    for idx, raw in enumerate(entries_raw, start=1):
        if len(raw) < 10:
            continue
        results.append(parse_bibliography_entry(raw, idx))

    return results
