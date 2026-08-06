"""
Shared fixtures for tests that need a live Postgres+pgvector instance
(search.py's ORM/SQL query logic can't be meaningfully tested without one —
mocking the DB would just be testing that mocks return what you told them
to). Tests using db_session are skipped automatically if no DB is
reachable, so `pytest` still runs cleanly for anyone who hasn't set up
Postgres yet; run `docker compose up` (or see README) to get real coverage
of these.
"""
import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine, init_db
from app.models import Chunk, Document


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()


@pytest.fixture
def db_session():
    if not DB_AVAILABLE:
        pytest.skip("No live Postgres reachable via DATABASE_URL — run `docker compose up` for DB-dependent tests")

    init_db()
    session = SessionLocal()

    # clean slate BEFORE the test too — not just after — so leftover rows
    # from outside the fixture (e.g. manually loading the real corpus while
    # developing) can't silently leak into a test's assertions
    session.query(Chunk).delete()
    session.query(Document).delete()
    session.commit()

    yield session

    session.rollback()
    session.query(Chunk).delete()
    session.query(Document).delete()
    session.commit()
    session.close()
