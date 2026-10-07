from fastapi.testclient import TestClient
from voyageai.error import RateLimitError

from app.main import app

client = TestClient(app)


def test_retrieve_without_voyage_key_returns_clean_503(monkeypatch):
    monkeypatch.setattr("app.config.settings.voyage_api_key", "")
    response = client.post("/retrieve", json={"query": "how much protein do I need"})

    assert response.status_code == 503
    assert "VOYAGE_API_KEY" in response.json()["detail"]


def test_retrieve_returns_503_when_voyage_api_errors(monkeypatch):
    class FailingClient:
        def embed(self, texts, input_type):
            raise RateLimitError("rate limited")

    monkeypatch.setattr("app.retrieval.router.EmbeddingClient", FailingClient)
    response = client.post("/retrieve", json={"query": "how much protein do I need"})

    assert response.status_code == 503
    assert "Embedding service error" in response.json()["detail"]


def test_retrieve_validates_request_body():
    response = client.post("/retrieve", json={})  # missing required "query" field
    assert response.status_code == 422
