"""
Extracts plain text from different source formats so the chunker only ever
has to deal with plain text, regardless of whether it came from a PDF, a
web article, or a markdown note.
"""
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader


def extract_text_from_pdf(path: Path) -> str:
    """PDF extraction returns text with hard line breaks wherever the PDF
    visually wraps a line — that's a rendering artifact, not a real
    paragraph break, and left as-is it fragments phrases mid-word-boundary
    (e.g. "glycogen\\nreplenishment" instead of "glycogen replenishment").
    Collapse those within a page into spaces; treat page boundaries as the
    paragraph separator instead, since PDFs don't expose real paragraph
    structure without layout-aware parsing.

    Known limitation: this means sub-page section headings aren't detected
    from text alone (unlike markdown's '#'). A future improvement could use
    the PDF's bookmark/outline metadata (reader.outline) for real section
    titles where the source PDF provides one.
    """
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        raw = page.extract_text() or ""
        collapsed = " ".join(line.strip() for line in raw.splitlines() if line.strip())
        pages.append(collapsed)
    return "\n\n".join(pages)


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {suffix}")
