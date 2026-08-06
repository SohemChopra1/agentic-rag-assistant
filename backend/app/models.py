"""
Two tables:
  - documents: one row per ingested source (a PDF, article URL, or note)
  - chunks: one row per chunk, embedding populated in Phase 2

Embedding dimension is set to 1024 to match Voyage AI's voyage-2 model
(Anthropic's recommended embedding provider — Claude itself doesn't expose
an embeddings endpoint). Change EMBEDDING_DIM here if a different model is
used in Phase 2.
"""
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

EMBEDDING_DIM = 1024


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(20))       # "pdf" | "url" | "file"
    source: Mapped[str] = mapped_column(String(1000))          # file path or URL actually ingested from
    citation_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # original web source, if different from `source`
    content_hash: Mapped[str] = mapped_column(String(64))      # skip re-ingesting unchanged docs
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)  # heading this chunk falls under, if any
    chunk_index: Mapped[int] = mapped_column(Integer)                        # position within the document
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="chunks")
