# Roadmap

Build order, each phase should be its own set of commits / PRs so the git
history tells a story.

- [x] **Phase 0 — Scaffold**
  - Repo structure, Docker skeleton, CI stub, README

- [x] **Phase 1 — Backend core**
  - [x] FastAPI app boots, `/health` endpoint
  - [x] SQLAlchemy models (`Document`, `Chunk` w/ pgvector column) + `init_db()`
        — **verified end-to-end** against a real local Postgres 16 +
        pgvector instance (installed directly in the build sandbox, no
        Docker daemon available there): extension enables, both tables
        create, the full 61-chunk corpus writes and reads back correctly
        via the ORM relationship, cascade delete works, and the
        `embedding` column is confirmed as a genuine `VECTOR(1024)` type.
        Found and fixed a real bug in the process: `init_db()` silently
        created zero tables if `app.models` hadn't been imported elsewhere
        first (SQLAlchemy only registers a model's table once its class
        has actually been imported) — now self-sufficient via a local
        import inside `init_db()` itself. Still worth running
        `docker compose up` locally once to confirm the containerized path
        matches, but the code itself is now proven correct.
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
  - [x] Embedding module (`app/retrieval/embed.py`) — batches unembedded
        chunks through Voyage AI (voyage-2, 1024-dim), skips already-embedded
        ones, idempotent. The actual API call is isolated behind
        `EmbeddingClient` so the batching/DB-write logic is fully unit
        tested (5 tests, fake client) without needing network access or a
        real key — api.voyageai.com isn't reachable from the build sandbox
        at all, so this was the only honest way to verify that half
  - [x] Similarity search (`app/retrieval/search.py`) — pgvector cosine
        distance query, **verified end-to-end against real Postgres+pgvector**
        using synthetic basis vectors with known geometric relationships (5
        tests): nearest-neighbor ordering, top_k limiting, NULL-embedding
        exclusion, citation_url fallback to source, section metadata
  - [x] `/retrieve` API endpoint — returns clean 503 (not an unhandled 500)
        when VOYAGE_API_KEY isn't set; request validation tested
  - [x] Load script (`app/retrieval/load.py`) — completes the actual
        pipeline (ingest.py -> load.py -> embed.py); skips unchanged docs
        via content_hash, replaces changed ones. Verified against the real
        61-chunk corpus, including idempotency (second run: 0 inserted, 9
        skipped)
  - [x] CI updated with a real `pgvector/pgvector:pg16` service container —
        without this, the 14 DB-dependent tests above would silently
        *skip* in CI (green checkmark, but not actually running)
  - [ ] **Still needs a real VOYAGE_API_KEY to run for real**: nothing in
        `data/chunks.jsonl` is actually embedded yet (all `embedding` values
        are NULL in the DB). The code path is proven correct with synthetic
        vectors; running `python -m app.retrieval.embed` with a real key is
        the last step to make `/retrieve` return real results instead of a
        503

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
