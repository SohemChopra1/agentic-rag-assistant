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
"""
import logging

from anthropic import Anthropic

from app.agent.tools import ALL_TOOLS, execute_calculate, execute_retrieve_docs
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


class AgentResult:
    def __init__(self, answer: str, tool_calls: list[dict]):
        self.answer = answer
        self.tool_calls = tool_calls


def run_agent(db, user_query: str) -> AgentResult:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — required to run the agent")

    client = Anthropic(api_key=settings.anthropic_api_key)
    embedding_client = EmbeddingClient()

    messages = [{"role": "user", "content": user_query}]
    tool_calls_made: list[dict] = []

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
            return AgentResult(answer=text, tool_calls=tool_calls_made)

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_calls_made.append({"tool": block.name, "input": block.input})

            is_error = False
            try:
                if block.name == "retrieve_docs":
                    result_text = execute_retrieve_docs(db, embedding_client, block.input["query"])
                elif block.name == "calculate":
                    result_text = execute_calculate(block.input["expression"])
                else:
                    result_text = f"Unknown tool: {block.name}"
                    is_error = True
            except Exception as e:  # noqa: BLE001 — reported to the model, logged for us
                logger.exception("Tool %s failed", block.name)
                # a failed DB statement leaves the session unusable until rolled back
                db.rollback()
                result_text = f"Tool {block.name} failed: {type(e).__name__}: {e}"
                is_error = True

            tool_result = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            if is_error:
                tool_result["is_error"] = True
            tool_results.append(tool_result)

        messages.append({"role": "user", "content": tool_results})

    return AgentResult(
        answer="I wasn't able to reach a final answer within the allotted reasoning steps.",
        tool_calls=tool_calls_made,
    )
