import io
import json
from pathlib import Path

from app.retrieval.ingest import ingest_source

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_ingest_source_from_pdf_produces_valid_jsonl_records():
    buf = io.StringIO()
    n_chunks = ingest_source(
        source_type="file",
        location=str(FIXTURES_DIR / "sample_guideline.pdf"),
        title="Exercise Recovery Basics (test fixture)",
        out_f=buf,
    )

    lines = buf.getvalue().strip().split("\n")
    assert len(lines) == n_chunks
    assert n_chunks >= 1

    records = [json.loads(line) for line in lines]
    first = records[0]

    assert first["source_type"] == "file"
    assert first["title"] == "Exercise Recovery Basics (test fixture)"
    assert first["chunk_index"] == 0
    assert "growth hormone" in first["content"]
    assert len(first["content_hash"]) == 64  # sha256 hex digest


def test_ingest_source_from_markdown_note(tmp_path):
    note = tmp_path / "hydration.md"
    note.write_text("# Hydration\n\nDrink water consistently throughout the day, not just around workouts.")

    buf = io.StringIO()
    n_chunks = ingest_source(source_type="file", location=str(note), title="Hydration Notes", out_f=buf)

    records = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    assert n_chunks == 1
    assert records[0]["section"] == "Hydration"
    assert "Drink water" in records[0]["content"]
