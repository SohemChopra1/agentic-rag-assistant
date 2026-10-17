"""
Pure scoring functions for the agent eval — no network, no API keys, so
every rule here is unit tested (eval/test_scoring.py).

A "run" is what one query produced, collected from /ask/stream and
/retrieve by run_eval.py:
    {
      "tool_calls":   ["retrieve_docs", "calculate", ...],   # in call order
      "retrievals":   [[source, ...], ...],   # one list per retrieve_docs call
      "raw_retrieval": [source, ...],         # /retrieve on the user's exact words
      "answer": str, "completed": bool, "error": str | None, "latency_s": float,
    }
where each source is {"content", "title", "section", "citation_url", "distance"}.
"""
import re
from statistics import median

# ---- tool selection -------------------------------------------------------


def tools_match(expected: list[str], actual: list[str]) -> bool:
    """True if the expected tools appear in `actual` in order, as a subsequence.

    Repeats and extra calls don't fail a run: the live 80 kg question made
    [retrieve_docs, calculate, calculate] — one calculate per end of the
    range — which is correct, and exact list equality would score it wrong.
    Order still matters: [calculate, retrieve_docs] means the model did math
    before it had the guideline, which is the failure this metric exists for.
    """
    it = iter(actual)
    return all(any(tool == step for step in it) for tool in expected)


# ---- retrieval ------------------------------------------------------------


def first_match_rank(sources: list[dict], phrase: str) -> int | None:
    """1-based rank of the first source containing `phrase`, else None."""
    for rank, src in enumerate(sources, start=1):
        if phrase in src["content"]:
            return rank
    return None


def reciprocal_rank(sources: list[dict], phrase: str) -> float:
    rank = first_match_rank(sources, phrase)
    return 1.0 / rank if rank else 0.0


# ---- answers --------------------------------------------------------------


def normalize_numbers(text: str) -> str:
    """'1,920' -> '1920' so expected numbers match however they're formatted."""
    return re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", text)


def contains_number(text: str, number: str) -> bool:
    """Whole-number match: '20' matches '20 km', '20.0' and 'total: 20.'
    but not '2026', '120' or '20.5'."""
    pattern = rf"(?<![\d.]){re.escape(number)}(?:\.0+)?(?!\.?\d)"
    return re.search(pattern, normalize_numbers(text)) is not None


def answer_contains_all(answer: str, expected: list[str]) -> bool:
    return all(contains_number(answer, n) for n in expected)


# Heuristic: does the answer say the knowledge base can't answer this?
# Only scored on out_of_scope queries — in-scope answers legitimately note
# partial gaps (the live protein answer said the corpus doesn't cover where
# in the range to fall), which would be false positives there. Every answer
# is saved in the JSON report so a miss here can be audited by reading it.
_REFUSAL_PATTERNS = [
    # "the knowledge base doesn't cover...", "my sources do not include..."
    r"\b(knowledge base|sources?|documents?|guidelines|materials?|database)\b[^.]{0,80}?"
    r"\b(doesn't|does not|don't|do not|isn't|is not|aren't|are not|didn't|did not|lacks?|has no|have no|contains? no)\b",
    # "I couldn't find...", "I was unable to locate..."
    r"\b(couldn't|could not|can't|cannot|unable to|wasn't able to|was not able to|didn't|did not)\b[^.]{0,40}?\b(find|locate)\b",
    # "I don't have information on..."
    r"\b(don't|do not)\s+have\b[^.]{0,60}?\b(information|data|guidance|details|recommendations?)\b",
    # "there's no specific guidance on..."
    r"\bno\s+(relevant\s+|specific\s+)?(information|data|guidance|details|recommendations?)\b",
    r"\bnot\s+(covered|included|addressed|mentioned)\b",
]


def is_refusal(answer: str) -> bool:
    return any(re.search(p, answer, re.IGNORECASE) for p in _REFUSAL_PATTERNS)


# ---- per-query and aggregate scores ---------------------------------------


def score_run(query: dict, run: dict) -> dict:
    """Score one run. Metrics a query isn't labeled for are None (not counted)."""
    phrase = query.get("expected_source_contains")
    agent_sources = [src for call in run["retrievals"] for src in call]
    first_search = run["retrievals"][0] if run["retrievals"] else []

    return {
        "id": query["id"],
        "category": query["category"],
        "tools_ok": tools_match(query["expected_tools"], run["tool_calls"]),
        # did ANY of the agent's searches surface the passage?
        "hit": (first_match_rank(agent_sources, phrase) is not None) if phrase else None,
        # how high was it in the agent's FIRST search (its own query wording)?
        "rr": reciprocal_rank(first_search, phrase) if phrase else None,
        # same, but searching with the user's exact words — the retriever alone
        "raw_hit": (first_match_rank(run["raw_retrieval"], phrase) is not None) if phrase else None,
        "raw_rr": reciprocal_rank(run["raw_retrieval"], phrase) if phrase else None,
        "answer_ok": answer_contains_all(run["answer"], query["expected_answer_contains"])
        if query.get("expected_answer_contains")
        else None,
        "refused": is_refusal(run["answer"]) if query.get("expected_refusal") else None,
        "completed": run["completed"] and run["error"] is None,
        "n_tool_calls": len(run["tool_calls"]),
        "latency_s": run["latency_s"],
    }


def _rate(values: list) -> dict | None:
    scored = [v for v in values if v is not None]
    if not scored:
        return None
    total = sum(scored)
    return {"value": total / len(scored), "n": len(scored), "sum": total}


def aggregate(scores: list[dict]) -> dict:
    latencies = sorted(s["latency_s"] for s in scores)
    p95_index = max(0, round(0.95 * len(latencies)) - 1)
    return {
        "runs": len(scores),
        "tool_selection_accuracy": _rate([s["tools_ok"] for s in scores]),
        "retrieval_hit_rate_at_5": _rate([s["hit"] for s in scores]),
        "mrr_first_search": _rate([s["rr"] for s in scores]),
        "raw_query_hit_rate_at_5": _rate([s["raw_hit"] for s in scores]),
        "raw_query_mrr": _rate([s["raw_rr"] for s in scores]),
        "answer_accuracy": _rate([s["answer_ok"] for s in scores]),
        "refusal_accuracy": _rate([s["refused"] for s in scores]),
        "completion_rate": _rate([s["completed"] for s in scores]),
        "mean_tool_calls": sum(s["n_tool_calls"] for s in scores) / len(scores),
        "median_latency_s": median(latencies),
        "p95_latency_s": latencies[p95_index],
    }


# ---- report formatting ----------------------------------------------------

_ROWS = [
    ("tool_selection_accuracy", "Tool selection accuracy", "expected tools called, in order"),
    ("retrieval_hit_rate_at_5", "Retrieval hit rate @5", "labeled passage in any agent search's top 5"),
    ("mrr_first_search", "MRR, agent's first search", "1/rank of the labeled passage"),
    ("raw_query_hit_rate_at_5", "Hit rate @5, user's raw words", "retriever alone, no agent rewriting"),
    ("raw_query_mrr", "MRR, user's raw words", "retriever alone"),
    ("answer_accuracy", "Numeric answer accuracy", "all expected numbers in the final answer"),
    ("refusal_accuracy", "Out-of-scope refusal rate", "says the knowledge base can't answer (heuristic)"),
    ("completion_rate", "Completion rate", "final answer within 5 turns, no errors"),
]


def markdown_table(metrics: dict) -> str:
    lines = ["| Metric | Result | Measures |", "|---|---|---|"]
    for key, label, note in _ROWS:
        m = metrics[key]
        if m is None:
            continue
        if key.startswith(("mrr", "raw_query_mrr")):
            result = f"{m['value']:.2f} (n={m['n']})"
        else:
            result = f"{m['value']:.0%} ({m['sum']:g}/{m['n']})"
        lines.append(f"| {label} | {result} | {note} |")
    lines.append(f"| Mean tool calls per question | {metrics['mean_tool_calls']:.1f} | |")
    lines.append(
        f"| Latency, median / p95 | {metrics['median_latency_s']:.1f}s / {metrics['p95_latency_s']:.1f}s | full agent run |"
    )
    return "\n".join(lines)
