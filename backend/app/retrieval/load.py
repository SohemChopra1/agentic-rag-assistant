"""
Loads chunks from a JSONL file (produced by ingest.py) into the database.

Skips documents whose content_hash already matches what's stored, so
re-running after ingest.py picks up new or changed sources without
duplicating unchanged ones. If a document's content changed (different
hash), the old document and its chunks are replaced (cascade delete) with
the new version.

Usage:
    python -m app.retrieval.load --in ../data/chunks.jsonl
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Chunk, Document


def load_chunks(db: Session, jsonl_path: Path) -> dict:
    with open(jsonl_path) as f:
        records = [json.loads(line) for line in f]

    docs_in_file: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        docs_in_file.setdefault((r["title"], r["source"]), []).append(r)

    inserted_docs = 0
    skipped_docs = 0
    inserted_chunks = 0

    for (title, source), doc_records in docs_in_file.items():
        content_hash = doc_records[0]["content_hash"]
        existing = db.execute(select(Document).where(Document.title == title, Document.source == source)).scalar_one_or_none()

        if existing is not None and existing.content_hash == content_hash:
            skipped_docs += 1
            continue

        if existing is not None:
            db.delete(existing)  # content changed — replace it and its chunks (cascade)
            db.flush()

        doc = Document(
            title=title,
            source_type=doc_records[0]["source_type"],
            source=source,
            citation_url=doc_records[0]["citation_url"],
            content_hash=content_hash,
        )
        db.add(doc)
        db.flush()
        inserted_docs += 1

        for r in doc_records:
            db.add(
                Chunk(
                    document_id=doc.id,
                    section=r["section"],
                    chunk_index=r["chunk_index"],
                    content=r["content"],
                    word_count=r["word_count"],
                    embedding=None,
                )
            )
            inserted_chunks += 1

    db.commit()
    return {"inserted_docs": inserted_docs, "skipped_docs": skipped_docs, "inserted_chunks": inserted_chunks}


def main():
    parser = argparse.ArgumentParser(description="Load chunked JSONL into the database")
    parser.add_argument("--in", dest="in_path", default="../data/chunks.jsonl", help="input JSONL path")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        stats = load_chunks(db, Path(args.in_path))
        print(f"Inserted {stats['inserted_docs']} new/changed document(s), {stats['inserted_chunks']} chunks")
        print(f"Skipped {stats['skipped_docs']} unchanged document(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
