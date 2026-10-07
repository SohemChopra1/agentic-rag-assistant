"""
Tool definitions (Claude tool-use JSON schemas) and the execution logic
behind each one.

retrieve_docs hits the same retrieval stack as /retrieve (embed query via
Voyage, cosine-similarity search over pgvector) and formats results as
plain text blocks the model can cite from.

calculate evaluates a numeric expression WITHOUT Python's eval() — only a
restricted AST walk that permits numeric literals and +-*/** is allowed.
This matters because the expression ultimately originates from model
output, which can itself be influenced by retrieved document content
(prompt injection): a real eval() would turn a malicious chunk of text
into arbitrary code execution. _safe_eval explicitly rejects Call, Name,
list/set/dict comprehensions, strings, and booleans — anything other than
numeric literals and the allowed binary/unary operators raises ValueError.

Blocking code execution isn't enough on its own: pure arithmetic can still
be a denial of service. Python ints are arbitrary-precision, so '9**9**9'
is a legal numeric expression that tries to build a ~370-million-digit
number and pins a worker thread for minutes. Three bounds close that:
  - MAX_EXPRESSION_CHARS caps input length (and so AST depth/size)
  - every Pow is checked BEFORE it is computed: the result's magnitude is
    estimated as |exponent| * log10(|base|) and rejected if it would exceed
    MAX_MAGNITUDE, so the expensive number is never built
  - every intermediate result is checked against MAX_MAGNITUDE (this also
    catches float overflow to inf), so repeated multiplication can't
    escalate either
1e15 is far beyond any real fitness/nutrition calculation (grams, kcal,
minutes) while keeping every operation on small numbers.
"""
import ast
import math
import operator

from sqlalchemy.orm import Session

from app.retrieval.embed import EmbeddingClient
from app.retrieval.search import get_query_embedding, search_chunks

RETRIEVE_DOCS_TOOL = {
    "name": "retrieve_docs",
    "description": (
        "Search the fitness/nutrition knowledge base (CDC, NIH, NIA, and "
        "USDA/HHS Dietary Guidelines content) for passages relevant to a "
        "query. Use this for any factual claim, guideline, or recommendation "
        "— do not answer from general knowledge when this tool can confirm "
        "or correct it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A focused search query, e.g. 'protein intake for adults'.",
            },
        },
        "required": ["query"],
    },
}

CALCULATE_TOOL = {
    "name": "calculate",
    "description": (
        "Evaluate a numeric arithmetic expression, e.g. '80 * 1.6' or "
        "'(150 + 200) / 2'. Use this for any arithmetic rather than doing "
        "the math yourself — especially when applying a retrieved "
        "guideline (e.g. grams-per-kg) to a specific number the user gave."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A numeric expression using +, -, *, /, ** and parentheses only.",
            },
        },
        "required": ["expression"],
    },
}

ALL_TOOLS = [RETRIEVE_DOCS_TOOL, CALCULATE_TOOL]


_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


MAX_EXPRESSION_CHARS = 200
MAX_MAGNITUDE = 1e15


def _check_magnitude(value: float) -> float:
    if isinstance(value, complex):
        # e.g. (-8) ** 0.5 — not a meaningful answer for this domain
        raise ValueError("Result is not a real number")
    if math.isnan(value) or math.isinf(value) or abs(value) > MAX_MAGNITUDE:
        raise ValueError(f"Result magnitude exceeds limit of {MAX_MAGNITUDE:g}")
    return value


def _check_pow_bounds(base: float, exponent: float) -> None:
    """Reject a Pow whose result would be huge, without computing it."""
    if base == 0 or abs(base) == 1:
        return  # 0**n, 1**n and (-1)**n stay small for any exponent
    estimated_log10 = exponent * math.log10(abs(base))
    if estimated_log10 > math.log10(MAX_MAGNITUDE):
        raise ValueError(f"Result magnitude exceeds limit of {MAX_MAGNITUDE:g}")


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"Disallowed constant: {node.value!r}")
        return _check_magnitude(node.value)

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINOPS:
            raise ValueError(f"Disallowed operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if op_type is ast.Pow:
            _check_pow_bounds(left, right)
        return _check_magnitude(_ALLOWED_BINOPS[op_type](left, right))

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARYOPS:
            raise ValueError(f"Disallowed operator: {op_type.__name__}")
        return _ALLOWED_UNARYOPS[op_type](_safe_eval(node.operand))

    raise ValueError(f"Disallowed expression element: {type(node).__name__}")


def execute_calculate(expression: str) -> str:
    if len(expression) > MAX_EXPRESSION_CHARS:
        return f"Error evaluating expression: longer than {MAX_EXPRESSION_CHARS} characters"
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:  # noqa: BLE001 — surfaced to the model as tool output, not raised
        return f"Error evaluating expression: {e}"


def execute_retrieve_docs(
    db: Session, embedding_client: EmbeddingClient, query: str, top_k: int = 5
) -> str:
    query_embedding = get_query_embedding(embedding_client, query)
    results = search_chunks(db, query_embedding, top_k=top_k)

    if not results:
        return "No relevant documents found in the knowledge base."

    blocks = []
    for r in results:
        section = f" — {r['section']}" if r.get("section") else ""
        source = r.get("citation_url") or r.get("title")
        blocks.append(f"[{r['title']}{section}]\n{r['content']}\nSource: {source}")
    return "\n\n".join(blocks)
