"""
Evaluation harness for the agent (Phase 7).

Runs every labeled query in test_queries.json through the running stack's
public API — the same /ask/stream the UI uses, plus /retrieve with the
user's exact words as a retriever-only baseline — then scores the runs with
eval/scoring.py and prints a results table.

Usage (stack running via `docker compose up`, backend venv active):
    python eval/run_eval.py                    # all queries, once
    python eval/run_eval.py --repeats 3        # model output varies; average over runs
    python eval/run_eval.py --only c01 o02     # a subset, by id
    python eval/run_eval.py --write-readme     # also update the README results table

Cost: each query is one agent run (usually 2-4 model calls) plus a couple
of Voyage embeddings. A full pass of 21 queries is ~60-80 model calls.

Every run's raw output (tool calls, retrieved chunks, answer) is saved to
eval/results/<timestamp>.json (gitignored) so any score can be audited.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from scoring import aggregate, markdown_table, score_run

EVAL_DIR = Path(__file__).resolve().parent
QUERIES_PATH = EVAL_DIR / "test_queries.json"
RESULTS_DIR = EVAL_DIR / "results"
README_PATH = EVAL_DIR.parent / "README.md"
README_START = "<!-- eval:start -->"
README_END = "<!-- eval:end -->"


def load_queries() -> list[dict]:
    return json.loads(QUERIES_PATH.read_text())


def iter_sse_events(response: httpx.Response):
    """Yield parsed JSON payloads from an SSE response, skipping pings."""
    event, data = None, []
    for line in response.iter_lines():
        if line == "":
            if data and event != "ping":
                yield json.loads("\n".join(data))
            event, data = None, []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].removeprefix(" "))
    if data and event != "ping":
        yield json.loads("\n".join(data))


def run_query(client: httpx.Client, query: dict) -> dict:
    raw = client.post("/retrieve", json={"query": query["query"], "top_k": 5})
    if raw.status_code != 200:
        raise RuntimeError(f"/retrieve returned HTTP {raw.status_code}: {raw.text}")

    run = {
        "tool_calls": [],
        "retrievals": [],
        "raw_retrieval": raw.json(),
        "answer": "",
        "completed": False,
        "error": None,
    }
    start = time.perf_counter()
    with client.stream("POST", "/ask/stream", json={"query": query["query"]}) as response:
        if response.status_code != 200:
            response.read()
            raise RuntimeError(f"/ask/stream returned HTTP {response.status_code}: {response.text}")
        for event in iter_sse_events(response):
            if event["type"] == "tool_call":
                run["tool_calls"].append(event["tool"])
            elif event["type"] == "tool_result" and event["tool"] == "retrieve_docs":
                run["retrievals"].append(event.get("sources") or [])
            elif event["type"] == "answer":
                run["answer"], run["completed"] = event["text"], event["completed"]
            elif event["type"] == "error":
                run["error"] = event["message"]
    run["latency_s"] = time.perf_counter() - start
    return run


def _mark(value) -> str:
    return "-" if value is None else ("ok" if value else "MISS")


def progress_line(s: dict) -> str:
    parts = [f"{s['id']:<4} {s['category']:<24} tools {_mark(s['tools_ok']):<4}"]
    if s["hit"] is not None:
        parts.append(f"hit {_mark(s['hit']):<4} rr {s['rr']:.2f}")
    if s["answer_ok"] is not None:
        parts.append(f"answer {_mark(s['answer_ok'])}")
    if s["refused"] is not None:
        parts.append(f"refused {_mark(s['refused'])}")
    parts.append(f"{s['latency_s']:.1f}s")
    return "  ".join(parts)


def write_readme_table(table: str, meta: str) -> None:
    readme = README_PATH.read_text()
    block = f"{README_START}\n{meta}\n\n{table}\n{README_END}"
    pattern = re.compile(re.escape(README_START) + ".*?" + re.escape(README_END), re.DOTALL)
    if not pattern.search(readme):
        sys.exit(f"README is missing the {README_START} / {README_END} markers")
    README_PATH.write_text(pattern.sub(lambda _: block, readme))


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the agent against eval/test_queries.json")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--repeats", type=int, default=1, help="runs per query (model output varies)")
    parser.add_argument("--only", nargs="+", metavar="ID", help="run only these query ids")
    parser.add_argument("--write-readme", action="store_true", help="update the results table in README.md")
    args = parser.parse_args()

    queries = load_queries()
    if args.only:
        unknown = set(args.only) - {q["id"] for q in queries}
        if unknown:
            sys.exit(f"Unknown query id(s): {', '.join(sorted(unknown))}")
        queries = [q for q in queries if q["id"] in args.only]

    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as e:
            sys.exit(f"Backend not reachable at {args.base_url} ({e}). Start it with `docker compose up`.")

        scores, runs = [], []
        for repeat in range(args.repeats):
            if args.repeats > 1:
                print(f"\n--- pass {repeat + 1} of {args.repeats}")
            for query in queries:
                try:
                    run = run_query(client, query)
                except (httpx.HTTPError, RuntimeError) as e:
                    sys.exit(f"{query['id']}: {e}")
                score = score_run(query, run)
                scores.append(score)
                runs.append({"query": query, "run": run, "score": score})
                print(progress_line(score), flush=True)

    metrics = aggregate(scores)
    table = markdown_table(metrics)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = (
        f"_{len(queries)} labeled questions × {args.repeats} run(s), {stamp}. "
        f"Reproduce with `python eval/run_eval.py --repeats {args.repeats}`._"
    )

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out_path.write_text(json.dumps({"metrics": metrics, "runs": runs}, indent=2))

    print(f"\n{table}\n\nFull report: {out_path.relative_to(EVAL_DIR.parent)}")
    if args.write_readme:
        write_readme_table(table, meta)
        print("README.md results table updated.")


if __name__ == "__main__":
    main()
