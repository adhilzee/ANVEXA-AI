import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))

import httpx
from backend.app.main import app


async def test_report_export():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        lr = await client.post(
            "/api/v1/auth/login",
            json={"email": "demo@anvexa.ai", "password": "DemoPassword123!"},
        )
        token = lr.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        docs = (await client.get("/api/v1/documents", headers=headers)).json()["documents"]
        doc_id = docs[0]["id"]
        fname = docs[0]["filename"]
        print(f"[+] Document ID: {doc_id} ({fname})")

        # 1. Generate Report
        post_pdf = await client.post(
            f"/api/v1/documents/{doc_id}/reports",
            headers=headers,
            json={"format": "pdf"},
        )
        print(f"[+] POST report status: {post_pdf.status_code}")
        rep = post_pdf.json()
        rep_id = rep["id"]
        print(f"[+] Report created ID: {rep_id} | Format: {rep['format']}")

        # 2. Download WITHOUT auth (no header and no query param)
        dl_unauth = await client.get(f"/api/v1/reports/{rep_id}/download")
        print(f"[+] Download without auth correctly rejected: {dl_unauth.status_code}")
        assert dl_unauth.status_code == 401

        # 3. Download WITH query param token (simulating direct link click / browser navigation)
        dl_query = await client.get(f"/api/v1/reports/{rep_id}/download?token={token}")
        print(f"[+] Download WITH ?token= query param status: {dl_query.status_code} | Bytes: {len(dl_query.content)}")
        assert dl_query.status_code == 200

        # 4. Download WITH Bearer header
        dl_auth = await client.get(f"/api/v1/reports/{rep_id}/download", headers=headers)
        print(f"[+] Download WITH Bearer header status: {dl_auth.status_code} | Bytes: {len(dl_auth.content)}")
        assert dl_auth.status_code == 200


if __name__ == "__main__":
    asyncio.run(test_report_export())
