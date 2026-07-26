from __future__ import annotations

from src.inventions.schemas import InventionInput
from src.inventions.service import InventionService
from src.reports.markdown_exporter import export_invention_markdown, safe_filename


def test_safe_filename_strips_windows_forbidden_characters():
    assert safe_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"


def test_safe_filename_passes_through_normal_invention_no():
    assert safe_filename("INV-2026-00001") == "INV-2026-00001"


def test_safe_filename_falls_back_when_result_is_empty():
    assert safe_filename("") == "untitled"
    assert safe_filename("   ") == "untitled"
    assert safe_filename("...") == "untitled"


def test_safe_filename_strips_control_characters():
    assert safe_filename("title\x00\x1fname") == "title__name"


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
    assert "원본 아이디어" in md
    assert "금속 핀을 먼저 배열하고 유리를 성형한다." in md
    assert "비슷한 기술(선행특허) 목록" in md
    assert "변리사" in md


def test_export_includes_newly_added_detail_fields(db_session):
    service = InventionService(db_session)
    invention = service.create(
        InventionInput(
            original_idea="아이디어 본문",
            key_components="금속 핀, 유리 기재",
            operating_principle="핀 배열 후 유리 성형",
            implementation_method="몰드 성형 장비 필요",
            experiment_notes="1차 시험 완료",
            review_notes="열팽창 계수 확인 필요",
            differentiation="비아 홀 가공이 없다",
        )
    )

    md = export_invention_markdown(invention)

    assert "금속 핀, 유리 기재" in md
    assert "핀 배열 후 유리 성형" in md
    assert "몰드 성형 장비 필요" in md
    assert "1차 시험 완료" in md
    assert "열팽창 계수 확인 필요" in md
    assert "비아 홀 가공이 없다" in md


def test_export_invention_markdown_without_patents_shows_placeholder(db_session):
    service = InventionService(db_session)
    invention = service.create(
        InventionInput(title="테스트 발명", original_idea="아이디어 본문")
    )
    md = export_invention_markdown(invention, patent_links=[])
    assert "연결된 선행특허 없음" in md
