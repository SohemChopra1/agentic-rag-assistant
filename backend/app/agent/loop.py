"""
Hand-rolled ReAct agent loop using Anthropic's native tool-use API directly
(no LangChain/LangGraph). Runs up to MAX_TURNS model calls, executing any
tool_use blocks in between, until the model returns a final text answer.

A tool that fails mid-loop (Voyage timeout or rate limit, DB hiccup) does
not abort the request: the error goes back to the model as a tool_result
with is_error=True, which is how the Messages API expects tool failures to
be reported. The model can then retry, use the other tool, or tell the
user the knowledge base is unavailable, instead of the whole /ask call
dying as an unhandled 500. Misconfiguration (missing API keys) is
different: it can't succeed on retry, so it is still raised up front.

The loop is written once, as an event generator (agent_events), and both
endpoints consume it:
  - /ask        collects the events into one JSON response (run_agent)
  - /ask/stream forwards each event over SSE as it happens
Events, in the order they can occur:
  tool_call   {"type", "id", "tool", "input"}            before a tool runs
  tool_result {"type", "id", "tool", "output", "is_error"} after it runs;
              retrieve_docs results also carry "sources": the structured
              chunks behind `output` (title, section, citation_url,
              content, distance), so clients never parse the model text
  answer      {"type", "text", "completed"}               always last
`completed` is False only when MAX_TURNS ran out before a final answer.
"""
import logging
from collections.abc import Iterator

from anthropic import Anthropic

from app.agent.tools import ALL_TOOLS, execute_calculate, format_passages, search_knowledge_base
from app.config import settings
from app.retrieval.embed import EmbeddingClient

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
MAX_TURNS = 5

SYSTEM_PROMPT = """You are a fitness and nutrition assistant backed by a knowledge base of \
CDC, NIH, NIA, and USDA/HHS Dietary Guidelines content.

Rules:
- For any factual claim, guideline, or recommendation, call retrieve_docs \
rather than answering from general knowledge.
- For any arithmetic (applying a guideline to a specific number the user \
gave, e.g. grams-per-kg times body weight), call calculate rather than \
doing the math yourself.
- Chain tools when a question needs both: retrieve the guideline, then \
calculate the number for the user's specifics.
- Always cite sources when you used retrieve_docs.
- If the knowledge base doesn't have what you need, say so plainly rather \
than filling the gap from general knowledge.
"""


FALLBACK_ANSWER = "I wasn't able to reach a final answer within the allotted reasoning steps."


class AgentResult:
    def __init__(self, answer: str, tool_calls: list[dict], events: list[dict] | None = None):
        self.answer = answer
        self.tool_calls = tool_calls
        # full trace including tool outputs (retrieved chunks), for evaluation
        self.events = events or []


def agent_events(db, user_query: str) -> Iterator[dict]:
    """Validate config and build clients NOW, then return a lazy iterator.

    The split matters for streaming: once an SSE response has started, its
    200 status is already sent, so a missing API key discovered inside the
    stream could only be reported as an in-band error event. Raising here,
    before the response starts, lets /ask/stream return a real 503 exactly
    like /ask does.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — required to run the agent")

    client = Anthropic(api_key=settings.anthropic_api_key)
    embedding_client = EmbeddingClient()  # raises RuntimeError if VOYAGE_API_KEY is missing
    return _run_loop(client, embedding_client, db, user_query)


def _run_loop(client, embedding_client, db, user_query: str) -> Iterator[dict]:
    messages = [{"role": "user", "content": user_query}]

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            text = "".join(block.text for block in response.content if block.type == "text")
            yield {"type": "answer", "text": text, "completed": True}
            return

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            yield {"type": "tool_call", "id": block.id, "tool": block.name, "input": block.input}

            result_text, is_error, sources = _execute_tool(db, embedding_client, block)
            event = {"type": "tool_result", "id": block.id, "tool": block.name, "output": result_text, "is_error": is_error}
            if sources is not None:
                event["sources"] = sources
            yield event

            tool_result = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            if is_error:
                tool_result["is_error"] = True
            tool_results.append(tool_result)

        messages.append({"role": "user", "content": tool_results})

    yield {"type": "answer", "text": FALLBACK_ANSWER, "completed": False}


def _execute_tool(db, embedding_client, block) -> tuple[str, bool, list[dict] | None]:
    """Returns (text for the model, is_error, structured sources or None)."""
    try:
        if block.name == "retrieve_docs":
            sources = search_knowledge_base(db, embedding_client, block.input["query"])
            return format_passages(sources), False, sources
        if block.name == "calculate":
            return execute_calculate(block.input["expression"]), False, None
        return f"Unknown tool: {block.name}", True, None
    except Exception as e:  # noqa: BLE001 — reported to the model, logged for us
        logger.exception("Tool %s failed", block.name)
        # a failed DB statement leaves the session unusable until rolled back
        db.rollback()
        return f"Tool {block.name} failed: {type(e).__name__}: {e}", True, None


def run_agent(db, user_query: str) -> AgentResult:
    """Non-streaming entry point: run the loop to completion and collect it."""
    events = list(agent_events(db, user_query))
    tool_calls = [{"tool": e["tool"], "input": e["input"]} for e in events if e["type"] == "tool_call"]
    answer = next(e["text"] for e in events if e["type"] == "answer")
    return AgentResult(answer=answer, tool_calls=tool_calls, events=events)
