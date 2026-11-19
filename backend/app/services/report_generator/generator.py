from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import logging
import re
import textwrap
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models.document import Citation, Claim, Document, DocumentVersion
from backend.app.models.enums import ProcessingStatus, ReportFormat, Verdict
from backend.app.models.verification import ReferenceIssue, Report, VerificationEvidence, VerificationResult
from backend.app.services.document_service import get_storage_backend
from backend.app.services.document_storage.storage_service import StorageBackend

logger = logging.getLogger(__name__)

# Transliteration mapping for mathematical and non-ASCII scientific characters
UNICODE_TRANSLITERATION_MAP = {
    "∑": "sum",
    "∏": "prod",
    "∈": "in",
    "∉": "not in",
    "∋": "contains",
    "⊆": "subset_eq",
    "⊂": "subset",
    "⊇": "superset_eq",
    "⊃": "superset",
    "∪": "union",
    "∩": "intersect",
    "∅": "empty_set",
    "∀": "for all",
    "∃": "exists",
    "∄": "not exists",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "≈": "~=",
    "≡": "==",
    "±": "+/-",
    "∓": "-/+",
    "×": "x",
    "÷": "/",
    "√": "sqrt",
    "∞": "infinity",
    "∫": "integral",
    "∂": "partial",
    "∇": "grad",
    "∆": "delta",
    "Δ": "Delta",
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "Γ": "Gamma",
    "δ": "delta",
    "ε": "epsilon",
    "θ": "theta",
    "λ": "lambda",
    "Λ": "Lambda",
    "μ": "mu",
    "π": "pi",
    "Π": "Pi",
    "σ": "sigma",
    "Σ": "Sigma",
    "τ": "tau",
    "φ": "phi",
    "ω": "omega",
    "Ω": "Omega",
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "⇒": "=>",
    "⇐": "<=",
    "⇔": "<=>",
    "†": "*",
    "‡": "**",
    "⋆": "*",
    "•": "*",
    "·": "*",
    "…": "...",
    "–": "-",
    "—": "--",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "′": "'",
    "″": '"',
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}


def sanitize_pdf_text(text: str) -> str:
    """Sanitize and transliterate mathematical and special Unicode symbols
    into standard ASCII/Latin-1 equivalents so math symbols do not render as '?' in the PDF.
    """
    if not text:
        return ""
    for symbol, rep in UNICODE_TRANSLITERATION_MAP.items():
        text = text.replace(symbol, rep)
    # Strip any remaining unencodable non-latin-1 characters
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _build_pdf_document(lines: list[str], max_lines_per_page: int = 50) -> bytes:
    """Build a compliant multi-page PDF document with text wrapping, sanitization, and xref table."""
    pages_lines: list[list[str]] = []
    current_page: list[str] = []
    for line in lines:
        current_page.append(line)
        if len(current_page) >= max_lines_per_page:
            pages_lines.append(current_page)
            current_page = []
    if current_page or not pages_lines:
        pages_lines.append(current_page)

    num_pages = len(pages_lines)
    font_obj_id = 3 + num_pages
    first_stream_id = font_obj_id + 1

    kids_str = " ".join(f"{3 + i} 0 R" for i in range(num_pages))
    parts: list[bytes] = []
    offsets: list[int] = []
    current_offset = 0

    def add_obj(obj_data: str | bytes) -> None:
        nonlocal current_offset
        offsets.append(current_offset)
        b = obj_data.encode("latin-1") if isinstance(obj_data, str) else obj_data
        parts.append(b)
        current_offset += len(b)

    header = b"%PDF-1.4\n"
    parts.append(header)
    current_offset += len(header)

    # 1: Catalog
    add_obj("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # 2: Pages
    add_obj(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {num_pages} >>\nendobj\n")
    # Page objects
    for i in range(num_pages):
        stream_id = first_stream_id + i
        add_obj(
            f"{3 + i} 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 {font_obj_id} 0 R >> >> /MediaBox [0 0 612 792] /Contents {stream_id} 0 R >>\nendobj\n"
        )
    # Font object
    add_obj(f"{font_obj_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n")

    # Content streams
    for i, p_lines in enumerate(pages_lines):
        stream_id = first_stream_id + i
        stream_content = "BT /F1 10 Tf 50 750 Td 12 TL\n"
        for line in p_lines:
            # Standardize [Page X] formatting so typos like '(Page 16' or '(Page 16)' never appear
            if "Page" in line and "Claim #" in line:
                line = re.sub(r"[\(\[]Page\s+(\d+)\)?", r"[Page \1]", line)
            sanitized = sanitize_pdf_text(line)
            safe = sanitized.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_content += f"({safe}) '\n"
        stream_content += "ET\n"
        s_bytes = stream_content.encode("latin-1", errors="replace")
        stream_obj = (
            f"{stream_id} 0 obj\n<< /Length {len(s_bytes)} >>\nstream\n".encode("ascii")
            + s_bytes
            + b"\nendstream\nendobj\n"
        )
        add_obj(stream_obj)

    startxref = current_offset
    total_objs = first_stream_id + num_pages
    xref = f"xref\n0 {total_objs}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n"
    trailer = f"trailer\n<< /Size {total_objs} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF"
    parts.append(xref.encode("ascii") + trailer.encode("ascii"))

    return b"".join(parts)


def generate_csv_report_data(
    doc: Document,
    version: DocumentVersion,
    claims: list[Claim],
    results_map: dict[UUID, VerificationResult],
    issues: list[ReferenceIssue],
) -> str:
    """Generate CSV string containing structured verification audit data."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Document Header
    writer.writerow(["ANVEXA AI Academic Verification Audit Report"])
    writer.writerow(["Document Title", doc.title])
    writer.writerow(["Filename", doc.filename])
    writer.writerow(["Total Claims", len(claims)])
    writer.writerow(["Generated At", datetime.now(timezone.utc).isoformat()])
    writer.writerow([])

    # Reference Issues Section
    writer.writerow(["--- REFERENCE ISSUES ---"])
    writer.writerow(["Issue ID", "Type", "Certainty", "Description"])
    for issue in issues:
        writer.writerow([str(issue.id), issue.issue_type.value, issue.certainty.value, issue.description])
    writer.writerow([])

    # Claims & Verification Section
    writer.writerow(["--- CLAIMS & VERIFICATION RESULTS ---"])
    writer.writerow([
        "Claim ID",
        "Page",
        "Paragraph",
        "Claim Type",
        "Claim Text",
        "Verdict",
        "Confidence",
        "Confidence Score",
        "Supporting Count",
        "Contradicting Count",
        "Neutral Count",
        "Total Retrieved",
        "AI Explanation",
    ])

    for c in claims:
        res = results_map.get(c.id)
        verdict = res.verdict.value if res else "unverified"
        conf = res.confidence.value if res and res.confidence else "n/a"
        score = f"{res.confidence_score:.2f}" if res and res.confidence_score is not None else "n/a"
        sup_cnt = res.supporting_count if res else 0
        contra_cnt = res.contradicting_count if res else 0
        neu_cnt = res.neutral_count if res else 0
        ret_cnt = res.retrieved_count if res else 0
        explanation = res.explanation if res else ""

        writer.writerow([
            str(c.id),
            c.page_number or 1,
            c.paragraph_number or 1,
            c.claim_type.value,
            c.original_text,
            verdict,
            conf,
            score,
            sup_cnt,
            contra_cnt,
            neu_cnt,
            ret_cnt,
            explanation,
        ])

    return output.getvalue()


def generate_pdf_report_data(
    doc: Document,
    version: DocumentVersion,
    claims: list[Claim],
    results_map: dict[UUID, VerificationResult],
    issues: list[ReferenceIssue],
) -> bytes:
    """Generate a clean, structured PDF report.

    Uses minimal pure PDF generation with standard PDF objects so it works
    universally without heavy graphics binaries.
    """
    verdicts_count: dict[str, int] = {}
    for c in claims:
        res = results_map.get(c.id)
        v = res.verdict.value if res else "unverified"
        verdicts_count[v] = verdicts_count.get(v, 0) + 1

    lines = [
        "ANVEXA AI - Academic Verification Audit Report",
        "=" * 50,
        f"Document Title: {doc.title}",
        f"Original Filename: {doc.filename}",
        f"Verified Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Total Extracted Claims: {len(claims)}",
        f"Flagged Reference Issues: {len(issues)}",
        "",
        "VERDICT SUMMARY:",
    ]

    for verdict_name, count in verdicts_count.items():
        pct = (count / len(claims) * 100) if claims else 0
        lines.append(f"  * {verdict_name.upper()}: {count} ({pct:.1f}%)")

    lines.extend([
        "",
        "FLAGGED REFERENCE ISSUES:",
    ])
    if issues:
        for idx, issue in enumerate(issues, start=1):
            lines.append(f"  [{idx}] {issue.issue_type.value.upper()} ({issue.certainty.value}): {issue.description}")
    else:
        lines.append("  No critical reference or citation integrity issues detected.")

    lines.extend([
        "",
        "DETAILED VERIFICATION RESULTS (SAMPLE):",
    ])

    for idx, c in enumerate(claims[:15], start=1):
        res = results_map.get(c.id)
        v = res.verdict.value.upper() if res else "UNVERIFIED"
        conf = f"{res.confidence_score * 100:.0f}%" if res and res.confidence_score else "N/A"
        sup_cnt = int(res.supporting_count) if res and res.supporting_count is not None else 0
        contra_cnt = int(res.contradicting_count) if res and res.contradicting_count is not None else 0
        neu_cnt = int(res.neutral_count) if res and res.neutral_count is not None else 0
        # Matching square brackets for claim header, ensuring consistent [Page X] formatting
        page_num = int(c.page_number) if c.page_number is not None else 1
        header_line = f"Claim #{idx} [Page {page_num}] {v} (Confidence: {conf})"
        header_line = re.sub(r"[\(\[]Page\s+(\d+)\)?", r"[Page \1]", header_line)
        lines.append(header_line)
        # Explicit evidence counts ensuring 0 counts format as '0 contradicting', never omitted
        lines.append(f"Evidence: {sup_cnt} supporting, {contra_cnt} contradicting, {neu_cnt} neutral")

        # Multi-line text wrapping for Text: and Explanation: fields
        text_str = f'Text: "{c.original_text}"'
        for wrapped_line in textwrap.wrap(text_str, width=80):
            lines.append(wrapped_line)

        if res and res.explanation:
            expl_str = f"Explanation: {res.explanation}"
            for wrapped_line in textwrap.wrap(expl_str, width=80):
                lines.append(wrapped_line)
        lines.append("-" * 40)

    return _build_pdf_document(lines)


def generate_verification_report(
    document_id: UUID,
    user_id: UUID,
    report_format: ReportFormat,
    db: Session,
    storage: StorageBackend | None = None,
    settings: Settings | None = None,
) -> Report:
    """Generate, persist, and store a verification report for a document."""
    if settings is None:
        settings = get_settings()
    if storage is None:
        storage = get_storage_backend(settings)

    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
    ).scalars().first()
    if version is None:
        raise ValueError(f"No version found for document {document_id}")

    claims = db.execute(
        select(Claim).where(Claim.document_version_id == version.id)
    ).scalars().all()

    results = db.execute(
        select(VerificationResult).where(VerificationResult.document_version_id == version.id)
    ).scalars().all()
    results_map = {r.claim_id: r for r in results}

    issues = db.execute(
        select(ReferenceIssue).where(ReferenceIssue.document_version_id == version.id)
    ).scalars().all()

    now = datetime.now(timezone.utc)
    ext = ".csv" if report_format == ReportFormat.CSV else ".pdf"
    storage_key = f"reports/{uuid4().hex}{ext}"

    if report_format == ReportFormat.CSV:
        content_str = generate_csv_report_data(doc, version, list(claims), results_map, list(issues))
        storage.save(storage_key, content_str.encode("utf-8"))
    else:
        content_bytes = generate_pdf_report_data(doc, version, list(claims), results_map, list(issues))
        storage.save(storage_key, content_bytes)

    report = Report(
        owner_id=user_id,
        document_id=doc.id,
        document_version_id=version.id,
        format=report_format,
        status=ProcessingStatus.COMPLETED,
        storage_key=storage_key,
        generated_at=now,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info("Generated %s report %s for document %s", report_format.value, report.id, doc.id)
    return report
