"""
/ask endpoint tests — just the error-handling and validation surface
(missing API keys -> clean 503, bad request body -> 422). The actual
agent-loop orchestration is covered by test_agent_loop.py with a fake
Anthropic client; these just confirm the route wires it up correctly.
"""
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_ask_returns_503_when_anthropic_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    response = client.post("/ask", json={"query": "how much protein should I eat?"})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_ask_returns_503_when_voyage_key_missing(monkeypatch):
    # anthropic key present so run_agent gets past its own guard, but
    # EmbeddingClient() should still fail fast on the missing voyage key
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-anthropic-key")
    monkeypatch.setattr(settings, "voyage_api_key", "")

    response = client.post("/ask", json={"query": "how much protein should I eat?"})

    assert response.status_code == 503
    assert "VOYAGE_API_KEY" in response.json()["detail"]


def test_ask_rejects_missing_query_field():
    response = client.post("/ask", json={})
    assert response.status_code == 422
