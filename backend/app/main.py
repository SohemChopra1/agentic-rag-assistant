"""
Agentic RAG Assistant — backend entrypoint.
"""
from fastapi import FastAPI

from app.agent.router import router as agent_router
from app.retrieval.router import router as retrieval_router

app = FastAPI(title="Agentic RAG Assistant")

app.include_router(retrieval_router)
app.include_router(agent_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
