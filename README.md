# ANVEXA AI — Academic Document Verification Platform

ANVEXA AI is an evidence-traceable academic document verification platform. It provides an automated, rigorous pipeline for parsing research papers, detecting citations, extracting verifiable claims, resolving research literature, ranking evidence, identifying reference integrity issues (including retractions and broken DOIs), and generating comprehensive verification audit reports.

---

## Key Capabilities

1. **Document Parsing (`document_parser`)**:
   - Native parsing of PDF and DOCX academic manuscripts.
   - Extracts sections (Abstract, Introduction, Methods, Results, Discussion, References).
   - Segments text into structured pages (`DocumentPage`) and paragraphs.

2. **Citation Detection (`citation_detector`)**:
   - Detects in-text citation markers: numeric brackets (`[1]`, `[1, 2]`, `[3-5]`) and author-year styles (`(Smith et al., 2021)`).
   - Parses bibliography/references into structured records: authors, title, year, DOI, and canonical URLs.
   - Automatically maps in-text citations to claims (`ClaimCitation`).

3. **Claim Extraction (`claim_extractor`)**:
   - Identifies atomic factual and empirical assertions from manuscripts.
   - Classifies claims into distinct academic types:
     - `NUMERICAL` (percentages, sample sizes, quantitative figures)
     - `STATISTICAL` (p-values, confidence intervals, correlation coefficients, ANOVA)
     - `COMPARATIVE` (outperformed, reduced, higher/lower than)
     - `CAUSAL` (causes, leads to, induces, prevents)
     - `TEMPORAL` (timeframes, longitudinal observations)
     - `DESCRIPTIVE` (architectural and empirical findings)
   - Evaluates whether external verification is required.

4. **Source Retrieval & Reference Audit (`source_retriever`)**:
   - Validates DOI structure and queries academic literature metadata.
   - **Retraction Detection**: Flags retracted publications (e.g. Retraction Watch / CrossRef).
   - **Reference Issue Auditing**: Identifies `RETRACTED_SOURCE`, `BROKEN_DOI`, `METADATA_MISMATCH`, and `DUPLICATE_REFERENCE`.

5. **Evidence Engine (`evidence_engine`)**:
   - Chunks academic sources into discrete `EvidencePassage` units with section and page tracking.
   - 384-dimensional semantic embeddings compatible with `sentence-transformers/all-MiniLM-L6-v2` and pgvector HNSW index.
   - Hybrid relevance ranking combining semantic cosine similarity and lexical token overlap.

6. **Verdict Classifier & Verification Engine (`verdict_classifier`, `verification_engine`)**:
   - Analyzes passage relation: `SUPPORTING`, `CONTRADICTING`, or `NEUTRAL`.
   - Produces evidence-traceable verdicts:
     - `SUPPORTED`: Validated by corroborating evidence.
     - `PARTLY_SUPPORTED`: Contextually relevant, but specific empirical details require review.
     - `CONTRADICTORY`: Conflicting findings or reliance on retracted literature.
     - `UNSUPPORTED`: Claim assertion not substantiated by retrieved literature.
     - `NEEDS_REVIEW`: Ambiguous or insufficient external evidence.
   - Generates confidence scores (0.0 to 1.0) and confidence tiers (`LOW`, `MEDIUM`, `HIGH`).

7. **Human Review Workflow (`human_review`)**:
   - Dedicated Reviewer/Admin workflow to inspect AI verdicts.
   - Supports actions: `ACCEPT_AI`, `REJECT_AI`, `CHANGE_VERDICT`, `RESOLVE`, `REOPEN`.
   - Full immutable audit logging (`AuditLog`).

8. **Audit Report Generation (`report_generator`)**:
   - Export verification audit certificates in **CSV** and **PDF** formats.
   - Includes summary statistics, verdict distributions, flagged integrity issues, and claim-by-claim rationales.

9. **Security, Authentication & Document Management**:
   - Argon2id password hashing and JWT access & refresh token rotation.
   - Role-Based Access Control (`USER`, `REVIEWER`, `ADMIN`).
   - IDOR prevention and brute-force rate limiting.

---

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register new user account |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT access + refresh tokens |
| `POST` | `/api/v1/documents/upload` | Upload PDF or DOCX academic document |
| `POST` | `/api/v1/documents/{id}/verify` | Trigger full verification pipeline |
| `GET` | `/api/v1/documents/{id}/verification-summary` | Get verification scores & verdict distribution |
| `GET` | `/api/v1/documents/{id}/jobs` | Track asynchronous processing jobs & progress |
| `GET` | `/api/v1/documents/{id}/claims` | List extracted claims with type filtering |
| `GET` | `/api/v1/claims/{id}` | Inspect claim details and linked citations |
| `GET` | `/api/v1/documents/{id}/citations` | List parsed bibliography citations |
| `GET` | `/api/v1/documents/{id}/reference-issues` | List flagged reference issues (retractions, broken DOIs) |
| `GET` | `/api/v1/documents/{id}/verification-results` | View claim verification results & evidence links |
| `POST` | `/api/v1/verification-results/{id}/review` | Submit human reviewer evaluation (Reviewer/Admin) |
| `POST` | `/api/v1/documents/{id}/reports` | Generate PDF or CSV verification report |
| `GET` | `/api/v1/reports/{id}/download` | Download verification report file |
| `POST` | `/api/v1/feedback` | Submit user feedback on verification results |

---

## Quickstart (Windows PowerShell)

### 1. Setup Environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

### 2. Run Database Migrations (PostgreSQL)

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

### 3. Run Development Server

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Interactive OpenAPI Swagger UI is available at `http://127.0.0.1:8000/docs`.

### 4. Run Test Suite

Run all 99 automated unit, integration, and pipeline tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```
