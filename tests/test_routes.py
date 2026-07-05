"""Request-level tests. R2 is monkeypatched so nothing touches the network."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def _png_bytes(w: int, h: int, color=(10, 120, 220, 255)) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


# --- early-return paths (no R2 access) -------------------------------------
def test_rejects_non_get_methods(client):
    resp = client.post("/cafes/abc/cover.jpg")
    assert resp.status_code == 405


def test_404s_path_traversal(client):
    resp = client.get("/..%2f..%2fsecret.jpg")
    assert resp.status_code == 404


def test_404s_direct_watermark_request(client):
    resp = client.get("/watermark.png")
    assert resp.status_code == 404


def test_404s_empty_key(client):
    resp = client.get("/")
    assert resp.status_code == 404


# --- full pipeline ----------------------------------------------------------
def test_404s_missing_object(client, monkeypatch):
    monkeypatch.setattr(main.r2, "get_object", lambda key: None)
    resp = client.get("/does/not/exist.jpg")
    assert resp.status_code == 404


def test_renders_resized_watermarked_webp(client, monkeypatch):
    source = _png_bytes(800, 600)
    watermark = _png_bytes(200, 80, color=(255, 255, 255, 255))
    monkeypatch.setattr(main.r2, "get_object", lambda key: source)
    monkeypatch.setattr(main.watermark_cache, "get", lambda: watermark)

    resp = client.get("/cafes/abc/cover.jpg", params={"w": 400})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert "immutable" in resp.headers["cache-control"]
    assert resp.headers["etag"]

    out = Image.open(BytesIO(resp.content))
    assert out.width == 400  # scaled down to the requested width
    assert out.height == 300  # aspect ratio preserved


def test_etag_revalidation_returns_304(client, monkeypatch):
    source = _png_bytes(400, 300)
    watermark = _png_bytes(100, 40)
    monkeypatch.setattr(main.r2, "get_object", lambda key: source)
    monkeypatch.setattr(main.watermark_cache, "get", lambda: watermark)

    first = client.get("/cafes/abc/cover.jpg", params={"w": 200})
    etag = first.headers["etag"]

    second = client.get(
        "/cafes/abc/cover.jpg", params={"w": 200}, headers={"If-None-Match": etag}
    )
    assert second.status_code == 304


def test_bypass_skips_watermark_and_marks_cache_key(client, monkeypatch):
    source = _png_bytes(300, 300)
    monkeypatch.setattr(main.settings, "watermark_bypass", "logos/")

    captured = {}

    def fake_get(key):
        captured.setdefault("keys", []).append(key)
        return source

    monkeypatch.setattr(main.r2, "get_object", fake_get)

    resp = client.get("/logos/brand.png", params={"format": "png"})
    assert resp.status_code == 200
    # watermark object must NOT be fetched for a bypassed path
    assert main.settings.watermark_key not in captured["keys"]
