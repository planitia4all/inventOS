from __future__ import annotations

from src.inventions.schemas import InventionInput
from src.inventions.service import InventionService
from src.reports.markdown_exporter import export_invention_markdown


def test_export_invention_markdown_contains_key_sections(db_session):
    service = InventionService(db_session)
    invention = service.create(
        InventionInput(
            title="유리기판 관통전극",
            original_idea="금속 핀을 먼저 배열하고 유리를 성형한다.",
            problem_to_solve="비아 홀 가공 공정을 줄인다.",
            keywords=["관통전극", "유리기판"],
        )
    )

    md = export_invention_markdown(invention)

    assert "# 유리기판 관통전극" in md
    assert "## 1. 최초 아이디어" in md
    assert "금속 핀을 먼저 배열하고 유리를 성형한다." in md
    assert "## 9. 선행특허 목록" in md
    assert "변리사" in md


def test_export_invention_markdown_without_patents_shows_placeholder(db_session):
    service = InventionService(db_session)
    invention = service.create(
        InventionInput(title="테스트 발명", original_idea="아이디어 본문")
    )
    md = export_invention_markdown(invention, patent_links=[])
    assert "연결된 선행특허 없음" in md
