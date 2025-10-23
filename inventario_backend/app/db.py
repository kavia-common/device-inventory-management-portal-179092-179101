"""
Database initialization and session management for the Inventario backend.

Provides utilities to:
- Build a SQLAlchemy database URL from environment variables
- Initialize an Engine and Session factory
- Provide a scoped session for request handling
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from .models import Base


def _build_db_url_from_env() -> Optional[str]:
    """
    Construct a database URL from POSTGRES_* environment variables if DATABASE_URL is not set.

    Supports variables:
    - POSTGRES_URL (full url) or components:
      POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST (default: localhost), POSTGRES_PORT (default: 5432)
    """
    # If a full URL is provided via POSTGRES_URL use it
    pg_full = os.getenv("POSTGRES_URL")
    if pg_full:
        return pg_full

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")

    if user and password and db:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

    # No sufficient info
    return None


# Module-level singletons after init_db is called
_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None
_scoped: Optional[scoped_session] = None


# PUBLIC_INTERFACE
def init_db(database_url: Optional[str] = None, echo: bool = False) -> Engine:
    """Initialize the SQLAlchemy engine and create all tables if not present.

    Args:
        database_url: The full database URL. If None, will try DATABASE_URL env var,
                      falling back to POSTGRES_* env vars. If still None, raises ValueError.
        echo: If True, SQLAlchemy will log SQL statements.

    Returns:
        Engine: The initialized SQLAlchemy engine.
    """
    global _engine

    url = database_url or os.getenv("DATABASE_URL") or _build_db_url_from_env()
    if not url:
        raise ValueError(
            "Database URL is not configured. Set DATABASE_URL or POSTGRES_* environment variables."
        )

    _engine = create_engine(url, echo=echo, future=True)
    # Ensure tables exist (dev-friendly behavior; in production, use migrations)
    Base.metadata.create_all(_engine)
    return _engine


# PUBLIC_INTERFACE
def init_session() -> scoped_session:
    """Create and return a scoped session bound to the initialized engine.

    Returns:
        scoped_session: Thread-safe scoped session factory.
    """
    global _SessionFactory, _scoped
    if _engine is None:
        raise RuntimeError("Engine is not initialized. Call init_db() first.")

    _SessionFactory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    _scoped = scoped_session(_SessionFactory)
    return _scoped


# PUBLIC_INTERFACE
def get_session() -> Session:
    """Get a SQLAlchemy Session from the scoped session."""
    if _scoped is None:
        raise RuntimeError("Session factory not initialized. Call init_session() first.")
    return _scoped()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
