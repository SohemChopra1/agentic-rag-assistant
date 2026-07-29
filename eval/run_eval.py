"""
Evaluation harness for the agent.

Phase 7 (see ROADMAP.md): loads test_queries.json, runs each query through
the agent, and scores:
  - tool-selection accuracy (did it call the expected tool?)
  - retrieval relevance (did the expected source show up in top-k?)

Placeholder for now — wire this up once the agent loop (Phase 3) exists.
"""
import json
from pathlib import Path

QUERIES_PATH = Path(__file__).parent / "test_queries.json"


def load_queries():
    with open(QUERIES_PATH) as f:
        return json.load(f)


def main():
    queries = load_queries()
    print(f"Loaded {len(queries)} eval queries. Agent not wired up yet — see ROADMAP.md Phase 3.")


if __name__ == "__main__":
    main()
