"""
Integration tests for search.py's pgvector query, run against a real
Postgres+pgvector instance (see conftest.py — skipped if none is
reachable). Uses synthetic basis vectors with known geometric relationships
so the expected nearest-neighbor order is unambiguous, rather than trusting
that "some ordering" came back.
"""
from app.models import Chunk, Document
from app.retrieval.search import search_chunks

DIM = 1024


def basis_vector(index: int, dim: int = DIM) -> list[float]:
    v = [0.0] * dim
    v[index] = 1.0
    return v


def _add_doc_with_chunk(db, title, embedding, content="test content", citation_url=None, section=None):
    doc = Document(title=title, source_type="file", source=f"test://{title}", citation_url=citation_url, content_hash="x")
    db.add(doc)
    db.flush()
    chunk = Chunk(document_id=doc.id, section=section, chunk_index=0, content=content, word_count=2, embedding=embedding)
    db.add(chunk)
    db.flush()
    return doc, chunk


def test_search_returns_nearest_neighbor_first(db_session):
    db = db_session
    _add_doc_with_chunk(db, "Doc A", basis_vector(0), content="about topic A")
    _add_doc_with_chunk(db, "Doc B", basis_vector(1), content="about topic B")
    _add_doc_with_chunk(db, "Doc C", basis_vector(2), content="about topic C")
    db.commit()

    # query vector is close to basis_vector(0) but not identical
    query = basis_vector(0)
    query[1] = 0.05

    results = search_chunks(db, query, top_k=3)

    assert results[0]["title"] == "Doc A"
    assert results[0]["distance"] < results[1]["distance"] < results[2]["distance"]


def test_search_respects_top_k(db_session):
    db = db_session
    for i in range(5):
        _add_doc_with_chunk(db, f"Doc {i}", basis_vector(i % DIM), content=f"content {i}")
    db.commit()

    results = search_chunks(db, basis_vector(0), top_k=2)
    assert len(results) == 2


def test_search_excludes_chunks_with_no_embedding(db_session):
    db = db_session
    _add_doc_with_chunk(db, "Embedded Doc", basis_vector(0), content="has an embedding")
    _add_doc_with_chunk(db, "Unembedded Doc", None, content="no embedding yet")
    db.commit()

    results = search_chunks(db, basis_vector(0), top_k=10)

    titles = [r["title"] for r in results]
    assert "Embedded Doc" in titles
    assert "Unembedded Doc" not in titles


def test_search_falls_back_to_source_when_no_citation_url(db_session):
    db = db_session
    _add_doc_with_chunk(db, "No Citation Doc", basis_vector(0), citation_url=None)
    _add_doc_with_chunk(db, "Cited Doc", basis_vector(1), citation_url="https://example.com/real-source")
    db.commit()

    results = search_chunks(db, basis_vector(0), top_k=2)
    by_title = {r["title"]: r for r in results}

    assert by_title["No Citation Doc"]["citation_url"] == "test://No Citation Doc"  # falls back to `source`
    assert by_title["Cited Doc"]["citation_url"] == "https://example.com/real-source"


def test_search_returns_section_metadata(db_session):
    db = db_session
    _add_doc_with_chunk(db, "Sectioned Doc", basis_vector(0), section="Protein Recommendations")
    db.commit()

    results = search_chunks(db, basis_vector(0), top_k=1)
    assert results[0]["section"] == "Protein Recommendations"
