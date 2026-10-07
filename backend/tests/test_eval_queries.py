"""
Guards eval/test_queries.json against drifting away from the real system.

Two ways an eval set silently goes bad, both of which happened here:
  - an expected tool that doesn't exist (q3 once expected "run_code"; the
    tool is "calculate"), so that query could never be scored correct
  - an expected source phrase that isn't actually in the corpus, so
    retrieval looks broken when the label is what's wrong
Both checks run against files in the repo — no API key or DB needed.
"""
import json
from pathlib import Path

from app.agent.tools import ALL_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERIES = json.loads((REPO_ROOT / "eval" / "test_queries.json").read_text())
CHUNK_TEXTS = [
    json.loads(line)["content"] for line in (REPO_ROOT / "data" / "chunks.jsonl").read_text().splitlines() if line
]
TOOL_NAMES = {t["name"] for t in ALL_TOOLS}


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
