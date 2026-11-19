from __future__ import annotations

import asyncio
import io
from typing import Iterator
import uuid

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token, hash_password, rate_limiter
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import create_app
from backend.app.models.enums import UserRole
from backend.app.models.user import User
from backend.app.services.document_service import reset_storage_backend, set_storage_backend
from backend.app.services.document_storage.storage_service import StorageBackend


class PipelineMockStorage(StorageBackend):
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> str:
        self.files[key] = data
        return key

    def read(self, key: str) -> bytes:
        if key not in self.files:
            raise FileNotFoundError(f"File {key} not found")
        return self.files[key]

    def delete(self, key: str) -> None:
        self.files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.files

    def get_path(self, key: str) -> str:
        return f"/mock/{key}"


@pytest.fixture(autouse=True)
def setup_settings(monkeypatch):
    monkeypatch.setenv(
        "ANVEXA_JWT_SECRET_KEY",
        "test-secret-key-for-testing-purposes-only-32bytes!",
    )
    get_settings.cache_clear()
    rate_limiter.reset_all()
    storage = PipelineMockStorage()
    set_storage_backend(storage)
    yield storage
    reset_storage_backend()
    get_settings.cache_clear()
    rate_limiter.reset_all()


@pytest.fixture
def pipeline_db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(conn, _rec):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        yield session

    engine.dispose()


@pytest.fixture
def test_app(pipeline_db_session: Session) -> FastAPI:
    application = create_app()

    def override_get_db():
        yield pipeline_db_session

    application.dependency_overrides[get_db] = override_get_db
    return application


def make_client_call(
    app: FastAPI,
    method: str,
    path: str,
    json: dict | None = None,
    headers: dict | None = None,
    files: dict | None = None,
) -> httpx.Response:
    async def run_call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json, headers=headers, files=files)

    return asyncio.run(run_call())


def test_end_to_end_verification_pipeline(
    test_app: FastAPI,
    pipeline_db_session: Session,
    setup_settings: PipelineMockStorage,
):
    storage = setup_settings

    # 1. Register test user
    reg_resp = make_client_call(
        test_app,
        "POST",
        "/api/v1/auth/register",
        json={
            "email": "scientist@anvexa.org",
            "password": "StrongPassword123!",
            "full_name": "Dr. Marie Curie",
        },
    )
    assert reg_resp.status_code == 201
    user_id = reg_resp.json()["id"]

    # 2. Login
    login_resp = make_client_call(
        test_app,
        "POST",
        "/api/v1/auth/login",
        json={"email": "scientist@anvexa.org", "password": "StrongPassword123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # 3. Create a test PDF paper with content, claims, and references
    pdf_content = (
        b"%PDF-1.4\n"
        b"Section 1. Introduction.\n"
        b"Recent neural network models achieved 95% accuracy in claim extraction [1].\n"
        b"However, earlier statistical approaches exhibited higher error rates [2].\n"
        b"References\n"
        b"[1] Smith, J. Deep Learning Verification. Nature 2021. doi: 10.1038/nature14539\n"
        b"[2] Wakefield, A. Measles Study. Lancet 1998. doi: 10.1016/s0140-6736(97)11096-0\n"
        b"%%EOF"
    )

    upload_resp = make_client_call(
        test_app,
        "POST",
        "/api/v1/documents/upload",
        headers=auth_header,
        files={"file": ("academic_paper.pdf", pdf_content, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    # 4. Trigger verification pipeline
    verify_resp = make_client_call(
        test_app,
        "POST",
        f"/api/v1/documents/{doc_id}/verify",
        headers=auth_header,
    )
    assert verify_resp.status_code == 202

    # 5. Check verification summary
    summary_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/documents/{doc_id}/verification-summary",
        headers=auth_header,
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_claims"] >= 1
    assert summary["verified_claims"] >= 1
    assert summary["status"] == "completed"

    # 6. Check processing jobs
    jobs_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/documents/{doc_id}/jobs",
        headers=auth_header,
    )
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json()
    assert len(jobs) >= 5

    # 7. Check claims endpoint
    claims_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/documents/{doc_id}/claims",
        headers=auth_header,
    )
    assert claims_resp.status_code == 200
    claims = claims_resp.json()["claims"]
    assert len(claims) >= 1
    first_claim_id = claims[0]["id"]

    # 8. Check claim details
    claim_detail_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/claims/{first_claim_id}",
        headers=auth_header,
    )
    assert claim_detail_resp.status_code == 200
    claim_detail = claim_detail_resp.json()
    assert "citation_links" in claim_detail

    # 9. Check citations and reference issues
    citations_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/documents/{doc_id}/citations",
        headers=auth_header,
    )
    assert citations_resp.status_code == 200
    assert len(citations_resp.json()["citations"]) >= 2

    issues_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/documents/{doc_id}/reference-issues",
        headers=auth_header,
    )
    assert issues_resp.status_code == 200
    issues = issues_resp.json()["issues"]
    # Wakefield paper is in KNOWN_RETRACTED_DOIS -> Retracted source issue detected
    assert any(i["issue_type"] == "retracted_source" for i in issues)

    # 10. Check verification results
    results_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/documents/{doc_id}/verification-results",
        headers=auth_header,
    )
    assert results_resp.status_code == 200
    results = results_resp.json()
    assert len(results) >= 1
    first_result_id = results[0]["id"]

    # 11. Generate CSV Report
    report_resp = make_client_call(
        test_app,
        "POST",
        f"/api/v1/documents/{doc_id}/reports",
        json={"format": "csv"},
        headers=auth_header,
    )
    assert report_resp.status_code == 201
    report_id = report_resp.json()["id"]

    # 12. Download report
    download_resp = make_client_call(
        test_app,
        "GET",
        f"/api/v1/reports/{report_id}/download",
        headers=auth_header,
    )
    assert download_resp.status_code == 200
    assert "ANVEXA AI" in download_resp.text

    # 13. Submit user feedback
    feedback_resp = make_client_call(
        test_app,
        "POST",
        "/api/v1/feedback",
        json={
            "claim_id": first_claim_id,
            "verification_result_id": first_result_id,
            "rating": 5,
            "comment": "Accurately caught the retracted reference!",
        },
        headers=auth_header,
    )
    assert feedback_resp.status_code == 201
    assert feedback_resp.json()["rating"] == 5
