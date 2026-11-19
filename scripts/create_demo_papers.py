"""Script to generate realistic academic demonstration papers (PDF and DOCX) for ANVEXA AI upload."""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
output_dir = root_dir / "sample_papers"
output_dir.mkdir(parents=True, exist_ok=True)


def build_pdf_binary(lines: list[str]) -> bytes:
    """Generate a clean, fully compliant PDF 1.4 binary file."""
    content_stream = "BT\n/F1 10 Tf\n45 740 Td\n13 TL\n"
    for line in lines:
        if line == "":
            content_stream += "T*\n"
            continue
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_stream += f"({safe}) '\n"
    content_stream += "ET\n"
    content_bytes = content_stream.encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content_bytes)).encode("ascii") + b" >>\nstream\n" + content_bytes + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii"))
    pdf.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


def build_docx_binary(paragraphs: list[str]) -> bytes:
    """Generate a clean, fully compliant Office Open XML DOCX binary file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )

        body_elements = []
        for p in paragraphs:
            escaped = (
                p.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            body_elements.append(f"<w:p><w:r><w:t>{escaped}</w:t></w:r></w:p>")

        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{"".join(body_elements)}</w:body>'
            "</w:document>"
        )
        zf.writestr("word/document.xml", doc_xml)

    return buf.getvalue()


def generate_sample_papers():
    print("=" * 65)
    print("ANVEXA AI — Generating Sample Demonstration Papers")
    print("=" * 65)

    # -------------------------------------------------------------------------
    # Paper 1: PDF — AI & Biomedical Claim Verification
    # Contains: supported claims, retracted citation, metadata mismatch, broken DOI
    # -------------------------------------------------------------------------
    p1_lines = [
        "Empirical Evaluation of Transformer Reasoning and Evidence Extraction",
        "Dr. Elena Rostova, Department of Computational Biology, Stanford University",
        "",
        "Abstract",
        "Modern deep learning architectures exhibit substantial proficiency in structured information",
        "retrieval. This study systematically analyzes multi-step biomedical claim extraction across",
        "peer-reviewed literature, establishing rigorous verification benchmarks and citation tracing.",
        "",
        "1. Introduction",
        "Recent advances in neural representation learning achieved 95% accuracy in claim extraction [1].",
        "The experimental clinical treatment demonstrated a 40% reduction in disease recurrence (p < 0.001) [1].",
        "Algorithm A consistently outperformed conventional baselines across all benchmark datasets [1].",
        "Between 2018 and 2022, clinical adoption increased significantly across medical centers.",
        "However, earlier epidemiological investigations claimed an association between MMR vaccines and autism [2].",
        "A speculative retrospective survey claimed that daily megadose vitamin C reduces all-cause mortality by 85% [3].",
        "",
        "2. Methodology and Empirical Results",
        "Model latency increased by 15% when scaling context lengths from 4,000 to 32,000 tokens [1].",
        "The automated verification pipeline achieved 91.4% precision on standard reference benchmarks.",
        "Reference integrity checks identified critical discrepancies in legacy biomedical citations [4].",
        "",
        "3. Conclusion",
        "Automated semantic alignment and citation integrity auditing provide essential safeguards against",
        "hallucinatory outputs and retracted claims in contemporary computational scholarship.",
        "",
        "References",
        "[1] Vaswani, A. et al. Attention is All You Need. NeurIPS 2017. doi: 10.1038/nature14539",
        "[2] Wakefield, A. et al. Retracted Ileal-lymphoid-nodular hyperplasia. Lancet 1998. doi: 10.1016/s0140-6736(97)11096-0",
        "[3] Linus, P. & Cameron, E. Supplemental Ascorbate in Cancer. PNAS 1976. doi: 10.1073/pnas.73.10.3685",
        "[4] Nonexistent Citation Entry for Integrity Testing. doi: 10.9999/broken.doi.never.existed.404",
    ]

    p1_pdf = build_pdf_binary(p1_lines)
    p1_path = output_dir / "sample_biomedical_verification_paper.pdf"
    p1_path.write_bytes(p1_pdf)
    print(f"[+] Created Demo PDF:  {p1_path.name} ({len(p1_pdf)} bytes)")

    # -------------------------------------------------------------------------
    # Paper 2: DOCX — Clinical Oncology & Targeted Immunotherapy Trial
    # -------------------------------------------------------------------------
    p2_paragraphs = [
        "Phase III Randomized Controlled Trial of Dual Immune Checkpoint Blockade",
        "Marcus Vance, MD, PhD, Institute of Experimental Oncology",
        "",
        "Abstract",
        "Dual immune checkpoint inhibition represents a paradigm shift in advanced solid tumor therapy.",
        "We evaluated overall survival and progression-free survival in patients receiving combination therapy.",
        "",
        "1. Introduction",
        "In patients with advanced metastatic melanoma, combination immunotherapy achieved a 52% 5-year survival rate [1].",
        "Adverse event incidence was 18% higher in the combination arm compared to monotherapy (p = 0.012) [1].",
        "Treatment response rates remained consistent across all biomarker-positive patient cohorts.",
        "Between 2019 and 2024, checkpoint inhibitors became the frontline standard of care across 85 oncology centers.",
        "",
        "2. Methods",
        "Patients were randomized 1:1 to receive either dual checkpoint blockade or standard monotherapy.",
        "Primary endpoints included progression-free survival and verified objective response rate.",
        "",
        "3. Results and Discussion",
        "Median progression-free survival reached 11.5 months in the investigational arm versus 6.9 months in control.",
        "Biomarker stratification demonstrated a 65% objective response rate in high PD-L1 expression subgroups [1].",
        "",
        "References",
        "[1] Wolchok, J. D. et al. Overall Survival with Combined Nivolumab and Ipilimumab in Advanced Melanoma. NEJM 2017. doi: 10.1038/nature14539",
        "[2] Experimental Oncology Benchmark Reference. doi: 10.1016/s0140-6736(97)11096-0",
    ]

    p2_docx = build_docx_binary(p2_paragraphs)
    p2_path = output_dir / "clinical_oncology_immunotherapy_trial.docx"
    p2_path.write_bytes(p2_docx)
    print(f"[+] Created Demo DOCX: {p2_path.name} ({len(p2_docx)} bytes)")

    # -------------------------------------------------------------------------
    # Paper 3: PDF — Thermodynamic Limits of Direct Air Carbon Capture
    # -------------------------------------------------------------------------
    p3_lines = [
        "Thermodynamic Constraints and Energetic Costs of Direct Air Carbon Capture",
        "Prof. Julian Sterling, Department of Chemical Engineering, MIT",
        "",
        "Abstract",
        "Direct Air Capture (DAC) systems face strict energetic limits imposed by the second law of thermodynamics.",
        "This evaluation calculates minimum theoretical work requirements for ambient atmospheric CO2 extraction.",
        "",
        "1. Introduction",
        "Minimum theoretical work required to separate CO2 from ambient air at 415 ppm is approximately 20 kJ per mole.",
        "Operating energetic consumption in prototype contactors exceeds thermodynamic minimums by over 300% [1].",
        "Electrochemical regeneration methods demonstrate a 25% improvement in thermal efficiency over solvent systems [1].",
        "Global direct air capture capacity grew from 10 kilotons in 2020 to over 150 kilotons in 2024.",
        "",
        "2. Discussion",
        "Capital expenditure remains high, averaging $450 per ton of net captured carbon dioxide.",
        "Transitioning to solid sorbent hollow fiber contactors reduced parasitic regeneration loads by 35% [1].",
        "",
        "References",
        "[1] Vaswani, A. et al. Scalable Energy Systems and Transformer Architectures. Nature 2017. doi: 10.1038/nature14539",
    ]

    p3_pdf = build_pdf_binary(p3_lines)
    p3_path = output_dir / "direct_air_carbon_capture_review.pdf"
    p3_path.write_bytes(p3_pdf)
    print(f"[+] Created Demo PDF:  {p3_path.name} ({len(p3_pdf)} bytes)")

    print("=" * 65)
    print(f"Sample demonstration papers created successfully in:")
    print(f"  {output_dir.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    generate_sample_papers()
