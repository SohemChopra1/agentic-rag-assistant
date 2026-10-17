**Agentic Fitness & Nutrition Assistant**

A full-stack AI agent that answers exercise, nutrition, and well-being
questions by autonomously choosing between retrieval, computation, and
external tools — rather than a single static prompt. Built to demonstrate
agent orchestration, retrieval-augmented generation, and production
deployment practices (streaming, containerization, CI/CD, evaluation).

**Why this project?**

Most "LLM wrapper" projects make one prompt call and return the output. This
project implements a reasoning loop: the agent decides *which* tool to
call, *when* to call it, and *how many steps* to take before answering —
grounded in retrieved source documents (guidelines, research summaries,
personal notes) with citations, not memory alone. E.g. "how much protein do
I need for my training load" gets answered from retrieved sources; "what's
my estimated calorie burn for a 45 min run + 30 min lifting session" gets
routed to a calculation tool instead of a hallucinated number.



**Stack**


- Frontend: React, SSE client 

- Backend: FastAPI 

- Agent loop: ReAct (Claude API) 

- Retrieval:  pgvector + PostgreSQL 

- Ingestion: PDF/HTML

- Deployment: Docker, GitHub Actions CI/CD 


 **Data sources**

The ingestion pipeline (`backend/app/retrieval/`) accepts any PDF, web
article, or markdown/text note via `--file`, `--url`, or a `--manifest`
JSON file listing many sources at once.

The repo currently ships with a real starter corpus of **9 sources / 61
chunks** (`data/sources.json` is the manifest, `data/raw/` has the cleaned
source text, `data/chunks.jsonl` is the ingested output):

| Source | Publisher | Topic |
|---|---|---|
| Adding Physical Activity as an Adult | CDC | Aerobic + strength guidelines |
| What Counts as Physical Activity for Adults | CDC | Intensity, reps, sets |
| Older Adult Activity: An Overview | CDC | Age-specific guidance |
| About Water and Healthier Drinks | CDC | Hydration |
| Hydrating for Health | NIH News in Health | Hydration research |
| Weekend Catch-Up Can't Counter Chronic Sleep Deprivation | NIH | Sleep + metabolism |
| Four Types of Exercise | NIA | Endurance/strength/balance/flexibility |
| Progressive Overload | Wikipedia (CC BY-SA) | Muscle physiology mechanism |
| Dietary Guidelines for Americans, 2025-2030 | USDA/HHS | Full nutrition guidance |

All sources are either U.S. government works (no copyright — safe to fully
ingest and store) or CC BY-SA licensed (Wikipedia, reused with
attribution). Commercial fitness/nutrition sites were deliberately excluded
from bulk ingestion since that content is copyrighted.

Re-run ingestion at any time with:
```bash
python -m app.retrieval.ingest --manifest ../data/sources.json --out ../data/chunks.jsonl
```
(run from `backend/`, or adjust paths — the manifest's file paths are
relative to the repo root)

## Status

This repo is under active development. See `ROADMAP.md` for the build order
and what's been verified so far vs. what's still pending.

## Local development

```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# ingest a source document (or bulk via --manifest ../data/sources.json)
python -m app.retrieval.ingest --file path/to/guidelines.pdf --title "..."

# load chunked JSONL into the database (skips unchanged docs)
python -m app.retrieval.load --in ../data/chunks.jsonl

# embed any chunks that don't have an embedding yet — requires VOYAGE_API_KEY
python -m app.retrieval.embed

# frontend
cd frontend
npm install
npm run dev

# full stack via Docker
docker compose up --build
```

## API

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /retrieve` `{"query", "top_k"}` | Top-k chunks with citations and cosine distance |
| `POST /ask` `{"query"}` | Final answer + the list of tool calls the agent made |
| `POST /ask/stream` `{"query"}` | The same run as Server-Sent Events, one per step |

`/ask/stream` events, in the order they occur:

```
event: tool_call     {"type":"tool_call","id":"t1","tool":"calculate","input":{"expression":"80 * 1.2"}}
event: tool_result   {"type":"tool_result","id":"t1","tool":"calculate","output":"96.0","is_error":false}
event: answer        {"type":"answer","text":"...","completed":true}
```

`retrieve_docs` results also include `sources` (the structured chunks the
model read). A failure after streaming has started arrives as a final
`event: error` with a `message`; a missing API key is a plain HTTP 503.

Try it:
```bash
curl -N -X POST http://localhost:8000/ask/stream -H "Content-Type: application/json" \
  -d '{"query": "how much protein should I eat if I weigh 80kg?"}'
```

## Environment variables

Copy `.env.example` to `.env` in `backend/` and fill in:

```
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
DATABASE_URL=postgresql://user:pass@localhost:5432/agentic_rag
JWT_SECRET=
```

## Evaluation

`eval/test_queries.json` holds 21 labeled questions in four groups:

| Group | n | What a correct run looks like |
|---|---|---|
| Retrieval | 9 | searches, and a labeled passage is in the top 5 |
| Retrieve, then calculate | 5 | searches *before* calculating; the answer has the right numbers |
| Calculate only | 3 | calls `calculate`; the answer has the right number |
| Out of scope | 4 | searches, then says the knowledge base can't answer |

Labels are checked by tests (`backend/tests/test_eval_queries.py`): every
expected passage must exist verbatim in `data/chunks.jsonl`, every expected
tool must exist, and each out-of-scope topic lists terms that must stay
*absent* from the corpus — so adding a source can't silently invalidate a
label.

With the stack running (`docker compose up`) and the backend venv active:

```bash
python eval/run_eval.py                  # one pass over all 21 questions
python eval/run_eval.py --repeats 3      # average over 3 passes (model output varies)
python eval/run_eval.py --write-readme   # also refresh the table below
```

The harness goes through the public API (`/ask/stream`, plus `/retrieve`
with the user's exact words as a retriever-only baseline), so it measures
the system as deployed. Scoring rules (`eval/scoring.py`, unit tested):

- **Tool selection**: expected tools appear *in order*; repeats are fine
  (`retrieve → calculate → calculate` for a range counts as correct)
- **Hit rate @5 / MRR**: is the labeled passage in the top 5, and at what
  rank — for the agent's own search query and for the user's raw words
- **Numeric answers**: whole-number match, ignoring thousands separators
  (`1,920` matches `1920`; `20` does not match `2026` or `120`)
- **Refusals**: a regex heuristic, scored only on out-of-scope questions;
  every answer is saved to `eval/results/` so misses can be audited

<!-- eval:start -->
_Not run yet: run `python eval/run_eval.py --write-readme` with the stack up to fill this in._
<!-- eval:end -->

## License

MIT
