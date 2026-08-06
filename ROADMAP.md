# Roadmap

Build order, each phase should be its own set of commits / PRs so the git
history tells a story.

- [x] **Phase 0 — Scaffold**
  - Repo structure, Docker skeleton, CI stub, README

- [x] **Phase 1 — Backend core**
  - [x] FastAPI app boots, `/health` endpoint
  - [x] SQLAlchemy models (`Document`, `Chunk` w/ pgvector column) + `init_db()`
        — code written, not yet run against a live Postgres; do that via
        `docker compose up`
  - [x] Text extraction for PDF / HTML / markdown (`app/retrieval/extractors.py`)
        — tested against a real generated PDF fixture; caught and fixed a
        real bug where PDF line-wraps fragmented phrases mid-word
  - [x] Prose chunker (`app/retrieval/chunker.py`) — chunks by paragraph,
        tracks markdown headings as section metadata, splits oversized
        paragraphs by sentence. 7 unit tests
  - [x] Generic ingestion script (`app/retrieval/ingest.py`) — accepts
        `--file`, `--url`, or `--manifest`; preserves original citation
        URLs even for locally-saved/cleaned sources
  - [x] **Real corpus ingested**: 9 public-domain / openly-licensed sources
        (CDC, NIH, NIA, USDA/HHS Dietary Guidelines 2025-2030, Wikipedia
        CC BY-SA) -> 61 chunks in `data/chunks.jsonl`. See `data/sources.json`
        for the manifest and `data/raw/` for the cleaned source text.
        Deliberately excludes copyrighted commercial fitness content
        (Examine, Healthline, etc.) — only government works (no copyright)
        and CC-licensed content were bulk-ingested.
  - [ ] Embedding step (Phase 2 — chunks are ready in JSONL, not yet embedded)

- [ ] **Phase 2 — Retrieval**
  - Embedding pipeline via Voyage AI (Claude has no native embeddings endpoint)
  - Similarity search endpoint returning ranked chunks + source citations
    (citation_url is already captured per-chunk from Phase 1, ready to surface)

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
  - `eval/test_queries.json`: labeled queries, phrases verified against the
    actual ingested corpus (not assumed) before being committed
  - `eval/run_eval.py`: scores tool-selection accuracy + retrieval precision
  - Add eval results to README as a table

- [ ] **Phase 8 — Deploy**
  - Deploy to Render/Fly.io
  - Update README with live demo link
