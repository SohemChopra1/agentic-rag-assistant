"""
Database engine + session management.

Requires the `vector` extension enabled in Postgres — the pgvector/pgvector
Docker image (used in docker-compose.yml) has this preinstalled; just run
`CREATE EXTENSION IF NOT EXISTS vector;` once (see init_db() below).
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Enable pgvector extension and create tables. Call once at startup.

    The import below is deliberate and load-bearing, not decorative:
    SQLAlchemy's Base.metadata only knows about model classes that have
    actually been imported somewhere in the process — that's how a model
    registers its table onto the shared metadata. Without this import,
    calling init_db() before anything else has imported app.models creates
    the pgvector extension successfully but silently creates ZERO tables —
    no error, just an empty database that fails much later on the first
    real query. Importing here (not at module level, which would be a
    circular import since models.py imports Base from this file) makes
    init_db() self-sufficient regardless of what else has run first.
    """
    from app import models  # noqa: F401 — import-for-side-effect, registers Document/Chunk

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
