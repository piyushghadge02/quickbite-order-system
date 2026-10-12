"""SQLite engine and session factory, shared by the API and all workers."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .config import settings
from .models import Base

# check_same_thread=False: the API serves requests on multiple threads.
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    # WAL mode: readers don't block the writer, so the API and workers can
    # share one database file. busy_timeout: wait up to 5s on a locked
    # database instead of failing immediately.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(db_engine=None) -> None:
    """Create tables if they don't exist. Safe to call from every service."""
    Base.metadata.create_all(db_engine or engine)


def get_db():
    """FastAPI dependency: one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
