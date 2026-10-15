"""Database session management utilities."""

import sqlite3
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from common.config import get_settings

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {
    "check_same_thread": False,
    # SQLite serializes writers. Wait briefly for short transactions instead
    # of failing immediately when another service is committing.
    "timeout": 30.0,
} if is_sqlite else {}
engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


if is_sqlite:
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(
        dbapi_connection: sqlite3.Connection,
        _connection_record,
    ) -> None:
        """Configure every SQLite connection for the multi-process local setup."""

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                # Another process may be changing journal mode during startup.
                pass
        finally:
            cursor.close()


def get_db() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        # Roll back any failed transaction before returning the connection.
        db.rollback()
        db.close()
