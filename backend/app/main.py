"""
Agentic RAG Assistant — backend entrypoint.

Phase 0 scaffold: just a health check. Agent loop, retrieval, and auth
land in later phases — see ROADMAP.md.
"""
from fastapi import FastAPI

from app.retrieval.router import router as retrieval_router

app = FastAPI(title="Agentic RAG Assistant")

app.include_router(retrieval_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Further routers get mounted here as phases land, e.g.:
# from app.agent.router import router as agent_router
# app.include_router(agent_router, prefix="/agent")
