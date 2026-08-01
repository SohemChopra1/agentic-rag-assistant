from pathlib import Path

from app.retrieval.extractors import (
    extract_text_from_file,
    extract_text_from_html,
    extract_text_from_pdf,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_extract_text_from_pdf_recovers_real_content():
    text = extract_text_from_pdf(FIXTURES_DIR / "sample_guideline.pdf")

    assert "Sleep and Recovery" in text
    assert "growth hormone" in text
    assert "Active Recovery" in text
    assert "Nutrition Timing" in text
    assert "glycogen replenishment" in text


def test_extract_text_from_file_dispatches_pdf_by_suffix():
    text = extract_text_from_file(FIXTURES_DIR / "sample_guideline.pdf")
    assert "Sleep and Recovery" in text


def test_extract_text_from_file_reads_markdown_directly(tmp_path):
    md_file = tmp_path / "notes.md"
    md_file.write_text("# Warm-up\n\nDynamic stretching before training reduces injury risk.")

    text = extract_text_from_file(md_file)
    assert "Dynamic stretching" in text


def test_extract_text_from_file_rejects_unsupported_type(tmp_path):
    bad_file = tmp_path / "notes.docx"
    bad_file.write_text("irrelevant")

    try:
        extract_text_from_file(bad_file)
        assert False, "expected ValueError for unsupported file type"
    except ValueError:
        pass


def test_extract_text_from_html_strips_tags_and_scripts():
    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <nav>Home | About</nav>
        <script>trackPageview();</script>
        <h1>Progressive Overload</h1>
        <p>Gradually increasing training stress drives long-term adaptation.</p>
        <footer>Copyright notice</footer>
      </body>
    </html>
    """
    text = extract_text_from_html(html)

    assert "Progressive Overload" in text
    assert "Gradually increasing training stress" in text
    assert "trackPageview" not in text
    assert "color: red" not in text
