from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import logging
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
        "AI Explanation",
    ])

    for c in claims:
        res = results_map.get(c.id)
        verdict = res.verdict.value if res else "unverified"
        conf = res.confidence.value if res and res.confidence else "n/a"
        score = f"{res.confidence_score:.2f}" if res and res.confidence_score is not None else "n/a"
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

    for idx, c in enumerate(claims[:10], start=1):
        res = results_map.get(c.id)
        v = res.verdict.value.upper() if res else "UNVERIFIED"
        conf = f"{res.confidence_score * 100:.0f}%" if res and res.confidence_score else "N/A"
        lines.append(f"Claim #{idx} [Page {c.page_number or 1}] - {v} (Confidence: {conf})")
        lines.append(f"Text: \"{c.original_text[:120]}...\"")
        if res:
            lines.append(f"Explanation: {res.explanation}")
        lines.append("-" * 40)

    # Convert text lines into valid PDF format
    content_stream = "BT /F1 10 Tf 50 750 Td 12 TL\n"
    for line in lines:
        # Escape parenthesis in PDF strings
        safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_stream += f"({safe_line}) '\n"
    content_stream += "ET\n"

    stream_bytes = content_stream.encode("latin-1", errors="replace")
    stream_len = len(stream_bytes)

    pdf_header = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n"
    )
    pdf_stream_header = f"5 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("ascii")
    pdf_footer = (
        b"\nendstream\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000325 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n500\n%%EOF"
    )
    pdf_template = pdf_header + pdf_stream_header + stream_bytes + pdf_footer

    return pdf_template


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
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == 1,
        )
    ).scalar_one_or_none()
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
