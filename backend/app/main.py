"""
Agentic RAG Assistant — backend entrypoint.

Phase 0 scaffold: just a health check. Agent loop, retrieval, and auth
land in later phases — see ROADMAP.md.
"""
from fastapi import FastAPI

app = FastAPI(title="Agentic RAG Assistant")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Routers get mounted here as phases land, e.g.:
# from app.agent.router import router as agent_router
# app.include_router(agent_router, prefix="/agent")
