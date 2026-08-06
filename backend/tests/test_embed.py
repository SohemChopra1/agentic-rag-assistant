"""
Tests embed_missing_chunks()'s batching/DB-write logic using a fake
embedding client — no network access or VOYAGE_API_KEY needed. This is the
part of the embedding pipeline that's actually testable in an environment
that can't reach api.voyageai.com at all; the real EmbeddingClient itself
is exercised only by actually running it with a real key.
"""
from app.models import Chunk, Document
from app.retrieval.embed import embed_missing_chunks

DIM = 1024


class FakeEmbeddingClient:
    """Deterministic stand-in for EmbeddingClient — no voyageai import, no
    network call. Records every call made so tests can assert on batching
    and input_type behavior, not just the end result."""

    def __init__(self):
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        self.calls.append((texts, input_type))
        return [[float(len(t))] * DIM for t in texts]  # content-derived but deterministic


def _add_chunk(db, content, embedding=None):
    doc = Document(title="Test Doc", source_type="file", source="test", content_hash="x")
    db.add(doc)
    db.flush()
    chunk = Chunk(document_id=doc.id, chunk_index=0, content=content, word_count=1, embedding=embedding)
    db.add(chunk)
    db.flush()
    return chunk


def test_embed_missing_chunks_fills_null_embeddings(db_session):
    db = db_session
    _add_chunk(db, "chunk one")
    _add_chunk(db, "chunk two")
    db.commit()

    client = FakeEmbeddingClient()
    n = embed_missing_chunks(db, client, batch_size=32)

    assert n == 2
    remaining = db.query(Chunk).filter(Chunk.embedding.is_(None)).count()
    assert remaining == 0


def test_embed_missing_chunks_skips_already_embedded(db_session):
    db = db_session
    _add_chunk(db, "already embedded", embedding=[0.5] * DIM)
    _add_chunk(db, "needs embedding")
    db.commit()

    client = FakeEmbeddingClient()
    n = embed_missing_chunks(db, client, batch_size=32)

    assert n == 1  # only the unembedded one
    assert len(client.calls) == 1
    assert client.calls[0][0] == ["needs embedding"]


def test_embed_missing_chunks_uses_document_input_type(db_session):
    db = db_session
    _add_chunk(db, "some content")
    db.commit()

    client = FakeEmbeddingClient()
    embed_missing_chunks(db, client)

    assert client.calls[0][1] == "document"


def test_embed_missing_chunks_batches_correctly(db_session):
    db = db_session
    for i in range(5):
        _add_chunk(db, f"chunk {i}")
    db.commit()

    client = FakeEmbeddingClient()
    n = embed_missing_chunks(db, client, batch_size=2)

    assert n == 5
    # 5 chunks at batch_size=2 -> 3 calls (2, 2, 1)
    assert len(client.calls) == 3
    assert [len(texts) for texts, _ in client.calls] == [2, 2, 1]


def test_embed_missing_chunks_is_idempotent(db_session):
    db = db_session
    _add_chunk(db, "chunk one")
    db.commit()

    client = FakeEmbeddingClient()
    first_run = embed_missing_chunks(db, client)
    second_run = embed_missing_chunks(db, client)

    assert first_run == 1
    assert second_run == 0  # nothing left to embed
