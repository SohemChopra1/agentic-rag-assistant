# Agentic Fitness & Nutrition Assistant

A full-stack AI agent that answers exercise, nutrition, and well-being
questions by autonomously choosing between retrieval, computation, and
external tools — rather than a single static prompt. Built to demonstrate
agent orchestration, retrieval-augmented generation, and production
deployment practices (streaming, containerization, CI/CD, evaluation).

## Why this project exists

Most "LLM wrapper" projects make one prompt call and return the output. This
project implements a **reasoning loop**: the agent decides *which* tool to
call, *when* to call it, and *how many steps* to take before answering —
grounded in retrieved source documents (guidelines, research summaries,
personal notes) with citations, not memory alone. E.g. "how much protein do
I need for my training load" gets answered from retrieved sources; "what's
my estimated calorie burn for a 45 min run + 30 min lifting session" gets
routed to a calculation tool instead of a hallucinated number.

## Architecture

```
┌─────────────┐      SSE stream      ┌──────────────────┐
│   React UI   │◄────────────────────┤   FastAPI server │
│ (chat + auth)│─────────────────────►│   (agent loop)   │
└─────────────┘      user query       └─────────┬────────┘
                                                 │
                          ┌──────────────────────┼──────────────────────┐
                          │                      │                      │
                    ┌─────▼─────┐         ┌──────▼──────┐        ┌──────▼──────┐
                    │  Retrieval │         │  Code/Calc  │        │  External   │
                    │  (pgvector)│         │   Sandbox   │        │     API     │
                    └────────────┘         └─────────────┘        └─────────────┘
                          │
                    ┌─────▼─────┐
                    │ PostgreSQL │  (embeddings, chat history, users)
                    └────────────┘
```

## Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React, SSE client | Streaming token-by-token responses |
| Backend | FastAPI | Async, matches existing FastAPI experience |
| Agent loop | Hand-rolled ReAct (Claude API) | Demonstrates understanding of the mechanics, not just a framework |
| Retrieval | pgvector + PostgreSQL | Single datastore for vectors + relational data |
| Ingestion | PDF / HTML / markdown extractors + prose chunker | Sources are guideline PDFs, articles, and notes — not code |
| Auth | JWT | Standard, framework-agnostic |
| Deployment | Docker, GitHub Actions CI/CD | Reproducible, automated |
| Evaluation | Custom harness (`/eval`) | Scores tool-selection accuracy + retrieval relevance |

## Data sources

The ingestion pipeline (`backend/app/retrieval/`) accepts any PDF, web
article, or markdown/text note via `--file`, `--url`, or a `--manifest`
JSON file listing many sources at once. For your own corpus this could be:

- Public-domain government guidelines (CDC, USDA, ODPHP — no copyright
  restrictions, safe to fully ingest and store)
- Research summaries or position stands you have the right to use
- Your own training notes / saved articles

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

# ingest a source document
python -m app.retrieval.ingest --file path/to/guidelines.pdf --title "..."

# frontend
cd frontend
npm install
npm run dev

# full stack via Docker
docker compose up --build
```

## Environment variables

Copy `.env.example` to `.env` in `backend/` and fill in:

```
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql://user:pass@localhost:5432/agentic_rag
JWT_SECRET=
```

## Evaluation

`eval/test_queries.json` contains a labeled set of queries with expected tool
choices and expected source content. Run:

```bash
cd eval
python run_eval.py
```

This reports tool-selection accuracy and retrieval precision/recall — the
same evaluation rigor applied to the fraud-detection model in a companion
project, here applied to agent behavior instead of a classifier.

## License

MIT
