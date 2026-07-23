"""Single synchronous SQLAlchemy engine (psycopg3).

``DATABASE_URL`` must be a psycopg3 URL, e.g.
``postgresql+psycopg://user:pass@supabase-db:5432/postgres``.
"""
import os
import time
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

_engine = None
_SessionLocal = None


def _init():
    global _engine, _SessionLocal
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            future=True,
        )
        _SessionLocal = sessionmaker(
            bind=_engine, expire_on_commit=False, class_=Session
        )
    return _engine, _SessionLocal


def get_engine():
    return _init()[0]


def wait_for_db(timeout: int = 60, interval: float = 2.0) -> None:
    """Block until the database accepts connections (used at startup)."""
    engine, _ = _init()
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001 - retry on any connection error
            last_err = exc
            logger.info("Waiting for database to become available...")
            time.sleep(interval)
    raise RuntimeError(f"Database not reachable after {timeout}s: {last_err}")


@contextmanager
def session_scope():
    """Transactional scope for pipeline/worker-thread DB writes."""
    _, SessionLocal = _init()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI dependency yielding a session (committed on success)."""
    _, SessionLocal = _init()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
