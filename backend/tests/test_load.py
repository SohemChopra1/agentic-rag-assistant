import json

from app.models import Chunk, Document
from app.retrieval.load import load_chunks


def _write_jsonl(tmp_path, records):
    path = tmp_path / "chunks.jsonl"
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path


def _record(title="Doc", source="src", content_hash="hash1", chunk_index=0, content="content", section=None):
    return {
        "source_type": "file",
        "source": source,
        "citation_url": None,
        "title": title,
        "content_hash": content_hash,
        "section": section,
        "chunk_index": chunk_index,
        "content": content,
        "word_count": len(content.split()),
    }


def test_load_inserts_new_documents(db_session, tmp_path):
    path = _write_jsonl(tmp_path, [_record(title="A", chunk_index=0), _record(title="A", chunk_index=1)])
    stats = load_chunks(db_session, path)

    assert stats == {"inserted_docs": 1, "skipped_docs": 0, "inserted_chunks": 2}
    assert db_session.query(Document).count() == 1
    assert db_session.query(Chunk).count() == 2


def test_load_skips_unchanged_document_on_rerun(db_session, tmp_path):
    path = _write_jsonl(tmp_path, [_record(title="A", content_hash="samehash")])
    load_chunks(db_session, path)

    stats = load_chunks(db_session, path)  # re-run with identical content
    assert stats == {"inserted_docs": 0, "skipped_docs": 1, "inserted_chunks": 0}
    assert db_session.query(Document).count() == 1  # not duplicated


def test_load_replaces_document_when_content_hash_changes(db_session, tmp_path):
    path_v1 = _write_jsonl(tmp_path, [_record(title="A", content_hash="v1", content="old content")])
    load_chunks(db_session, path_v1)

    path_v2 = _write_jsonl(tmp_path, [_record(title="A", content_hash="v2", content="new content")])
    stats = load_chunks(db_session, path_v2)

    assert stats["inserted_docs"] == 1
    assert db_session.query(Document).count() == 1  # replaced, not duplicated
    remaining_chunk = db_session.query(Chunk).one()
    assert remaining_chunk.content == "new content"


def test_load_handles_multiple_distinct_documents(db_session, tmp_path):
    path = _write_jsonl(
        tmp_path,
        [
            _record(title="Doc A", source="src-a", content_hash="ha"),
            _record(title="Doc B", source="src-b", content_hash="hb"),
        ],
    )
    stats = load_chunks(db_session, path)

    assert stats["inserted_docs"] == 2
    assert db_session.query(Document).count() == 2
