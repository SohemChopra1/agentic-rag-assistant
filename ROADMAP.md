# Roadmap

Build order, each phase should be its own set of commits / PRs so the git
history tells a story.

- [x] **Phase 0 — Scaffold**
  - Repo structure, Docker skeleton, CI stub, README

- [x] **Phase 1 — Backend core**
  - [x] FastAPI app boots, `/health` endpoint
  - [x] SQLAlchemy models (`Document`, `Chunk` w/ pgvector column) + `init_db()`
        — **verified end-to-end** against a real local Postgres 16 +
        pgvector instance: extension enables, both tables create, the full
        61-chunk corpus writes and reads back correctly via the ORM
        relationship, cascade delete works, and the `embedding` column is
        confirmed as a genuine `VECTOR(1024)` type. Found and fixed a real
        bug in the process: `init_db()` silently created zero tables if
        `app.models` hadn't been imported elsewhere first — now
        self-sufficient via a local import inside `init_db()` itself.
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

- [x] **Phase 2 — Retrieval**
  - [x] Embedding module (`app/retrieval/embed.py`) — batches unembedded
        chunks through Voyage AI (voyage-2, 1024-dim), skips already-embedded
        ones, idempotent. Unit tested (5 tests, fake client) and then
        **run for real** against the live corpus with a real `VOYAGE_API_KEY`
        through Docker
  - [x] Similarity search (`app/retrieval/search.py`) — pgvector cosine
        distance query, verified end-to-end against real Postgres+pgvector
        using synthetic basis vectors (5 tests): nearest-neighbor ordering,
        top_k limiting, NULL-embedding exclusion, citation_url fallback,
        section metadata
  - [x] `/retrieve` API endpoint — returns clean 503 (not an unhandled 500)
        when VOYAGE_API_KEY isn't set; request validation tested. **Verified
        live**: a real query returned the Dietary Guidelines protein chunk
        ranked first by cosine distance
  - [x] Load script (`app/retrieval/load.py`) — completes the actual
        pipeline (ingest.py -> load.py -> embed.py); skips unchanged docs
        via content_hash, replaces changed ones. Verified against the real
        61-chunk corpus, including idempotency
  - [x] CI updated with a real `pgvector/pgvector:pg16` service container —
        without this, the DB-dependent tests above would silently *skip*
        in CI (green checkmark, but not actually running)

- [x] **Phase 3 — Agent loop**
  - [x] Hand-rolled ReAct loop (`app/agent/loop.py`) calling the Anthropic
        API directly (no LangChain/LangGraph) — up to 5 reasoning turns,
        threads tool_use/tool_result blocks, terminates cleanly instead of
        looping forever if the model never stops calling tools
  - [x] Tool definitions (`app/agent/tools.py`): `retrieve_docs` (hits the
        same embed+search stack as `/retrieve`) and `calculate` (arithmetic
        for applying a retrieved guideline to a user's specific numbers,
        e.g. g/kg protein x bodyweight)
  - [x] `calculate` is **not** a raw `eval()`: a restricted `ast` walk
        permits only numeric literals and `+ - * / ** %`, explicitly
        rejecting `Call`, `Name`, comprehensions, strings, and booleans.
        This matters because the expression can be influenced by retrieved
        document content — a real `eval()` would turn a prompt-injected
        chunk into arbitrary code execution. Tested against actual
        injection attempts (`__import__`, `open()`, list comprehensions,
        bare names, string literals, bool-as-int)
  - [x] `/ask` endpoint (`app/agent/router.py`) — clean 503 on missing
        `ANTHROPIC_API_KEY`/`VOYAGE_API_KEY` or an `AnthropicError`, 422 on
        a malformed request
  - [x] 22 new tests: safe-eval injection coverage, `execute_retrieve_docs`
        formatting, and orchestration (direct answer / single-tool /
        chained retrieve-then-calculate / unknown-tool / max-turns
        termination / missing-key guard) against a fake Anthropic client —
        no network or real API key needed to verify the loop logic itself
  - [x] Upgraded `anthropic` 0.34.2 -> 1.11.0 (was stale); confirmed an
        empty `ANTHROPIC_API_KEY` raises a bare `TypeError` rather than an
        `AnthropicError` on both versions — added an explicit upfront
        `RuntimeError` guard in `run_agent()` rather than relying on the
        SDK's exception hierarchy for that case
  - [x] **Hardening pass** (found by review, each confirmed by running it
        and then covered by a regression test — 66 tests total):
    - `calculate` blocked code execution but not resource exhaustion:
      `9**9**9` is legal arithmetic and pinned a worker for minutes. Now
      bounded by input length (200 chars), a magnitude check on every
      intermediate result (1e15), and a `Pow` check that estimates
      `exponent * log10(|base|)` *before* computing, so the huge number is
      never built. Tests assert rejection in <0.5s
    - A tool failure mid-loop (e.g. Voyage timeout) crashed `/ask` with an
      unhandled 500. Now returned to the model as an `is_error` tool_result
      (with a session rollback) so it can recover or say the knowledge base
      is unavailable; `/retrieve` maps Voyage API errors to 503
    - Model ID corrected to `claude-sonnet-5-5`
    - `eval/test_queries.json` expected a nonexistent `run_code` tool on a
      calorie-burn query the corpus can't answer (no MET data). Replaced
      with a chained retrieve-then-calculate query, switched to an ordered
      `expected_tools` list, and added `test_eval_queries.py`, which fails if
      any expected tool doesn't exist or any expected phrase isn't in
      `data/chunks.jsonl`
    - `embed.py` pairs chunks with vectors via `zip(strict=True)`, so a
      short API response fails loudly instead of mis-assigning embeddings

    LIVE CHECK: (real Anthropic + Voyage APIs): for "how much
        protein should I eat if I weigh 80kg?"
        the Dietary Guidelines' 1.2-1.6 g/kg chunk, returned 96-128 g/day
        with a citation, and stated what the corpus couldn't answer rather
        than filling the gap from general knowledge
        `curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"query": "how much protein should I eat if I weigh 80kg?"}'`

- [x] **Phase 4 — Streaming + frontend**
  - [x] Agent loop restructured as an event generator (`agent_events`):
        `tool_call` -> `tool_result` per tool, then a terminal `answer`.
        `/ask` collects the events into its existing JSON response (all
        Phase 3 tests pass unchanged); `POST /ask/stream` forwards each one
        as a Server-Sent Event the moment it happens. One loop, two
        transports — no duplicated orchestration logic
  - [x] Two-phase error handling, because an SSE response commits to HTTP
        200 on its first byte: missing API keys are checked *before*
        streaming starts (real 503, same as `/ask`); failures mid-stream
        become a terminal `error` event instead of a dropped connection
  - [x] The stream owns its DB session (opened with the generator, closed
        in its `finally`) rather than using `Depends(get_db)`, so the
        session lives exactly as long as the loop that queries it
  - [x] `retrieve_docs` results carry structured `sources` (title,
        section, URL, chunk text, distance) alongside the text the model
        reads — the UI renders them directly and Phase 7 can score them,
        with no parsing of model-facing text
  - [x] React chat UI: each step renders live on a trace (searches show
        the exact passages the model read; calculations show the equation),
        then the markdown answer. Stop button (AbortController), backend
        status check, and clear messages for 503s and mid-stream errors
  - [x] Incremental SSE parser (`fetch` + `ReadableStream`, since
        `EventSource` can't POST), tested against the stream split at
        every byte position — including mid-`\r\n` and mid-UTF-8 character
  - [x] Verified end to end through the Vite proxy: events arrived at the
        exact delays the server introduced (no buffering anywhere in the
        chain); UI checked at desktop and 390px mobile widths
  - [x] 13 new backend tests (event ordering, SSE wire format, error
        phases, session cleanup) + 6 frontend tests; `npm test` added to CI

- [ ] **Phase 5 — Auth + persistence**
  - JWT auth, user accounts
  - Chat history persisted in Postgres

- [x] **Phase 6 — Ops** (partial — revisit once frontend/auth land)
  - [x] Dockerize both services, `docker-compose.yml` for local full stack
  - [x] GitHub Actions on push/PR, three jobs: ruff lint + pytest against a
        real `pgvector/pgvector:pg16` service container; frontend
        `npm run build`; backend Docker image build
  - [x] Vite dev proxy fixed: `/api/*` is forwarded with the prefix
        stripped (backend routes live at the root), and the target comes
        from `VITE_API_TARGET` (`http://backend:8000` in docker compose,
        where `localhost` is the frontend container itself)

- [ ] **Phase 7 — Evaluation**
  - `eval/test_queries.json`: labeled queries, phrases verified against the
    actual ingested corpus (not assumed) before being committed
  - `eval/run_eval.py`: scores tool-selection accuracy + retrieval precision
    — needs wiring up against the now-real `/ask` endpoint
  - Add eval results to README as a table

- [ ] **Phase 8 — Deploy**
  - Deploy to Render/Fly.io
  - Update README with live demo link
