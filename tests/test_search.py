"""FTS5 통합 검색 검증: 제목/원본메모/발명내용/태그/첨부파일명."""
from __future__ import annotations

from src.attachments.service import AttachmentService
from src.config.settings import Settings
from src.inventions.schemas import InventionInput, QuickIdeaInput
from src.inventions.service import InventionService


def test_search_matches_title(db_session):
    service = InventionService(db_session)
    inv = service.create(InventionInput(title="유리기판 관통전극", original_idea="본문"))
    service.create(InventionInput(title="배터리 냉각 구조", original_idea="본문2"))

    results = service.search(keyword="유리기판")
    assert [r.id for r in results] == [inv.id]


def test_search_matches_original_idea(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(
        QuickIdeaInput(memo="금속 핀을 먼저 배열하고 유리를 성형한다")
    )
    results = service.search(keyword="핀")
    assert inv.id in [r.id for r in results]


def test_search_matches_detail_content_field(db_session):
    service = InventionService(db_session)
    inv = service.create(InventionInput(title="발명", original_idea="본문"))
    service.update_fields(inv.id, core_principle="그래핀 히팅 방식으로 접합한다")

    results = service.search(keyword="그래핀")
    assert inv.id in [r.id for r in results]


def test_search_matches_tags(db_session):
    service = InventionService(db_session)
    inv = service.create(
        InventionInput(title="발명", original_idea="본문", keywords=["Battery", "Marine"])
    )
    results = service.search(keyword="Battery")
    assert inv.id in [r.id for r in results]


def test_search_matches_attachment_filename(db_session, tmp_path):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="첨부 검색 테스트"))
    AttachmentService(db_session, settings=Settings(data_dir=tmp_path)).save(
        inv.id, "실험결과_1차.png", b"fake"
    )

    results = service.search(keyword="실험결과")
    assert inv.id in [r.id for r in results]


def test_search_excludes_unrelated_inventions(db_session):
    service = InventionService(db_session)
    service.create(InventionInput(title="유리기판 관통전극", original_idea="본문"))
    unrelated = service.create(InventionInput(title="로봇 팔 제어", original_idea="다른 내용"))

    results = service.search(keyword="유리기판")
    assert unrelated.id not in [r.id for r in results]


def test_search_index_updates_after_edit(db_session):
    # 제목을 고정해 둔다 — 안 그러면 자동 생성 제목이 옛 원본 문구를 그대로
    # 담고 있어서(예: 제목이 "원본 텍스트") 검색어가 계속 남아 있는 것처럼
    # 보일 수 있다.
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="원본 텍스트", title="고정 제목"))
    assert inv.id in [r.id for r in service.search(keyword="원본")]

    service.update_original_idea(inv.id, "완전히 다른 새 텍스트")
    assert inv.id not in [r.id for r in service.search(keyword="원본")]
    assert inv.id in [r.id for r in service.search(keyword="새")]


def test_search_index_removed_after_delete(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="삭제될 아이디어"))
    service.delete(inv.id)

    results = service.search(keyword="삭제될", include_archived=True)
    assert results == []


def test_search_supports_prefix_matching(db_session):
    service = InventionService(db_session)
    inv = service.create(InventionInput(title="발명", original_idea="자동화 시스템 설계"))

    results = service.search(keyword="자동")
    assert inv.id in [r.id for r in results]


def test_search_returns_empty_for_no_match(db_session):
    service = InventionService(db_session)
    service.quick_create(QuickIdeaInput(memo="아무 내용"))
    assert service.search(keyword="존재하지않는검색어절대없음") == []


def test_search_combined_with_status_filter(db_session):
    service = InventionService(db_session)
    inv = service.create(InventionInput(title="유리기판", original_idea="본문", status="검토 중"))
    service.create(InventionInput(title="유리기판 다른 발명", original_idea="본문2"))

    results = service.search(keyword="유리기판", status="검토 중")
    assert [r.id for r in results] == [inv.id]
