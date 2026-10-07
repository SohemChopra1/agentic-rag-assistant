"""
Hand-rolled ReAct agent loop using Anthropic's native tool-use API directly
(no LangChain/LangGraph). Runs up to MAX_TURNS model calls, executing any
tool_use blocks in between, until the model returns a final text answer.
"""
from anthropic import Anthropic

from app.config import settings
from app.agent.tools import ALL_TOOLS, execute_calculate, execute_retrieve_docs
from app.retrieval.embed import EmbeddingClient

MODEL = "claude-sonnet-5"
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

            if block.name == "retrieve_docs":
                result_text = execute_retrieve_docs(db, embedding_client, block.input["query"])
            elif block.name == "calculate":
                result_text = execute_calculate(block.input["expression"])
            else:
                result_text = f"Unknown tool: {block.name}"

            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            )

        messages.append({"role": "user", "content": tool_results})

    return AgentResult(
        answer="I wasn't able to reach a final answer within the allotted reasoning steps.",
        tool_calls=tool_calls_made,
    )
