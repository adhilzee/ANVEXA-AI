# ANVEXA AI — Academic Document Verification & Research Integrity Platform

[![Tests](https://img.shields.io/badge/tests-127%2F127%20passing-brightgreen.svg)](#running-the-automated-test-suite)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![PWA](https://img.shields.io/badge/PWA-Installable%20App-orange.svg)](#-progressive-web-app-pwa-support)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**ANVEXA AI** is an evidence-traceable academic document verification and scientific integrity platform. It provides an automated, rigorous end-to-end pipeline for parsing research manuscripts, detecting and linking citations, extracting verifiable atomic claims, resolving academic literature via Crossref and Semantic Scholar, auditing reference integrity (retractions, broken DOIs, metadata mismatches), ranking evidence passages using hybrid semantic-lexical retrieval, classifying claims into evidence-grounded verdicts, and exporting formal verification audit certificates (PDF and CSV).

---

## ⚡ Quickstart for Mentors & Teammates (1-Minute Setup)

You can launch the complete platform with a pre-seeded manuscript, verified claims, and audit reports in **one single command** without needing to configure external databases or third-party API keys.

### 1. Clone & Enter Repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd ANVEXA-AI-main
```

### 2. Set Up Virtual Environment & Dependencies

#### On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt
```

#### On macOS / Linux (Bash / Zsh):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
```

### 3. Launch Demo with 1 Click

Run the root quickstart launcher:

```bash
python run_demo.py
```

This single command will:
1. Initialize the local SQLite database schema (`anvexa_demo.db`).
2. Seed the demo user account.
3. Ingest and execute the 6-stage verification pipeline on a sample manuscript.
4. Generate both PDF audit certificates and CSV reports.
5. Start the live ASGI application server at **`http://127.0.0.1:8000/`**.

---

## 🖥️ Live Access & Credentials

| Service | URL | Notes |
|---|---|---|
| **Web Dashboard & PWA** | [`http://127.0.0.1:8000/`](http://127.0.0.1:8000/) | Responsive Glassmorphism UI with live audit tracking |
| **Interactive API Docs** | [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs) | Interactive Swagger UI for all REST endpoints |
| **Alternative API Docs** | [`http://127.0.0.1:8000/redoc`](http://127.0.0.1:8000/redoc) | ReDoc API specifications |

### Demo Login
- **Email**: `demo@anvexa.ai`
- **Password**: `DemoPassword123!`
- *(Or simply click the **"Quick Demo Login"** button on the web login screen)*

---

## 📂 Testing With Pre-Bundled Sample Papers

The `sample_papers/` folder contains ready-to-test academic documents designed to demonstrate different verification capabilities. After logging into the dashboard, drag and drop or upload any of the following:

| Manuscript File | Format | Key Demonstration Capabilities |
|---|---|---|
| [`sample_papers/sample_biomedical_verification_paper.pdf`](sample_papers/sample_biomedical_verification_paper.pdf) | PDF | Biomedical assertions, p-values, and retracted literature detection (`Wakefield et al.` Lancet retraction audit). |
| [`sample_papers/clinical_oncology_immunotherapy_trial.docx`](sample_papers/clinical_oncology_immunotherapy_trial.docx) | Word DOCX | Native DOCX XML parsing, clinical oncology trial claims, percentages, and statistical confidence intervals. |
| [`sample_papers/direct_air_carbon_capture_review.pdf`](sample_papers/direct_air_carbon_capture_review.pdf) | PDF | Environmental engineering review, multi-citation resolution, thermodynamic efficiency claims, and comparative baselines. |

---

## 📲 Progressive Web App (PWA) Support

ANVEXA AI is a fully compliant Progressive Web App with service worker offline caching, responsive UI, high-resolution app icons, and standalone app display mode.

### How to Install as an App:
- **PC & Mac (Google Chrome / Microsoft Edge / Brave)**:
  - Open `http://127.0.0.1:8000/`.
  - Click the **"Install App 📲"** button in the top navigation bar, or click the install icon in the browser address bar.
  - The app will run in its own dedicated, chromeless desktop window.
- **Android (Chrome / Edge / Samsung Internet)**:
  - Navigate to `http://127.0.0.1:8000/`.
  - Tap the **"Install App 📲"** banner or tap `⋮` Menu $\to$ **"Add to Home screen"** / **"Install app"**.
- **iOS & iPadOS (Apple Safari)**:
  - Open `http://127.0.0.1:8000/` in Safari.
  - Tap the **Share** button (box with upward arrow) $\to$ select **"Add to Home Screen"** $\to$ tap **Add**.

---

## 🔬 Core Verification Architecture

ANVEXA AI operates as a 6-stage evidence verification pipeline:

```
[ Research Paper (PDF / DOCX) ]
              │
              ▼
    1. Document Parser
    (De-hyphenation, front-matter stripping, section parsing, references cutoff)
              │
              ▼
    2. Citation & Bibliography Detector
    (Bracketed [1] & Author-Year, DOI hygiene & validation, citation-to-claim mapping)
              │
              ▼
    3. Atomic Claim Extractor
    (Numerical, Statistical, Comparative, Causal, Temporal, Descriptive; filters setup & future work)
              │
              ▼
    4. Literature Retriever & Integrity Auditor
    (Retraction database checks, broken DOI fallback to Google Scholar / Semantic Scholar)
              │
              ▼
    5. Evidence Engine & Neural Ranking
    (384-dim semantic embeddings, passage chunking, hybrid semantic-lexical scoring)
              │
              ▼
    6. Verdict Classifier & Human Review Workflow
    (SUPPORTED, PARTLY_SUPPORTED, CONTRADICTORY, UNSUPPORTED, confidence scoring)
              │
              ▼
[ Audit Certificate (PDF & CSV) / Interactive PWA Dashboard ]
```

### Detailed Pipeline Capabilities:
1. **Document Parser (`backend/app/services/document_parser/`)**:
   - Parses PDF (via `pypdf`) and Word DOCX (via native XML schema parsing).
   - Fixes PDF line-wrap word hyphenation (e.g. `knowl- edge` $\to$ `knowledge`, `pre- trained` $\to$ `pre-trained`).
   - Strips metadata front-matter headers (titles, author emails, affils) before `"Abstract"`.
   - Stops claim extraction cleanly before the `"References"` section.
2. **Citation Detector (`backend/app/services/citation_detector/`)**:
   - Parses inline citation markers (`[1]`, `[1, 2]`, `(Smith et al., 2021)`).
   - Cleans extracted DOIs of trailing punctuation (`.,;:'")\]}`) and supports multi-slash ACL Anthology DOIs.
   - Detects `RETRACTED_SOURCE`, `BROKEN_DOI`, and `METADATA_MISMATCH`.
3. **Claim Extractor (`backend/app/services/claim_extractor/`)**:
   - Classifies assertions into 6 academic claim categories (`NUMERICAL`, `STATISTICAL`, `COMPARATIVE`, `CAUSAL`, `TEMPORAL`, `DESCRIPTIVE`).
   - Filters out internal methodology parameters (e.g., `"We use k=100..."`), speculative future work, reference numbers, and tabular data rows.
4. **Evidence Engine (`backend/app/services/evidence_engine/`)**:
   - Chunks academic literature into passage units with section and page tracking.
   - Hybrid relevance ranking combining cosine semantic similarity and token overlap.
5. **Verdict Classifier (`backend/app/services/verdict_classifier/`)**:
   - Assigns evidence-grounded verdicts: `SUPPORTED`, `PARTLY_SUPPORTED`, `CONTRADICTORY`, `UNSUPPORTED`, `NEEDS_REVIEW`.
   - Flags contradiction when claims rely on retracted literature.
6. **Audit Report Generator (`backend/app/services/report_generator/`)**:
   - Generates publication-ready PDF audit certificates and CSV reports.
   - Sanitizes non-ASCII math symbols (`∑` $\to$ `sum`, `∈` $\to$ `in`) preventing PDF encoding errors.
   - Enforces clean `[Page X]` bracket formatting and evidence counts.

---

## 🧪 Running the Automated Test Suite

The project includes an extensive test suite verifying all parsers, extractors, retrievers, classifiers, API endpoints, PWA manifests, and security controls:

```bash
# Run all tests
pytest backend/tests

# Run with verbose output and coverage
pytest backend/tests -v
```

**Results**: `127 passed in ~27s` (100% pass rate).

---

## 🌐 Production PostgreSQL Configuration (Optional)

While SQLite is configured out-of-the-box for instant local development and demos, ANVEXA AI supports enterprise PostgreSQL with pgvector for high-throughput semantic search:

1. Copy `.env.example` to `.env`:
   ```bash
   cp backend/.env.example backend/.env
   ```
2. Configure your PostgreSQL connection string in `backend/.env`:
   ```env
   ANVEXA_DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/anvexa_db
   ```
3. Run Alembic migrations:
   ```bash
   alembic -c backend/alembic.ini upgrade head
   ```

---

## 📁 Repository Directory Structure

```
ANVEXA-AI-main/
├── run_demo.py                      # 1-Click root launcher (Seeds demo DB & starts app)
├── README.md                        # Documentation & mentor guide
├── sample_papers/                   # Pre-bundled test academic papers (PDF & DOCX)
│   ├── sample_biomedical_verification_paper.pdf
│   ├── clinical_oncology_immunotherapy_trial.docx
│   └── direct_air_carbon_capture_review.pdf
├── scripts/                         # Helper & utility automation scripts
│   ├── run_demo.py                  # Demo runner logic
│   ├── seed_demo.py                 # SQLite database seeder
│   ├── generate_pwa_icons.py        # PWA icon generation script
│   └── test_demo_e2e.py             # End-to-end integration test
├── backend/
│   ├── requirements.txt             # Core production dependencies
│   ├── requirements-dev.txt         # Development & testing dependencies
│   ├── alembic.ini                  # Database migration configuration
│   ├── app/
│   │   ├── main.py                  # FastAPI application entrypoint & static routes
│   │   ├── core/                    # Security, JWT, hashing, DOI utilities & config
│   │   ├── database/                # SQLAlchemy session, engine & base metadata
│   │   ├── models/                  # Database models (User, Document, Claim, Evidence, Review, Report)
│   │   ├── schemas/                 # Pydantic validation schemas
│   │   ├── api/endpoints/           # REST endpoints (auth, documents, claims, verification, reports, review)
│   │   ├── services/
│   │   │   ├── document_parser/     # PDF & DOCX text extraction & section segmentation
│   │   │   ├── citation_detector/   # In-text citations & bibliography parsing
│   │   │   ├── claim_extractor/     # Atomic claim classification & filtering
│   │   │   ├── source_retriever/    # Crossref / Semantic Scholar & retraction auditor
│   │   │   ├── evidence_engine/     # Passage chunking & hybrid ranking
│   │   │   ├── verdict_classifier/  # Evidence-grounded verdict determination
│   │   │   ├── verification_engine/ # 6-stage verification orchestration pipeline
│   │   │   └── report_generator/    # PDF audit certificate & CSV generator
│   │   └── static/                  # PWA Web Frontend
│   │       ├── dashboard.html       # Single-page glassmorphism dashboard UI
│   │       ├── manifest.json        # PWA application manifest
│   │       ├── sw.js                # Service Worker for offline asset caching
│   │       └── icons/               # 192px, 512px, maskable & Apple touch icons
│   └── tests/                       # 127 Automated Unit & Integration Tests
```

---

## 👥 Team & Acknowledgments

Developed by **Team Code Nova** for the academic and scientific research community.
Questions or feedback? Please open an issue or pull request!
