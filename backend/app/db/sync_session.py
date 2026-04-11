"""Sessão síncrona para worker RQ e tarefas bloqueantes."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.url import to_sync_database_url

_sync_url = to_sync_database_url(settings.database_url)
sync_engine = create_engine(_sync_url, echo=False, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)


@contextmanager
def sync_session_scope() -> Generator[Session, None, None]:
    s = SyncSessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
