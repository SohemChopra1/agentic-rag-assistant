"""
/retrieve endpoint: embeds a query via Voyage and returns the top-k most
similar chunks with citations. Requires VOYAGE_API_KEY and an embedded
corpus (run embed.py first) — will raise a clear error otherwise rather
than failing silently.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.retrieval.embed import EmbeddingClient
from app.retrieval.search import get_query_embedding, search_chunks

router = APIRouter()


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5


class RetrieveResult(BaseModel):
    content: str
    section: str | None
    title: str
    citation_url: str | None
    distance: float


@router.post("/retrieve", response_model=list[RetrieveResult])
def retrieve(req: RetrieveRequest, db: Session = Depends(get_db)):
    try:
        client = EmbeddingClient()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    query_embedding = get_query_embedding(client, req.query)
    return search_chunks(db, query_embedding, top_k=req.top_k)
