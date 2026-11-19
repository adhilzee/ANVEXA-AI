import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))

import httpx
from backend.app.main import app


async def test_sample_uploads():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "demo@anvexa.ai", "password": "DemoPassword123!"},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        sample_dir = root_dir / "sample_papers"
        files_to_test = [
            ("sample_biomedical_verification_paper.pdf", "application/pdf"),
            ("clinical_oncology_immunotherapy_trial.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("direct_air_carbon_capture_review.pdf", "application/pdf"),
        ]

        for fname, mime in files_to_test:
            fpath = sample_dir / fname
            data = fpath.read_bytes()
            print(f"\n[*] Uploading: {fname} ({len(data)} bytes)...")

            files = {"file": (fname, data, mime)}
            up_res = await client.post("/api/v1/documents/upload", headers=headers, files=files)

            if up_res.status_code == 409:
                print(f"    [i] Already uploaded previously (duplicate detection working).")
                # Retrieve existing document ID
                docs = (await client.get("/api/v1/documents", headers=headers)).json()["documents"]
                doc = next(d for d in docs if d["filename"] == fname)
                doc_id = doc["id"]
            else:
                assert up_res.status_code == 201, f"Upload failed: {up_res.status_code} {up_res.text}"
                doc_id = up_res.json()["id"]
                print(f"    [+] Successfully uploaded! Document ID: {doc_id}")

            # Verify
            print(f"[*] Triggering verification for {doc_id}...")
            v_res = await client.post(f"/api/v1/documents/{doc_id}/verify", headers=headers)
            assert v_res.status_code == 202, f"Verification failed: {v_res.status_code} {v_res.text}"

            # Summary
            s_res = await client.get(f"/api/v1/documents/{doc_id}/verification-summary", headers=headers)
            summary = s_res.json()
            print(f"    [+] Verification Score: {summary['verification_score']}%")
            print(f"    [+] Claims Extracted: {summary['total_claims']}")
            print(f"    [+] Verdict Distribution: {summary['verdict_distribution']}")
            print(f"    [+] Reference Issues Flagged: {summary['reference_issues_count']}")

    print("\n[SUCCESS] All 3 sample demonstration papers uploaded and verified cleanly!")


if __name__ == "__main__":
    asyncio.run(test_sample_uploads())
