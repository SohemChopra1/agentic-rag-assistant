"""
Unit tests for app.agent.loop.run_agent, using a fake Anthropic client so
the orchestration logic (message threading, tool dispatch, loop
termination) is verified without needing network access or a real API key.
"""
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

import app.agent.loop as loop_module
from app.agent.loop import MAX_TURNS, run_agent


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

    with patch("app.agent.loop.execute_retrieve_docs", return_value="[Dietary Guidelines] 1.2-1.6 g/kg") as mock_retrieve, patch(
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
    tool_result_content = second_call_messages[-1]["content"][0]["content"]
    assert tool_result_content == "Unknown tool: not_a_real_tool"


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
