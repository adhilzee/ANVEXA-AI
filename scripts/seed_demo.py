"""Seed script to create a sample verified paper and demonstrate ANVEXA AI."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))

# Ensure demo environment database is configured
env_file = root_dir / "backend" / ".env"
demo_db_path = (root_dir / "anvexa_demo.db").resolve().as_posix()
if not env_file.exists():
    env_content = (
        f"ANVEXA_APP_NAME=ANVEXA AI API\n"
        f"ANVEXA_APP_VERSION=0.1.0\n"
        f"ANVEXA_ENVIRONMENT=development\n"
        f"ANVEXA_DATABASE_URL=sqlite:///{demo_db_path}\n"
        f"ANVEXA_JWT_SECRET_KEY=anvexa-super-secret-key-for-development-only-change-in-prod-32bytes!\n"
        f"ANVEXA_DOCUMENT_STORAGE_PATH=./storage/documents\n"
    )
    env_file.write_text(env_content, encoding="utf-8")
    print(f"[+] Initialized backend/.env with local demo database")

if not os.environ.get("ANVEXA_DATABASE_URL"):
    os.environ["ANVEXA_DATABASE_URL"] = f"sqlite:///{demo_db_path}"

from backend.app.core.config import get_settings
from backend.app.database.connection import get_engine
from backend.app.database.session import SessionLocal
from backend.app.database.base import Base
import backend.app.models  # Register all SQLAlchemy models
from backend.app.models.enums import UserRole, DocumentStatus, ReportFormat
from backend.app.models.user import User
from backend.app.models.document import Document
from backend.app.core.security import hash_password
from backend.app.services.document_service import get_storage_backend
from backend.app.services.verification_engine.pipeline import run_verification_pipeline
from backend.app.services.report_generator.generator import generate_verification_report


def seed():
    print("=" * 60)
    print("ANVEXA AI — Seeding Sample Verified Manuscript")
    print("=" * 60)

    # 1. Initialize Tables
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print("[+] Database schema verified and initialized.")

    db = SessionLocal()
    settings = get_settings()
    storage = get_storage_backend(settings)

    try:
        # 2. Create or get Demo User
        user = db.query(User).filter(User.email == "demo@anvexa.ai").first()
        if not user:
            user = User(
                email="demo@anvexa.ai",
                full_name="Team Code Nova",
                hashed_password=hash_password("DemoPassword123!"),
                role=UserRole.USER,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[+] Created Demo User: {user.email}")
        else:
            print(f"[*] Found Existing Demo User: {user.email}")

        # 3. Sample Academic Manuscript Content
        sample_pdf_text = (
            b"%PDF-1.4\n"
            b"Section 1. Introduction.\n"
            b"Recent advances in neural representation learning achieved 95% accuracy in claim extraction [1].\n"
            b"The experimental clinical treatment demonstrated a 40% reduction in disease recurrence (p < 0.001) [1].\n"
            b"However, earlier epidemiological investigations claimed an association between MMR vaccines and autism [2].\n"
            b"Algorithm A consistently outperformed conventional baselines across all benchmark datasets [1].\n"
            b"Between 2018 and 2022, clinical adoption increased significantly across medical centers.\n"
            b"References\n"
            b"[1] Vaswani, A. et al. Attention is All You Need. NeurIPS 2017. doi: 10.1038/nature14539\n"
            b"[2] Wakefield, A. et al. Retracted Ileal-lymphoid-nodular hyperplasia. Lancet 1998. doi: 10.1016/s0140-6736(97)11096-0\n"
            b"%%EOF"
        )

        content_hash = hashlib.sha256(sample_pdf_text).hexdigest()
        storage_key = "demo_manuscript.pdf"
        storage.save(storage_key, sample_pdf_text)

        # 4. Create Document Record if not exists
        doc = db.query(Document).filter(Document.user_id == user.id, Document.file_hash == content_hash).first()
        if not doc:
            doc = Document(
                user_id=user.id,
                title="Advancements in Neural Verification & Empirical Therapeutics",
                filename="neural_verification_paper.pdf",
                storage_path=storage_key,
                file_hash=content_hash,
                file_type="application/pdf",
                file_size=len(sample_pdf_text),
                processing_status=DocumentStatus.UPLOADED,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            print(f"[+] Created Manuscript Document ID: {doc.id}")
        else:
            print(f"[*] Found Existing Manuscript Document ID: {doc.id}")

        # 5. Run Verification Pipeline
        print("\n[*] Executing 6-Step Verification Pipeline...")
        run_verification_pipeline(document_id=doc.id, user_id=user.id, db=db, storage=storage, settings=settings)
        print("[+] Verification Pipeline Completed Successfully!")

        # 6. Generate PDF and CSV Reports
        print("\n[*] Generating Audit Reports...")
        csv_rep = generate_verification_report(doc.id, user.id, ReportFormat.CSV, db, storage, settings)
        pdf_rep = generate_verification_report(doc.id, user.id, ReportFormat.PDF, db, storage, settings)
        print(f"[+] Generated CSV Audit Report: {csv_rep.id}")
        print(f"[+] Generated PDF Audit Certificate: {pdf_rep.id}")

        print("\n" + "=" * 60)
        print("SEEDING COMPLETE!")
        print("Demo User Credentials:")
        print("  Email:    demo@anvexa.ai")
        print("  Password: DemoPassword123!")
        print("Access Web Dashboard: http://127.0.0.1:8000/")
        print("Access API Docs:      http://127.0.0.1:8000/docs")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    seed()
