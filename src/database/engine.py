"""SQLite 엔진 및 세션 생성."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import Settings, get_settings
from src.database.migrations import run_migrations
from src.database.models import Base

_engine = None
_SessionLocal: sessionmaker | None = None


class DataDirectoryError(RuntimeError):
    """데이터 저장 경로를 만들거나 쓸 수 없을 때(권한 없음, 잘못된 경로 등)."""


def init_engine(settings: Settings | None = None):
    """엔진을 초기화하고 테이블이 없으면 생성한다."""
    global _engine, _SessionLocal
    settings = settings or get_settings()
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DataDirectoryError(
            f"데이터 저장 경로를 사용할 수 없습니다: {settings.data_dir} "
            f"(원인: {exc}). INVENTOS_DATA_DIR 설정이나 폴더 쓰기 권한을 확인하세요."
        ) from exc

    _engine = create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(_engine)
    # 기존 DB에 나중에 추가된 컬럼을 채워 넣는다 (데이터 보존).
    run_migrations(_engine)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
