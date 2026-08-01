"""
Ingests fitness/nutrition/well-being source documents — PDFs, web articles,
plain-text or markdown notes — into chunked JSONL, ready for embedding in
Phase 2.

Sources can be passed individually via --file/--url, or in bulk via a
--manifest JSON file: a list of {"type": "file"|"url", "location": "...",
"title": "..."}.

Usage:
    python -m app.retrieval.ingest --file guidelines.pdf --title "CDC Physical Activity Guidelines"
    python -m app.retrieval.ingest --url https://example.com/article
    python -m app.retrieval.ingest --manifest sources.json
"""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import IO

from app.retrieval.chunker import chunk_text
from app.retrieval.extractors import extract_text_from_file, extract_text_from_html


def fetch_url_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "agentic-rag-assistant-ingest/0.1"})
    with urllib.request.urlopen(req) as response:
        html = response.read().decode("utf-8", errors="ignore")
    return extract_text_from_html(html)


def ingest_source(source_type: str, location: str, title: str, out_f: IO) -> int:
    text = fetch_url_text(location) if source_type == "url" else extract_text_from_file(Path(location))
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    chunks = chunk_text(text)

    for c in chunks:
        record = {
            "source_type": source_type,
            "source": location,
            "title": title,
            "content_hash": content_hash,
            "section": c.section,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "word_count": c.word_count,
        }
        out_f.write(json.dumps(record) + "\n")

    return len(chunks)


def main():
    parser = argparse.ArgumentParser(description="Ingest fitness/nutrition sources into chunked JSONL")
    parser.add_argument("--file", action="append", default=[], help="local file (.pdf/.txt/.md); repeatable")
    parser.add_argument("--url", action="append", default=[], help="article URL; repeatable")
    parser.add_argument("--title", help="title for a single --file/--url source")
    parser.add_argument("--manifest", help="JSON file listing many sources at once")
    parser.add_argument("--out", default="data/chunks.jsonl", help="output JSONL path")
    args = parser.parse_args()

    sources = []
    for f in args.file:
        sources.append({"type": "file", "location": f, "title": args.title or Path(f).stem})
    for u in args.url:
        sources.append({"type": "url", "location": u, "title": args.title or u})
    if args.manifest:
        with open(args.manifest) as mf:
            sources.extend(json.load(mf))

    if not sources:
        parser.error("Provide at least one --file, --url, or --manifest")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_chunks = 0
    with open(out_path, "w") as out_f:
        for src in sources:
            n = ingest_source(src["type"], src["location"], src.get("title", src["location"]), out_f)
            print(f"  {src['title']}: {n} chunks")
            total_chunks += n

    print(f"Ingested {len(sources)} source(s) -> {total_chunks} chunks total")
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
