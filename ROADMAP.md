# Roadmap

Build order, each phase should be its own set of commits / PRs so the git
history tells a story.

- [x] **Phase 0 — Scaffold**
  - Repo structure, Docker skeleton, CI stub, README

- [x] **Phase 1 — Backend core**
  - [x] FastAPI app boots, `/health` endpoint
  - [x] SQLAlchemy models (`Document`, `Chunk` w/ pgvector column) + `init_db()`
        (enables the `vector` extension, creates tables) — code written,
        not yet run against a live Postgres; do that via `docker compose up`
  - [x] Text extraction for PDF / HTML / markdown (`app/retrieval/extractors.py`)
        — tested against a real generated PDF fixture; caught and fixed a
        real bug where PDF line-wraps fragmented phrases mid-word
        ("glycogen\nreplenishment" instead of "glycogen replenishment")
  - [x] Prose chunker (`app/retrieval/chunker.py`) — chunks by paragraph,
        tracks markdown headings as section metadata, splits oversized
        paragraphs by sentence. 13 unit tests covering heading detection,
        multi-section documents, overlap, and edge cases
  - [x] Generic ingestion script (`app/retrieval/ingest.py`) — accepts
        `--file` (PDF/txt/md), `--url`, or a `--manifest` of many sources;
        verified end-to-end against a PDF fixture, producing valid JSONL
  - [ ] Embedding step (Phase 2 — chunks are ready in JSONL, not yet embedded)
  - **Note:** this pipeline previously targeted GitHub source code (AST-based
    chunking of a Python repo); pivoted to prose/PDF ingestion for the
    fitness/nutrition domain — old code-chunking approach removed entirely
    rather than left as dead code.

- [ ] **Phase 2 — Retrieval**
  - Embedding pipeline via Voyage AI (Claude has no native embeddings endpoint)
  - Similarity search endpoint returning ranked chunks + source citations
  - Populate a real starter corpus (e.g. public-domain CDC/USDA guidelines)

- [ ] **Phase 3 — Agent loop**
  - Hand-rolled ReAct loop calling Claude API directly
  - Tool definitions: `retrieve_docs`, `run_code` (e.g. calorie/macro
    calculations), one live external API tool
  - Agent decides tool vs. direct answer based on query — e.g. "how much
    protein do I need" -> retrieval; "calories burned in a 45 min run" ->
    calculation tool, not a hallucinated number

- [ ] **Phase 4 — Streaming + frontend**
  - SSE endpoint streaming agent steps + final answer
  - React chat UI consuming the stream
  - Show intermediate "thinking" steps (which tool was called and why) —
    good for demos/interviews

- [ ] **Phase 5 — Auth + persistence**
  - JWT auth, user accounts
  - Chat history persisted in Postgres

- [ ] **Phase 6 — Ops**
  - Dockerize both services, `docker-compose.yml` for local full stack
  - GitHub Actions: lint, test, build on push

- [ ] **Phase 7 — Evaluation**
  - `eval/test_queries.json`: ~15-20 labeled fitness/nutrition queries
  - `eval/run_eval.py`: scores tool-selection accuracy + retrieval precision
  - Add eval results to README as a table

- [ ] **Phase 8 — Deploy**
  - Deploy to Render/Fly.io
  - Update README with live demo link
