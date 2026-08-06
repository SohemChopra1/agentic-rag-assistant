"""
Generates embeddings for chunks via Voyage AI — Anthropic's recommended
embedding provider, since Claude itself has no embeddings endpoint.

The actual API call is isolated in `embed_texts()` so the batching/DB-write
logic (`embed_missing_chunks()`) can be unit tested with a fake client,
with no network access or API key required. This mattered in practice:
api.voyageai.com isn't reachable from the sandbox this was built in at all
(same restriction as everything else), so the only way to verify the
surrounding logic honestly was to mock the one function that actually
talks to the network.

voyage-2 produces 1024-dim embeddings, matching EMBEDDING_DIM in models.py.
Voyage recommends different input_type for documents vs. queries
(asymmetric embedding) — "document" here at ingestion time, "query" in
search.py at retrieval time.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk

MODEL = "voyage-2"
BATCH_SIZE = 32


class EmbeddingClient:
    """Thin wrapper around the voyageai SDK. Exists so tests can substitute
    a fake client instead of needing VOYAGE_API_KEY or network access."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.voyage_api_key
        if not self.api_key:
            raise RuntimeError("VOYAGE_API_KEY not set — required to generate real embeddings")
        import voyageai  # imported lazily so the package isn't required just to run DB-only tests

        self._client = voyageai.Client(api_key=self.api_key)

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        result = self._client.embed(texts, model=MODEL, input_type=input_type)
        return result.embeddings


def embed_missing_chunks(db: Session, client: EmbeddingClient, batch_size: int = BATCH_SIZE) -> int:
    """Finds chunks with no embedding yet and fills them in, in batches.
    Safe to re-run: already-embedded chunks are skipped, so ingesting new
    documents and re-running this only embeds what's new."""
    total = 0
    while True:
        chunks = db.execute(select(Chunk).where(Chunk.embedding.is_(None)).limit(batch_size)).scalars().all()
        if not chunks:
            break

        texts = [c.content for c in chunks]
        embeddings = client.embed(texts, input_type="document")

        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        db.commit()
        total += len(chunks)

    return total


def main():
    from app.db import SessionLocal

    client = EmbeddingClient()
    db = SessionLocal()
    try:
        n = embed_missing_chunks(db, client)
        print(f"Embedded {n} chunk(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
