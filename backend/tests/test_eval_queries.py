"""
Guards eval/test_queries.json against drifting away from the real system.

Two ways an eval set silently goes bad, both of which happened here:
  - an expected tool that doesn't exist (q3 once expected "run_code"; the
    tool is "calculate"), so that query could never be scored correct
  - an expected source phrase that isn't actually in the corpus, so
    retrieval looks broken when the label is what's wrong
A third guards the out-of-scope set from the other direction: if a new
source ever covers one of those topics, the "should refuse" label becomes
wrong, so each lists terms that must stay absent from the corpus.
All checks run against files in the repo — no API key or DB needed.
"""
import json
import re
from pathlib import Path

from app.agent.tools import ALL_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERIES = json.loads((REPO_ROOT / "eval" / "test_queries.json").read_text())
CHUNK_TEXTS = [
    json.loads(line)["content"] for line in (REPO_ROOT / "data" / "chunks.jsonl").read_text().splitlines() if line
]
TOOL_NAMES = {t["name"] for t in ALL_TOOLS}
CATEGORIES = {"retrieval", "retrieve_then_calculate", "calculate_only", "out_of_scope"}


def test_every_expected_tool_exists():
    for q in QUERIES:
        assert q["expected_tools"], f"{q['id']}: expected_tools is empty"
        unknown = set(q["expected_tools"]) - TOOL_NAMES
        assert not unknown, f"{q['id']}: expects nonexistent tool(s) {unknown}; real tools are {TOOL_NAMES}"


def test_every_expected_source_phrase_is_in_the_corpus():
    for q in QUERIES:
        phrase = q["expected_source_contains"]
        if phrase is None:
            continue
        assert any(phrase in text for text in CHUNK_TEXTS), f"{q['id']}: {phrase!r} not found in any chunk"


def test_query_ids_are_unique():
    ids = [q["id"] for q in QUERIES]
    assert len(ids) == len(set(ids))


def test_every_query_has_a_known_category():
    for q in QUERIES:
        assert q["category"] in CATEGORIES, f"{q['id']}: unknown category {q['category']!r}"


def test_calculation_queries_label_the_expected_answer():
    for q in QUERIES:
        if q["category"] in {"retrieve_then_calculate", "calculate_only"}:
            assert q.get("expected_answer_contains"), f"{q['id']}: no expected_answer_contains"
            assert "calculate" in q["expected_tools"], f"{q['id']}: calculation query doesn't expect calculate"


def test_retrieval_queries_label_a_source_passage():
    for q in QUERIES:
        if q["category"] in {"retrieval", "retrieve_then_calculate"}:
            assert q["expected_source_contains"], f"{q['id']}: no expected_source_contains"


def test_out_of_scope_topics_are_really_absent_from_the_corpus():
    for q in QUERIES:
        if q["category"] != "out_of_scope":
            continue
        assert q.get("expected_refusal") is True, f"{q['id']}: out_of_scope must set expected_refusal"
        assert q.get("absent_terms"), f"{q['id']}: list absent_terms so corpus changes can't silently break the label"
        for term in q["absent_terms"]:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            found = [text[:80] for text in CHUNK_TEXTS if pattern.search(text)]
            assert not found, f"{q['id']}: {term!r} now appears in the corpus, e.g. {found[0]!r} — relabel or rewrite the query"
