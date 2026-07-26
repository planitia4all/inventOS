"""설정 화면의 백업/내보내기 헬퍼 검증."""
from __future__ import annotations

import sqlite3
import zipfile
from io import BytesIO

from src.config.settings import Settings
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService
from src.ui.pages.settings import _build_data_zip, _build_markdown_zip


def _write_real_sqlite_db(path) -> None:
    """`create_consistent_snapshot`(sqlite3 Backup API)이 열 수 있는 진짜 DB 파일을 만든다."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


def test_build_markdown_zip_contains_one_file_per_invention(db_session):
    service = InventionService(db_session)
    inv1 = service.quick_create(QuickIdeaInput(memo="첫번째 아이디어"))
    inv2 = service.quick_create(QuickIdeaInput(memo="두번째 아이디어"))

    zip_bytes = _build_markdown_zip(db_session)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert f"{inv1.invention_no}.md" in names
        assert f"{inv2.invention_no}.md" in names


def test_build_markdown_zip_includes_archived_inventions(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="보관될 아이디어"))
    service.set_archived(inv.id, True)

    zip_bytes = _build_markdown_zip(db_session)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert f"{inv.invention_no}.md" in zf.namelist()


def test_build_data_zip_includes_db_and_attachments(tmp_path):
    settings = Settings(data_dir=tmp_path)
    _write_real_sqlite_db(settings.db_path)
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    (settings.attachments_dir / "inv-1").mkdir()
    (settings.attachments_dir / "inv-1" / "photo.png").write_bytes(b"fake-photo")

    zip_bytes = _build_data_zip(settings)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "inventos.db" in names
        assert "attachments/inv-1/photo.png" in names


def test_build_data_zip_db_entry_is_independently_openable(tmp_path):
    """스냅샷이 원본 read_bytes()가 아니라 sqlite3 Backup API로 만들어졌는지 확인."""
    settings = Settings(data_dir=tmp_path)
    _write_real_sqlite_db(settings.db_path)

    zip_bytes = _build_data_zip(settings)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        db_bytes = zf.read("inventos.db")

    restored = tmp_path / "restored.db"
    restored.write_bytes(db_bytes)
    conn = sqlite3.connect(str(restored))
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    assert ("t",) in tables


def test_build_data_zip_includes_drafts_json(tmp_path):
    settings = Settings(data_dir=tmp_path)
    _write_real_sqlite_db(settings.db_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "drafts.json").write_text('{"some-key": "임시 저장된 내용"}', encoding="utf-8")

    zip_bytes = _build_data_zip(settings)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert "drafts.json" in zf.namelist()
        assert "임시 저장된 내용" in zf.read("drafts.json").decode("utf-8")


def test_build_data_zip_handles_missing_db_and_attachments(tmp_path):
    settings = Settings(data_dir=tmp_path)
    # DB 파일도, 첨부파일 폴더도, drafts.json도 없는 완전히 새 상태 — 예외 없이 빈 zip을 만든다.
    zip_bytes = _build_data_zip(settings)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert zf.namelist() == []
