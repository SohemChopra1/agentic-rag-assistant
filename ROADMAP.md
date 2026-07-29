# Roadmap

Build order, each phase should be its own set of commits / PRs so the git
history tells a story.

- [ ] **Phase 0 — Scaffold** (this commit)
  - Repo structure, Docker skeleton, CI stub, README

- [ ] **Phase 1 — Backend core**
  - FastAPI app boots, `/health` endpoint
  - Postgres connection + pgvector extension enabled
  - Document ingestion script (chunk + embed a sample GitHub repo)

- [ ] **Phase 2 — Retrieval**
  - Embedding pipeline (chunking strategy, overlap tuning)
  - Similarity search endpoint returning ranked chunks + source citations

- [ ] **Phase 3 — Agent loop**
  - Hand-rolled ReAct loop calling Claude API directly
  - Tool definitions: `retrieve_docs`, `run_code` (sandboxed calc/exec), one
    live external API tool
  - Agent decides tool vs. direct answer based on query

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
  - `eval/test_queries.json`: ~15-20 labeled queries
  - `eval/run_eval.py`: scores tool-selection accuracy + retrieval precision
  - Add eval results to README as a table

- [ ] **Phase 8 — Deploy**
  - Deploy to Render/Fly.io
  - Update README with live demo link
