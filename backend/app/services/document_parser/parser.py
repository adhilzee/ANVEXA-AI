from __future__ import annotations

from dataclasses import dataclass, field
import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile

try:
    import pypdf
except ImportError:
    pypdf = None

logger = logging.getLogger(__name__)

# XML Namespaces in WordprocessingML
WORD_SCHEMA = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_SCHEMA}

SECTION_HEADERS = [
    "abstract",
    "introduction",
    "background",
    "related work",
    "literature review",
    "methods",
    "methodology",
    "materials and methods",
    "experiments",
    "results",
    "discussion",
    "conclusions",
    "conclusion",
    "acknowledgments",
    "acknowledgements",
    "references",
    "bibliography",
]


@dataclass
class ParsedPage:
    page_number: int
    text: str
    paragraphs: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    full_text: str
    sections: dict[str, str] = field(default_factory=dict)
    bibliography_text: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


def _split_into_paragraphs(text: str) -> list[str]:
    """Split text into clean, non-empty paragraphs."""
    raw_paras = re.split(r"\n\s*\n", text)
    cleaned = []
    for p in raw_paras:
        clean = " ".join(p.split()).strip()
        if clean:
            cleaned.append(clean)
    return cleaned


def _detect_sections(full_text: str) -> tuple[dict[str, str], str]:
    """Segment document text into recognized academic sections and bibliography."""
    sections: dict[str, str] = {}
    bibliography_text = ""

    # Look for section headers (e.g. '1. Introduction', 'References', etc.)
    pattern = (
        r"(?mi)^(?:[0-9IVXLCDM]+\.?\s+)?("
        + "|".join(re.escape(h) for h in SECTION_HEADERS)
        + r")\s*$"
    )

    matches = list(re.finditer(pattern, full_text))
    if not matches:
        return sections, bibliography_text

    for i, match in enumerate(matches):
        section_name = match.group(1).lower().strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()
        sections[section_name] = content

        if section_name in ("references", "bibliography"):
            bibliography_text = content

    return sections, bibliography_text


def parse_pdf(file_bytes: bytes) -> ParsedDocument:
    """Extract pages, text, and structure from a PDF file."""
    pages: list[ParsedPage] = []
    full_text_parts: list[str] = []

    if pypdf is not None:
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for idx, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                paras = _split_into_paragraphs(page_text)
                pages.append(
                    ParsedPage(
                        page_number=idx,
                        text=page_text,
                        paragraphs=paras,
                        metadata={"page_index": idx - 1},
                    )
                )
                full_text_parts.append(page_text)
        except Exception as exc:
            logger.warning("pypdf extraction error: %s; falling back to text scan", exc)

    # Fallback if no pages extracted (e.g. plain text or corrupted PDF streams)
    if not pages:
        fallback_text = file_bytes.decode("utf-8", errors="ignore")
        paras = _split_into_paragraphs(fallback_text)
        pages.append(
            ParsedPage(
                page_number=1,
                text=fallback_text,
                paragraphs=paras,
                metadata={"page_index": 0},
            )
        )
        full_text_parts.append(fallback_text)

    full_text = "\n\n".join(full_text_parts)
    sections, bibliography_text = _detect_sections(full_text)

    return ParsedDocument(
        pages=pages,
        full_text=full_text,
        sections=sections,
        bibliography_text=bibliography_text,
        metadata={"total_pages": len(pages), "format": "pdf"},
    )


def parse_docx(file_bytes: bytes) -> ParsedDocument:
    """Extract pages, text, and structure from a DOCX file without external dependencies."""
    buf = io.BytesIO(file_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("Invalid DOCX file: missing word/document.xml")
        xml_content = zf.read("word/document.xml")

    root = ET.fromstring(xml_content)

    pages: list[ParsedPage] = []
    current_page_number = 1
    current_page_paras: list[str] = []
    all_text_parts: list[str] = []

    for elem in root.iter():
        if elem.tag == f"{{{WORD_SCHEMA}}}p":
            text_runs: list[str] = []
            has_page_break = False

            for child in elem.iter():
                if child.tag == f"{{{WORD_SCHEMA}}}t" and child.text:
                    text_runs.append(child.text)
                elif child.tag == f"{{{WORD_SCHEMA}}}br":
                    br_type = child.attrib.get(f"{{{WORD_SCHEMA}}}type")
                    if br_type == "page":
                        has_page_break = True
                elif child.tag == f"{{{WORD_SCHEMA}}}lastRenderedPageBreak":
                    has_page_break = True

            para_text = "".join(text_runs).strip()
            if para_text:
                current_page_paras.append(para_text)
                all_text_parts.append(para_text)

            if has_page_break and current_page_paras:
                page_text = "\n\n".join(current_page_paras)
                pages.append(
                    ParsedPage(
                        page_number=current_page_number,
                        text=page_text,
                        paragraphs=list(current_page_paras),
                        metadata={"page_index": current_page_number - 1},
                    )
                )
                current_page_number += 1
                current_page_paras.clear()

    if current_page_paras or not pages:
        page_text = "\n\n".join(current_page_paras) if current_page_paras else ""
        pages.append(
            ParsedPage(
                page_number=current_page_number,
                text=page_text,
                paragraphs=list(current_page_paras),
                metadata={"page_index": current_page_number - 1},
            )
        )

    full_text = "\n\n".join(all_text_parts)
    sections, bibliography_text = _detect_sections(full_text)

    return ParsedDocument(
        pages=pages,
        full_text=full_text,
        sections=sections,
        bibliography_text=bibliography_text,
        metadata={"total_pages": len(pages), "format": "docx"},
    )


def parse_document(file_bytes: bytes, filename: str) -> ParsedDocument:
    """Parse PDF or DOCX file bytes into a structured ParsedDocument."""
    lower_name = filename.lower()
    if lower_name.endswith(".docx"):
        return parse_docx(file_bytes)
    return parse_pdf(file_bytes)
