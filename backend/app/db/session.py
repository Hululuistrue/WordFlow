from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db import models  # noqa: F401


def _create_engine(settings: Settings) -> Engine:
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        echo=settings.database_echo,
        future=True,
        connect_args=connect_args,
    )


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return _create_engine(settings)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def init_database() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations(engine)


def _apply_lightweight_migrations(engine: Engine) -> None:
    # Keep local sqlite dev DB compatible when models add optional columns.
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info('jobs')").fetchall()
        columns = {row[1] for row in rows}
        if "youtube_use_cookies" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE jobs ADD COLUMN youtube_use_cookies BOOLEAN NOT NULL DEFAULT 0"
            )
        if "youtube_client" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE jobs ADD COLUMN youtube_client VARCHAR(32) NOT NULL DEFAULT 'web'"
            )
        if "youtube_mode" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE jobs ADD COLUMN youtube_mode VARCHAR(16) NOT NULL DEFAULT 'compat'"
            )
        if "youtube_cookies_txt" not in columns:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN youtube_cookies_txt TEXT")

        transcript_rows = conn.exec_driver_sql("PRAGMA table_info('transcripts')").fetchall()
        transcript_columns = {row[1] for row in transcript_rows}
        if "title" not in transcript_columns:
            conn.exec_driver_sql("ALTER TABLE transcripts ADD COLUMN title VARCHAR(255)")


def get_db_session() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
