"""설정 화면의 백업/내보내기 헬퍼 검증."""
from __future__ import annotations

import zipfile
from io import BytesIO

from src.config.settings import Settings
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService
from src.ui.pages.settings import _build_data_zip, _build_markdown_zip


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
    settings.db_path.write_bytes(b"fake-db-content")
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    (settings.attachments_dir / "inv-1").mkdir()
    (settings.attachments_dir / "inv-1" / "photo.png").write_bytes(b"fake-photo")

    zip_bytes = _build_data_zip(settings)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "inventos.db" in names
        assert "attachments/inv-1/photo.png" in names


def test_build_data_zip_handles_missing_db_and_attachments(tmp_path):
    settings = Settings(data_dir=tmp_path)
    # DB 파일도, 첨부파일 폴더도 없는 완전히 새 상태 — 예외 없이 빈 zip을 만든다.
    zip_bytes = _build_data_zip(settings)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert zf.namelist() == []
