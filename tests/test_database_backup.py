"""SQLite 온라인 백업 스냅샷 검증."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

from src.database.backup import backup_to_file, create_consistent_snapshot
from src.database.models import Base, Invention


def _make_db_with_inventions(tmp_path: Path, count: int) -> Path:
    db_path = tmp_path / "inventos.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=engine)()
    try:
        for i in range(count):
            session.add(
                Invention(
                    invention_no=f"INV-2026-{i:05d}",
                    title=f"발명 {i}",
                    original_idea=f"본문 {i}",
                    status="아이디어",
                    version=1,
                )
            )
        session.commit()
    finally:
        session.close()
    engine.dispose()
    return db_path


def test_snapshot_returns_none_when_db_missing(tmp_path):
    assert create_consistent_snapshot(tmp_path / "no_such.db") is None


def test_snapshot_is_openable_and_has_matching_row_count(tmp_path):
    db_path = _make_db_with_inventions(tmp_path, count=5)

    snapshot_bytes = create_consistent_snapshot(db_path)
    assert snapshot_bytes is not None

    snapshot_path = tmp_path / "snapshot.db"
    snapshot_path.write_bytes(snapshot_bytes)

    conn = sqlite3.connect(str(snapshot_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM inventions").fetchone()[0]
    finally:
        conn.close()
    assert count == 5


def test_snapshot_matches_original_row_count(tmp_path):
    db_path = _make_db_with_inventions(tmp_path, count=3)

    original_conn = sqlite3.connect(str(db_path))
    try:
        original_count = original_conn.execute("SELECT COUNT(*) FROM inventions").fetchone()[0]
    finally:
        original_conn.close()

    snapshot_bytes = create_consistent_snapshot(db_path)
    snapshot_path = tmp_path / "snapshot2.db"
    snapshot_path.write_bytes(snapshot_bytes)
    snap_conn = sqlite3.connect(str(snapshot_path))
    try:
        snapshot_count = snap_conn.execute("SELECT COUNT(*) FROM inventions").fetchone()[0]
    finally:
        snap_conn.close()

    assert snapshot_count == original_count == 3


def test_backup_to_file_returns_false_when_db_missing(tmp_path):
    assert backup_to_file(tmp_path / "no_such.db", tmp_path / "dest.db") is False


def test_backup_to_file_creates_independently_openable_copy(tmp_path):
    db_path = _make_db_with_inventions(tmp_path, count=4)
    dest_path = tmp_path / "inventos_backup_20260101_000000.db"

    ok = backup_to_file(db_path, dest_path)

    assert ok is True
    assert dest_path.exists()
    conn = sqlite3.connect(str(dest_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM inventions").fetchone()[0]
    finally:
        conn.close()
    assert count == 4
