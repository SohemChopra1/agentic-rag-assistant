"""
/ask/stream tests: SSE wire format, event ordering, and the two error
phases (before the stream starts -> real HTTP status; during the stream ->
terminal `error` event). The agent loop itself is replaced with a canned
event list — its logic is covered in test_agent_loop.py.
"""
import json
from unittest.mock import MagicMock

import pytest
from anthropic import APIConnectionError
from fastapi.testclient import TestClient
from sse_starlette.sse import AppStatus

import app.agent.router as router_module
from app.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_sse_state():
    # sse-starlette keeps a module-level exit event bound to the event loop
    # that first created it; each TestClient request runs a new loop, so
    # without this reset the second streaming test fails with
    # "bound to a different event loop"
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


@pytest.fixture
def fake_session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: session)
    return session


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event_name, data) pairs, skipping pings."""
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line and not line.startswith(":"))
        if "event" in fields and fields["event"] != "ping":
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def _stream_with_events(monkeypatch, events_or_generator):
    monkeypatch.setattr(router_module, "agent_events", lambda db, query: iter(events_or_generator))
    return client.post("/ask/stream", json={"query": "how much protein for 80kg?"})


CANNED_RUN = [
    {"type": "tool_call", "id": "t1", "tool": "retrieve_docs", "input": {"query": "protein"}},
    {"type": "tool_result", "id": "t1", "tool": "retrieve_docs", "output": "1.2 to 1.6 grams", "is_error": False},
    {"type": "tool_call", "id": "t2", "tool": "calculate", "input": {"expression": "80 * 1.2"}},
    {"type": "tool_result", "id": "t2", "tool": "calculate", "output": "96.0", "is_error": False},
    {"type": "answer", "text": "About 96-128 g/day.", "completed": True},
]


def test_stream_sends_each_agent_event_in_order(monkeypatch, fake_session):
    response = _stream_with_events(monkeypatch, CANNED_RUN)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["tool_call", "tool_result", "tool_call", "tool_result", "answer"]
    # the SSE event name matches the payload's type, and payloads pass through unchanged
    assert [data for _, data in events] == CANNED_RUN


def test_stream_closes_its_db_session_when_done(monkeypatch, fake_session):
    _stream_with_events(monkeypatch, CANNED_RUN)
    fake_session.close.assert_called_once()


def test_stream_returns_503_before_streaming_when_anthropic_key_missing(monkeypatch, fake_session):
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    response = client.post("/ask/stream", json={"query": "anything"})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]
    fake_session.close.assert_called_once()  # not leaked on the early exit


def test_stream_returns_503_before_streaming_when_voyage_key_missing(monkeypatch, fake_session):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-anthropic-key")
    monkeypatch.setattr(settings, "voyage_api_key", "")

    response = client.post("/ask/stream", json={"query": "anything"})

    assert response.status_code == 503
    assert "VOYAGE_API_KEY" in response.json()["detail"]


def test_stream_ends_with_error_event_when_model_api_fails_midway(monkeypatch, fake_session):
    def failing_run():
        yield CANNED_RUN[0]
        yield CANNED_RUN[1]
        raise APIConnectionError(request=MagicMock())

    response = _stream_with_events(monkeypatch, failing_run())

    assert response.status_code == 200  # already committed when the failure happened
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["tool_call", "tool_result", "error"]
    assert events[-1][1]["message"].startswith("Model API error")
    fake_session.close.assert_called_once()


def test_stream_ends_with_error_event_on_unexpected_failure(monkeypatch, fake_session):
    def failing_run():
        yield CANNED_RUN[0]
        raise KeyError("boom")

    events = parse_sse(_stream_with_events(monkeypatch, failing_run()).text)

    assert events[-1] == ("error", {"type": "error", "message": "Unexpected error: KeyError"})


def test_stream_rejects_missing_query_field():
    response = client.post("/ask/stream", json={})
    assert response.status_code == 422
