import os
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

# Load environment variables from .env file
load_dotenv()


def get_database_url() -> str:
    """Retrieve and normalize the DATABASE_URL environment variable."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "The DATABASE_URL environment variable is not set. "
            "Please create a .env file in the project root containing your Aiven connection URL."
        )

    # Normalize driver prefix for SQLAlchemy 2.0 (e.g., postgres:// or postgresql:// -> postgresql+psycopg://)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    return db_url


def get_engine():
    """Create and return a SQLAlchemy Engine with connection pooling."""
    db_url = get_database_url()

    # Secure PostgreSQL connection for cloud database (Aiven)
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    return engine


# Lazily instantiated global engine
_engine = None


def get_db_engine():
    """Retrieve or create the global SQLAlchemy Engine instance."""
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


def get_session_factory():
    """Create a configured sessionmaker bound to the global engine."""
    engine = get_db_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency injection / Context manager helper for obtaining database sessions."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> dict:
    """Validate database connectivity and verify PostGIS extension status."""
    engine = get_db_engine()
    with engine.connect() as connection:
        pg_version = connection.execute(text("SELECT version();")).scalar()
        postgis_version = connection.execute(
            text("SELECT PostGIS_Version();")
        ).scalar()

        return {
            "status": "connected",
            "postgres_version": pg_version,
            "postgis_version": postgis_version,
        }
