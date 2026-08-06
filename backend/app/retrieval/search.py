"""
Similarity search over embedded chunks using pgvector's cosine distance
operator (via pgvector-python's `.cosine_distance()` comparator, which
compiles to Postgres's `<=>` operator).

Deliberately separate from embed.py: search_chunks() takes an
already-computed query embedding rather than a raw query string, so the
SQL/ORM query logic can be fully tested against a real Postgres+pgvector
instance using synthetic vectors — no Voyage API call, no network, no key
required. get_query_embedding() is the thin (currently untested, since it
needs a live API key) layer that turns a raw query string into a vector
using Voyage's "query" input_type — Voyage's models are asymmetric, so
documents and queries are deliberately embedded differently.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.retrieval.embed import EmbeddingClient


def get_query_embedding(client: EmbeddingClient, query: str) -> list[float]:
    return client.embed([query], input_type="query")[0]


def search_chunks(db: Session, query_embedding: list[float], top_k: int = 5) -> list[dict]:
    stmt = (
        select(Chunk, Document, Chunk.embedding.cosine_distance(query_embedding).label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.embedding.is_not(None))
        .order_by("distance")
        .limit(top_k)
    )

    results = []
    for chunk, doc, distance in db.execute(stmt).all():
        results.append(
            {
                "content": chunk.content,
                "section": chunk.section,
                "title": doc.title,
                "citation_url": doc.citation_url or doc.source,
                "distance": float(distance),
            }
        )
    return results
