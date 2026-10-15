"""
Unit tests for app.agent.loop.run_agent, using a fake Anthropic client so
the orchestration logic (message threading, tool dispatch, loop
termination) is verified without needing network access or a real API key.
"""
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

import app.agent.loop as loop_module
from app.agent.loop import FALLBACK_ANSWER, MAX_TURNS, agent_events, run_agent


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeResponse:
    content: list
    stop_reason: str


class FakeMessagesAPI:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


@dataclass
class FakeAnthropicClient:
    messages: FakeMessagesAPI


def _source(content, title="Dietary Guidelines for Americans, 2025-2030 (USDA/HHS)"):
    return {"content": content, "section": None, "title": title, "citation_url": "https://www.realfood.gov", "distance": 0.1}


def _patch_clients(monkeypatch, responses):
    fake_messages = FakeMessagesAPI(responses)
    fake_anthropic_client = FakeAnthropicClient(messages=fake_messages)

    monkeypatch.setattr(loop_module, "Anthropic", lambda api_key: fake_anthropic_client)
    monkeypatch.setattr(loop_module, "EmbeddingClient", lambda: MagicMock())
    # the RuntimeError guard at the top of run_agent fires on an empty key —
    # give it a non-empty fake one so the fake client is actually reached
    monkeypatch.setattr(loop_module.settings, "anthropic_api_key", "fake-key-for-orchestration-test")

    return fake_messages


def test_run_agent_returns_direct_answer_with_no_tool_use(monkeypatch):
    responses = [
        FakeResponse(content=[FakeTextBlock(text="Direct answer, no tools needed.")], stop_reason="end_turn")
    ]
    _patch_clients(monkeypatch, responses)

    result = run_agent(db=MagicMock(), user_query="what is exercise")

    assert result.answer == "Direct answer, no tools needed."
    assert result.tool_calls == []


def test_run_agent_calls_calculate_tool(monkeypatch):
    responses = [
        FakeResponse(
            content=[FakeToolUseBlock(id="t1", name="calculate", input={"expression": "80 * 1.6"})],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[FakeTextBlock(text="You need about 128g of protein.")], stop_reason="end_turn"),
    ]
    _patch_clients(monkeypatch, responses)

    with patch("app.agent.loop.execute_calculate", return_value="128.0") as mock_calc:
        result = run_agent(db=MagicMock(), user_query="80kg, how much protein at 1.6g/kg?")

    mock_calc.assert_called_once_with("80 * 1.6")
    assert result.answer == "You need about 128g of protein."
    assert result.tool_calls == [{"tool": "calculate", "input": {"expression": "80 * 1.6"}}]


def test_run_agent_chains_retrieve_then_calculate(monkeypatch):
    responses = [
        FakeResponse(
            content=[FakeToolUseBlock(id="t1", name="retrieve_docs", input={"query": "protein guideline"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[FakeToolUseBlock(id="t2", name="calculate", input={"expression": "80 * 1.6"})],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[FakeTextBlock(text="About 128g/day, per the Dietary Guidelines.")], stop_reason="end_turn"),
    ]
    _patch_clients(monkeypatch, responses)

    with patch("app.agent.loop.search_knowledge_base", return_value=[_source("1.2-1.6 g/kg")]) as mock_retrieve, patch(
        "app.agent.loop.execute_calculate", return_value="128.0"
    ) as mock_calc:
        result = run_agent(db=MagicMock(), user_query="how much protein for an 80kg person?")

    mock_retrieve.assert_called_once()
    mock_calc.assert_called_once_with("80 * 1.6")
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0]["tool"] == "retrieve_docs"
    assert result.tool_calls[1]["tool"] == "calculate"


def test_run_agent_handles_unknown_tool_name(monkeypatch):
    responses = [
        FakeResponse(
            content=[FakeToolUseBlock(id="t1", name="not_a_real_tool", input={})],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[FakeTextBlock(text="done")], stop_reason="end_turn"),
    ]
    fake_messages = _patch_clients(monkeypatch, responses)

    result = run_agent(db=MagicMock(), user_query="trigger unknown tool")

    assert result.answer == "done"
    # the fake tool result should have been threaded back in as a tool_result
    second_call_messages = fake_messages.calls[1]["messages"]
    tool_result = second_call_messages[-1]["content"][0]
    assert tool_result["content"] == "Unknown tool: not_a_real_tool"
    assert tool_result["is_error"] is True


def test_run_agent_reports_failing_tool_to_model_instead_of_crashing(monkeypatch):
    # e.g. a Voyage timeout during retrieve_docs: the request must not die
    # as a 500 — the model gets an is_error tool_result and can recover
    responses = [
        FakeResponse(
            content=[FakeToolUseBlock(id="t1", name="retrieve_docs", input={"query": "protein"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[FakeTextBlock(text="The knowledge base is unavailable right now.")], stop_reason="end_turn"
        ),
    ]
    fake_messages = _patch_clients(monkeypatch, responses)
    fake_db = MagicMock()

    with patch("app.agent.loop.search_knowledge_base", side_effect=ConnectionError("voyage timed out")):
        result = run_agent(db=fake_db, user_query="how much protein?")

    assert result.answer == "The knowledge base is unavailable right now."
    tool_result = fake_messages.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "ConnectionError" in tool_result["content"]
    assert "voyage timed out" in tool_result["content"]
    fake_db.rollback.assert_called_once()  # session left usable for later turns


def test_successful_tool_result_is_not_marked_as_error(monkeypatch):
    responses = [
        FakeResponse(
            content=[FakeToolUseBlock(id="t1", name="calculate", input={"expression": "2+2"})],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[FakeTextBlock(text="4")], stop_reason="end_turn"),
    ]
    fake_messages = _patch_clients(monkeypatch, responses)

    run_agent(db=MagicMock(), user_query="2+2")

    tool_result = fake_messages.calls[1]["messages"][-1]["content"][0]
    assert "is_error" not in tool_result


def test_agent_stops_at_max_turns_instead_of_looping_forever(monkeypatch):
    # the model keeps calling a tool forever and never returns end_turn —
    # the loop MUST terminate rather than hang
    responses = [
        FakeResponse(
            content=[FakeToolUseBlock(id=f"t{i}", name="calculate", input={"expression": "1+1"})],
            stop_reason="tool_use",
        )
        for i in range(MAX_TURNS)
    ]
    fake_messages = _patch_clients(monkeypatch, responses)

    with patch("app.agent.loop.execute_calculate", return_value="2"):
        result = run_agent(db=MagicMock(), user_query="never-ending tool use")

    assert result.answer == "I wasn't able to reach a final answer within the allotted reasoning steps."
    assert len(result.tool_calls) == MAX_TURNS
    assert len(fake_messages.calls) == MAX_TURNS


def test_run_agent_raises_runtime_error_without_api_key(monkeypatch):
    monkeypatch.setattr(loop_module.settings, "anthropic_api_key", "")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        run_agent(db=MagicMock(), user_query="anything")


# ---- agent_events: the event stream both endpoints consume -----------------


def _types(events):
    return [e["type"] for e in events]


def test_agent_events_direct_answer_is_a_single_answer_event(monkeypatch):
    _patch_clients(monkeypatch, [FakeResponse(content=[FakeTextBlock(text="hi")], stop_reason="end_turn")])

    events = list(agent_events(MagicMock(), "hello"))

    assert events == [{"type": "answer", "text": "hi", "completed": True}]


def test_agent_events_chained_run_emits_each_call_before_its_result(monkeypatch):
    responses = [
        FakeResponse(
            content=[FakeToolUseBlock(id="t1", name="retrieve_docs", input={"query": "protein"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[
                # two tool calls in ONE turn, as the live model did (80*1.2 and 80*1.6)
                FakeToolUseBlock(id="t2", name="calculate", input={"expression": "80 * 1.2"}),
                FakeToolUseBlock(id="t3", name="calculate", input={"expression": "80 * 1.6"}),
            ],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[FakeTextBlock(text="96-128 g/day")], stop_reason="end_turn"),
    ]
    _patch_clients(monkeypatch, responses)

    with patch("app.agent.loop.search_knowledge_base", return_value=[_source("1.2 to 1.6 grams")]):
        events = list(agent_events(MagicMock(), "80kg protein?"))

    assert _types(events) == ["tool_call", "tool_result"] * 3 + ["answer"]
    # each result is paired to its call by id, in order
    assert [e["id"] for e in events if e["type"] == "tool_call"] == ["t1", "t2", "t3"]
    assert [e["id"] for e in events if e["type"] == "tool_result"] == ["t1", "t2", "t3"]
    retrieve_result, calc_1, calc_2 = [e for e in events if e["type"] == "tool_result"]
    assert "1.2 to 1.6 grams" in retrieve_result["output"]  # formatted text the model reads
    assert retrieve_result["sources"] == [_source("1.2 to 1.6 grams")]  # structured, for UI/eval
    assert (calc_1["output"], calc_2["output"]) == ("96.0", "128.0")
    assert "sources" not in calc_1  # only retrieval results carry sources
    assert events[-1] == {"type": "answer", "text": "96-128 g/day", "completed": True}


def test_agent_events_marks_failed_tool_result_as_error(monkeypatch):
    responses = [
        FakeResponse(content=[FakeToolUseBlock(id="t1", name="retrieve_docs", input={"query": "x"})], stop_reason="tool_use"),
        FakeResponse(content=[FakeTextBlock(text="unavailable")], stop_reason="end_turn"),
    ]
    _patch_clients(monkeypatch, responses)

    with patch("app.agent.loop.search_knowledge_base", side_effect=TimeoutError("voyage")):
        events = list(agent_events(MagicMock(), "x"))

    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] is True
    assert "TimeoutError" in result["output"]


def test_agent_events_max_turns_ends_with_incomplete_answer(monkeypatch):
    responses = [
        FakeResponse(content=[FakeToolUseBlock(id=f"t{i}", name="calculate", input={"expression": "1+1"})], stop_reason="tool_use")
        for i in range(MAX_TURNS)
    ]
    _patch_clients(monkeypatch, responses)

    events = list(agent_events(MagicMock(), "loop forever"))

    assert events[-1] == {"type": "answer", "text": FALLBACK_ANSWER, "completed": False}


def test_agent_events_checks_keys_before_iteration_starts(monkeypatch):
    # must raise at call time, not on first next(): /ask/stream relies on
    # this to return a real 503 before the SSE response commits to 200
    monkeypatch.setattr(loop_module.settings, "anthropic_api_key", "")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        agent_events(MagicMock(), "anything")


def test_run_agent_keeps_full_event_trace_for_evaluation(monkeypatch):
    responses = [
        FakeResponse(content=[FakeToolUseBlock(id="t1", name="retrieve_docs", input={"query": "sleep"})], stop_reason="tool_use"),
        FakeResponse(content=[FakeTextBlock(text="7+ hours")], stop_reason="end_turn"),
    ]
    _patch_clients(monkeypatch, responses)

    with patch("app.agent.loop.search_knowledge_base", return_value=[_source("at least 7 hours")]):
        result = run_agent(MagicMock(), "sleep?")

    # the retrieved chunks are what Phase 7 scores retrieval relevance against
    (retrieve_result,) = [e for e in result.events if e["type"] == "tool_result"]
    assert [src["content"] for src in retrieve_result["sources"]] == ["at least 7 hours"]
