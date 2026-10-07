"""
Evaluation harness for the agent.

Phase 7 (see ROADMAP.md): loads test_queries.json, runs each query through
the agent, and scores:
  - tool-selection accuracy (did it call the expected tools, in order?)
  - retrieval relevance (did the expected source show up in top-k?)

Each query lists `expected_tools` in call order, so chained queries (e.g.
retrieve the g/kg guideline, then calculate for the user's weight) can be
scored, not just single-tool ones. Every `expected_source_contains` phrase
is verified to exist verbatim in data/chunks.jsonl.

Placeholder for now — the agent loop (Phase 3) exists; scoring is wired up
in Phase 7.
"""
import json
from pathlib import Path

QUERIES_PATH = Path(__file__).parent / "test_queries.json"


def load_queries():
    with open(QUERIES_PATH) as f:
        return json.load(f)


def main():
    queries = load_queries()
    print(f"Loaded {len(queries)} eval queries. Scoring not wired up yet — see ROADMAP.md Phase 7.")


if __name__ == "__main__":
    main()
