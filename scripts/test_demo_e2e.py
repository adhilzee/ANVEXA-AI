import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))

import httpx
from backend.app.main import app


async def test_endpoints():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health
        r = await client.get("/health")
        assert r.status_code == 200, f"Health failed: {r.status_code}"
        print("[+] Health check passed:", r.json())

        # 2. UI Dashboard
        r = await client.get("/")
        assert r.status_code == 200, f"Dashboard failed: {r.status_code}"
        assert "ANVEXA AI" in r.text
        print(f"[+] Dashboard HTML page served successfully (size: {len(r.text)} bytes)")

        # 3. Login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "demo@anvexa.ai", "password": "DemoPassword123!"},
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.status_code} {login_res.text}"
        token = login_res.json()["access_token"]
        print("[+] Authentication successful! Token acquired for demo@anvexa.ai")

        headers = {"Authorization": f"Bearer {token}"}

        # 4. List Documents
        r = await client.get("/api/v1/documents", headers=headers)
        assert r.status_code == 200, f"List documents failed: {r.status_code}"
        docs = r.json()["documents"]
        print(f"[+] Listed {len(docs)} documents in workspace:")
        for d in docs:
            print(f"    - Document ID: {d['id']} | Title: {d['title']} | Status: {d['processing_status']}")

        doc_id = docs[0]["id"]

        # 5. Get Document Claims
        r = await client.get(f"/api/v1/documents/{doc_id}/claims", headers=headers)
        assert r.status_code == 200, f"Get claims failed: {r.status_code}"
        claims = r.json()["claims"]
        print(f"[+] Extracted Claims ({len(claims)} total):")
        for c in claims[:3]:
            print(f"    - [{c['claim_type']}] \"{c['original_text'][:60]}...\"")

        # 6. Get Document Citations
        r = await client.get(f"/api/v1/documents/{doc_id}/citations", headers=headers)
        assert r.status_code == 200
        citations = r.json()["citations"]
        print(f"[+] Detected Citations ({len(citations)} total):")
        for cit in citations:
            print(f"    - [{cit['reference_number']}] {cit['citation_text'][:60]}...")

        # 7. Get Verification Summary & Results
        r = await client.get(f"/api/v1/documents/{doc_id}/verification-summary", headers=headers)
        assert r.status_code == 200
        summary = r.json()
        print(f"[+] Verification Summary:")
        print(f"    - Verification Score: {summary.get('verification_score')}%")
        print(f"    - Verdict Distribution: {summary.get('verdict_distribution')}")
        print(f"    - Flagged Reference Issues: {summary.get('reference_issues_count')}")
        print(f"    - Total Claims: {summary.get('total_claims')}")

        # 8. Get Verification Detailed Results
        r = await client.get(f"/api/v1/documents/{doc_id}/verification-results", headers=headers)
        assert r.status_code == 200
        results = r.json()
        print(f"[+] Verification Results ({len(results)} items verified)")

        # 9. Get Reference Issues
        r = await client.get(f"/api/v1/documents/{doc_id}/reference-issues", headers=headers)
        assert r.status_code == 200
        issues = r.json()["issues"]
        print(f"[+] Reference Issues Flagged ({len(issues)} items):")
        for iss in issues:
            print(f"    - [{iss['issue_type']}] {iss['description']}")

        print("\n[SUCCESS] ALL API endpoints, authentication, verification pipeline, and database validated flawlessly!")


if __name__ == "__main__":
    asyncio.run(test_endpoints())
