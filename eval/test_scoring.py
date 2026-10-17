"""Unit tests for eval/scoring.py. Run from backend/: pytest ../eval"""
import pytest

from run_eval import iter_sse_events
from scoring import (
    aggregate,
    answer_contains_all,
    contains_number,
    first_match_rank,
    is_refusal,
    markdown_table,
    reciprocal_rank,
    score_run,
    tools_match,
)

# ---- tools_match -----------------------------------------------------------


def test_tools_match_accepts_the_live_run_with_repeated_calculate():
    # the real Oct 14 run for the 80 kg protein question
    assert tools_match(["retrieve_docs", "calculate"], ["retrieve_docs", "calculate", "calculate"])


def test_tools_match_rejects_wrong_order():
    assert not tools_match(["retrieve_docs", "calculate"], ["calculate", "retrieve_docs"])


def test_tools_match_rejects_missing_tool():
    assert not tools_match(["retrieve_docs", "calculate"], ["retrieve_docs"])


def test_tools_match_allows_extra_calls_between():
    assert tools_match(["retrieve_docs", "calculate"], ["retrieve_docs", "retrieve_docs", "calculate"])


def test_tools_match_fails_when_no_tools_called():
    assert not tools_match(["retrieve_docs"], [])


# ---- retrieval -------------------------------------------------------------


def _src(content):
    return {"content": content, "title": "t", "section": None, "citation_url": None, "distance": 0.1}


SOURCES = [_src("unrelated"), _src("adults get at least 7 hours of sleep"), _src("also at least 7 hours of sleep")]


def test_first_match_rank_is_one_based_and_takes_first():
    assert first_match_rank(SOURCES, "at least 7 hours of sleep") == 2


def test_first_match_rank_none_when_absent():
    assert first_match_rank(SOURCES, "creatine") is None


def test_reciprocal_rank():
    assert reciprocal_rank(SOURCES, "at least 7 hours of sleep") == 0.5
    assert reciprocal_rank(SOURCES, "creatine") == 0.0
    assert reciprocal_rank([], "anything") == 0.0


# ---- numbers in answers ----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["about 20 km", "20.0 km total", "a total of 20.", "**20 km**", "(20)", "20km"],
)
def test_contains_number_matches_whole_number(text):
    assert contains_number(text, "20")


@pytest.mark.parametrize("text", ["in 2026", "120 km", "20.5 km", "1.20 kg", "200 m"])
def test_contains_number_rejects_partial_matches(text):
    assert not contains_number(text, "20")


def test_contains_number_ignores_thousands_separators():
    assert contains_number("You lifted 1,920 kg in total.", "1920")
    assert contains_number("That's 16,800 calories a week.", "16800")


def test_answer_contains_all_requires_every_number():
    assert answer_contains_all("between 96 and 128 g per day", ["96", "128"])
    assert not answer_contains_all("about 128 g per day", ["96", "128"])


# ---- refusal heuristic -----------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "The knowledge base doesn't include any guidance on creatine dosing.",
        "I couldn't find information about intermittent fasting in my sources.",
        "My sources do not cover vitamin D supplement doses in IU.",
        "I don't have specific information about heart rate zones.",
        "There's no specific guidance on this in the guidelines I can access.",
        "Fat-burning heart rate zones are not covered in the available documents.",
    ],
)
def test_is_refusal_detects_admissions(answer):
    assert is_refusal(answer)


@pytest.mark.parametrize(
    "answer",
    [
        "Adults should get at least 7 hours of sleep per night.",
        "Take 3 to 5 grams of creatine daily.",  # a confident answer from general knowledge
        "Intermittent fasting works well for most people.",
    ],
)
def test_is_refusal_ignores_confident_answers(answer):
    assert not is_refusal(answer)


# ---- score_run / aggregate -------------------------------------------------


def _run(tool_calls, retrievals=(), raw=(), answer="", completed=True, error=None, latency=2.0):
    return {
        "tool_calls": list(tool_calls),
        "retrievals": [list(r) for r in retrievals],
        "raw_retrieval": list(raw),
        "answer": answer,
        "completed": completed,
        "error": error,
        "latency_s": latency,
    }


CHAINED = {
    "id": "c01",
    "category": "retrieve_then_calculate",
    "query": "80 kg protein?",
    "expected_tools": ["retrieve_docs", "calculate"],
    "expected_source_contains": "1.2 to 1.6 grams",
    "expected_answer_contains": ["96", "128"],
}

OUT_OF_SCOPE = {
    "id": "o01",
    "category": "out_of_scope",
    "query": "creatine?",
    "expected_tools": ["retrieve_docs"],
    "expected_source_contains": None,
    "expected_refusal": True,
}


def test_score_run_for_a_correct_chained_run():
    run = _run(
        ["retrieve_docs", "calculate", "calculate"],
        retrievals=[[_src("other"), _src("goal: 1.2 to 1.6 grams per kg")]],
        raw=[_src("goal: 1.2 to 1.6 grams per kg")],
        answer="Aim for 96 to 128 g per day.",
    )
    s = score_run(CHAINED, run)
    assert (s["tools_ok"], s["hit"], s["rr"], s["raw_hit"], s["raw_rr"], s["answer_ok"]) == (True, True, 0.5, True, 1.0, True)
    assert s["refused"] is None  # not labeled for refusal -> not scored


def test_score_run_hit_counts_a_later_search_but_mrr_uses_the_first():
    run = _run(
        ["retrieve_docs", "retrieve_docs", "calculate"],
        retrievals=[[_src("miss")], [_src("1.2 to 1.6 grams")]],
        answer="96 to 128",
    )
    s = score_run(CHAINED, run)
    assert s["hit"] is True
    assert s["rr"] == 0.0


def test_score_run_out_of_scope_skips_retrieval_and_answer_metrics():
    s = score_run(OUT_OF_SCOPE, _run(["retrieve_docs"], retrievals=[[]], answer="The knowledge base doesn't cover creatine."))
    assert (s["tools_ok"], s["refused"]) == (True, True)
    assert s["hit"] is None and s["answer_ok"] is None


def test_score_run_mid_stream_error_is_not_completed():
    s = score_run(OUT_OF_SCOPE, _run([], answer="", completed=False, error="Model API error"))
    assert s["completed"] is False
    assert s["tools_ok"] is False


def test_aggregate_only_counts_labeled_queries_per_metric():
    scores = [
        score_run(CHAINED, _run(["retrieve_docs", "calculate"], retrievals=[[_src("1.2 to 1.6 grams")]], answer="96 or 128")),
        score_run(OUT_OF_SCOPE, _run(["retrieve_docs"], retrievals=[[]], answer="Take 5 g daily.", latency=6.0)),
    ]
    m = aggregate(scores)
    assert m["tool_selection_accuracy"] == {"value": 1.0, "n": 2, "sum": 2}
    assert m["retrieval_hit_rate_at_5"]["n"] == 1  # only c01 has a labeled passage
    assert m["refusal_accuracy"] == {"value": 0.0, "n": 1, "sum": 0}
    assert m["median_latency_s"] == 4.0


def test_markdown_table_formats_rates_and_counts():
    scores = [score_run(CHAINED, _run(["retrieve_docs", "calculate"], retrievals=[[_src("1.2 to 1.6 grams")]], answer="96, 128"))]
    table = markdown_table(aggregate(scores))
    assert "| Tool selection accuracy | 100% (1/1) |" in table
    assert "| MRR, agent's first search | 1.00 (n=1) |" in table
    assert "refusal" not in table.lower()  # no out-of-scope queries -> row omitted


# ---- SSE parsing in the runner ---------------------------------------------


class FakeResponse:
    def __init__(self, body):
        self._lines = body.replace("\r\n", "\n").split("\n")

    def iter_lines(self):
        return iter(self._lines)


def test_iter_sse_events_parses_events_and_skips_pings():
    body = (
        'event: tool_call\r\ndata: {"type": "tool_call", "tool": "calculate"}\r\n\r\n'
        ": ping - 2026-10-17\r\n\r\n"
        'event: ping\r\ndata: {}\r\n\r\n'
        'event: answer\r\ndata: {"type": "answer", "text": "20", "completed": true}\r\n\r\n'
    )
    events = list(iter_sse_events(FakeResponse(body)))
    assert [e["type"] for e in events] == ["tool_call", "answer"]
