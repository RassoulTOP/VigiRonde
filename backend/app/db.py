from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind=engine) -> None:
    """Crée l'extension PostGIS et les tables (les migrations Alembic viendront en phase 5)."""
    from app import models  # noqa: F401  (enregistre les modèles)

    with bind.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
