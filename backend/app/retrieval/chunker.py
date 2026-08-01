"""
Chunks prose documents (guideline PDFs, articles, notes) for retrieval.

Unlike code, prose has no syntactic boundaries (no functions/classes) to
chunk on. Strategy instead: split into paragraphs, treat markdown-style
headings as section boundaries (tracked as metadata so retrieved chunks
carry a "section" label for citation, e.g. "Protein Recommendations"), and
greedily pack paragraphs into ~TARGET_CHUNK_WORDS-sized chunks so each
chunk is topically coherent rather than an arbitrary character slice. A
small word overlap is carried into the next chunk so a sentence split
across a chunk boundary still has context on both sides.

Any single paragraph longer than MAX_CHUNK_WORDS (common with PDF
extraction, which sometimes collapses a whole page into one paragraph)
gets further split by sentence.
"""
import re
from dataclasses import dataclass

TARGET_CHUNK_WORDS = 180
MAX_CHUNK_WORDS = 260
OVERLAP_WORDS = 30

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class TextChunk:
    section: str | None
    chunk_index: int
    content: str
    word_count: int


def chunk_text(text: str) -> list[TextChunk]:
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[TextChunk] = []
    current_section: str | None = None
    buffer: list[str] = []
    buffer_words = 0

    def flush():
        nonlocal buffer, buffer_words
        content = "\n\n".join(buffer).strip()
        if content:
            chunks.append(TextChunk(current_section, len(chunks), content, len(content.split())))
        buffer = []
        buffer_words = 0

    for para in paragraphs:
        lines = para.split("\n")
        heading_match = _HEADING_RE.match(lines[0])
        if heading_match:
            flush()
            current_section = heading_match.group(2).strip()
            para = "\n".join(lines[1:]).strip()
            if not para:
                continue

        para_words = len(para.split())

        if para_words > MAX_CHUNK_WORDS:
            flush()
            for sub in _split_long_paragraph(para):
                chunks.append(TextChunk(current_section, len(chunks), sub, len(sub.split())))
            continue

        if buffer_words + para_words > TARGET_CHUNK_WORDS and buffer:
            flush()
            if chunks:
                overlap_words = chunks[-1].content.split()[-OVERLAP_WORDS:]
                overlap = " ".join(overlap_words)
                buffer = [overlap]
                buffer_words = len(overlap_words)

        buffer.append(para)
        buffer_words += para_words

    flush()
    return chunks


def _split_paragraphs(text: str) -> list[str]:
    raw = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in raw if p.strip()]


def _split_long_paragraph(para: str) -> list[str]:
    sentences = _SENTENCE_SPLIT_RE.split(para)
    sub_chunks = []
    buffer: list[str] = []
    buffer_words = 0

    for sent in sentences:
        sent_words = len(sent.split())
        if buffer_words + sent_words > TARGET_CHUNK_WORDS and buffer:
            sub_chunks.append(" ".join(buffer))
            buffer = []
            buffer_words = 0
        buffer.append(sent)
        buffer_words += sent_words

    if buffer:
        sub_chunks.append(" ".join(buffer))

    return sub_chunks
