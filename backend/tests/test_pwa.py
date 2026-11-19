from __future__ import annotations

import json
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_pwa_manifest_endpoint(client: TestClient):
    # Test /manifest.json
    response = client.get("/manifest.json")
    assert response.status_code == 200
    assert "application/manifest+json" in response.headers.get("content-type", "")

    data = response.json()
    assert data["name"] == "ANVEXA AI — Academic Verification Platform"
    assert data["short_name"] == "ANVEXA AI"
    assert data["display"] == "standalone"
    assert data["start_url"] == "/?source=pwa"
    assert len(data["icons"]) >= 4

    # Test /manifest.webmanifest alias
    resp_alias = client.get("/manifest.webmanifest")
    assert resp_alias.status_code == 200


def test_pwa_service_worker_endpoint(client: TestClient):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers.get("content-type", "")
    assert response.headers.get("service-worker-allowed") == "/"
    content = response.text
    assert "CACHE_NAME" in content
    assert "self.addEventListener('install'" in content
    assert "self.addEventListener('fetch'" in content


def test_pwa_icons_served(client: TestClient):
    # Standard 192 icon
    r192 = client.get("/static/icons/icon-192.png")
    assert r192.status_code == 200
    assert r192.content.startswith(b"\x89PNG\r\n\x1a\n")

    # Maskable 192 icon
    r192m = client.get("/static/icons/icon-192-maskable.png")
    assert r192m.status_code == 200
    assert r192m.content.startswith(b"\x89PNG\r\n\x1a\n")

    # Standard 512 icon
    r512 = client.get("/static/icons/icon-512.png")
    assert r512.status_code == 200
    assert r512.content.startswith(b"\x89PNG\r\n\x1a\n")

    # Apple Touch Icon
    rapple = client.get("/static/icons/apple-touch-icon.png")
    assert rapple.status_code == 200
    assert rapple.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_dashboard_pwa_meta_tags(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Manifest link
    assert '<link rel="manifest" href="/manifest.json">' in html

    # Apple / iOS standalone tags
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in html
    assert '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">' in html
    assert '<meta name="apple-mobile-web-app-title" content="ANVEXA AI">' in html
    assert '<link rel="apple-touch-icon"' in html

    # Theme color
    assert '<meta name="theme-color" content="#4f46e5">' in html

    # PWA install button & service worker script
    assert 'id="pwa-install-btn"' in html
    assert 'navigator.serviceWorker.register' in html
    assert 'pwa-install-modal' in html
