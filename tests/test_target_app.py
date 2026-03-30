import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'target-app'))

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_memory_endpoint_default(client):
    """GET /memory with no params allocates 20MB and returns JSON."""
    resp = client.get("/memory")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["allocated_mb"] == 20
    assert data["held_s"] == 0  # patched to 0 in tests


def test_memory_endpoint_custom_mb(client):
    """GET /memory?mb=50 allocates 50MB."""
    resp = client.get("/memory?mb=50")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["allocated_mb"] == 50


def test_memory_endpoint_cap(client):
    """GET /memory?mb=9999 is capped at 100MB."""
    resp = client.get("/memory?mb=9999")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["allocated_mb"] == 100


def test_memory_endpoint_invalid(client):
    """GET /memory?mb=abc returns 400."""
    resp = client.get("/memory?mb=abc")
    assert resp.status_code == 400


def test_memory_endpoint_negative_mb(client):
    """GET /memory?mb=-50 is clamped to 1MB minimum."""
    resp = client.get("/memory?mb=-50")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["allocated_mb"] == 1
