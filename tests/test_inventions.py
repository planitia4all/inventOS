from __future__ import annotations

import pytest

from src.inventions.schemas import InventionInput, QuickIdeaInput
from src.inventions.service import InventionService, generate_title


def make_input(**overrides) -> InventionInput:
    data = dict(title="유리기판 관통전극", original_idea="금속 핀을 먼저 배열한다.")
    data.update(overrides)
    return InventionInput(**data)


def test_create_invention_requires_idea_content(db_session):
    service = InventionService(db_session)
    with pytest.raises(ValueError):
        service.create(InventionInput(title="제목만 있음", original_idea=""))


def test_create_invention_minimal_fields(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    assert invention.id
    assert invention.status == "아이디어"
    assert invention.invention_no.startswith("INV-")


def test_invention_no_increments_sequentially(db_session):
    service = InventionService(db_session)
    first = service.create(make_input(title="발명 1"))
    second = service.create(make_input(title="발명 2"))
    first_seq = int(first.invention_no.split("-")[-1])
    second_seq = int(second.invention_no.split("-")[-1])
    assert second_seq == first_seq + 1


def test_update_invention(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    updated = service.update(
        invention.id, make_input(title="수정된 제목", status="완료")
    )
    assert updated.title == "수정된 제목"
    assert updated.status == "완료"


def test_delete_invention(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    service.delete(invention.id)
    assert service.get(invention.id) is None


def test_archive_invention_excluded_from_default_list(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    service.set_archived(invention.id, True)
    assert invention.id not in [i.id for i in service.list()]
    assert invention.id in [i.id for i in service.list(include_archived=True)]


def test_save_revision_creates_snapshot(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    revision = service.save_revision(invention.id, change_note="첫 버전")
    assert revision.revision_no == 1
    assert revision.snapshot_json["title"] == invention.title

    service.update(invention.id, make_input(title="다음 버전"))
    revision2 = service.save_revision(invention.id, change_note="두번째 버전")
    assert revision2.revision_no == 2

    revisions = service.list_revisions(invention.id)
    assert len(revisions) == 2


def test_search_by_keyword(db_session):
    service = InventionService(db_session)
    service.create(make_input(title="유리기판 발명"))
    service.create(make_input(title="배터리 발명"))
    results = service.search(keyword="유리기판")
    assert len(results) == 1
    assert results[0].title == "유리기판 발명"


# ----------------------------------------------------------------------
# 빠른 기록 / 제목 자동 생성
# ----------------------------------------------------------------------


def test_generate_title_uses_first_sentence():
    assert generate_title("금속 핀을 배열한다. 그리고 유리를 성형한다.") == "금속 핀을 배열한다"


def test_generate_title_truncates_long_text():
    title = generate_title("가" * 100)
    assert title.endswith("...")
    assert len(title) <= 43


def test_generate_title_falls_back_to_date():
    title = generate_title("   ")
    assert title.endswith("아이디어")


def test_quick_create_requires_only_memo(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(QuickIdeaInput(memo="유리에 금속 핀을 심는다"))
    assert invention.title == "유리에 금속 핀을 심는다"
    assert invention.original_idea == "유리에 금속 핀을 심는다"


def test_quick_create_rejects_empty_memo(db_session):
    service = InventionService(db_session)
    with pytest.raises(ValueError):
        service.quick_create(QuickIdeaInput(memo="   "))


def test_quick_create_keeps_user_title(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(
        QuickIdeaInput(memo="본문 내용", title="내가 정한 제목")
    )
    assert invention.title == "내가 정한 제목"


# ----------------------------------------------------------------------
# 원본 보존
# ----------------------------------------------------------------------


def test_editing_original_idea_keeps_previous_version(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(QuickIdeaInput(memo="처음 적은 내용"))

    service.update_original_idea(invention.id, "고쳐 쓴 내용")

    assert service.get(invention.id).original_idea == "고쳐 쓴 내용"
    revisions = service.list_revisions(invention.id)
    assert len(revisions) == 1
    assert revisions[0].snapshot_json["original_idea"] == "처음 적은 내용"


def test_editing_original_with_same_text_creates_no_revision(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(QuickIdeaInput(memo="같은 내용"))
    service.update_original_idea(invention.id, "같은 내용")
    assert service.list_revisions(invention.id) == []


def test_update_original_idea_rejects_empty(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(QuickIdeaInput(memo="내용"))
    with pytest.raises(ValueError):
        service.update_original_idea(invention.id, "  ")


def test_update_snapshots_original_when_it_changes(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input(original_idea="원본 A"))
    service.update(invention.id, make_input(original_idea="원본 B"))

    revisions = service.list_revisions(invention.id)
    assert len(revisions) == 1
    assert revisions[0].snapshot_json["original_idea"] == "원본 A"


def test_update_fields_cannot_touch_original_idea(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(QuickIdeaInput(memo="원본"))
    with pytest.raises(ValueError):
        service.update_fields(invention.id, original_idea="몰래 덮어쓰기")
    assert service.get(invention.id).original_idea == "원본"


def test_update_fields_saves_detail_sections(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(QuickIdeaInput(memo="원본"))
    service.update_fields(
        invention.id, problem_to_solve="가공 공정이 길다", experiment_notes="1차 시험"
    )
    saved = service.get(invention.id)
    assert saved.problem_to_solve == "가공 공정이 길다"
    assert saved.experiment_notes == "1차 시험"
    assert saved.original_idea == "원본"


# ----------------------------------------------------------------------
# 홈 화면용 목록
# ----------------------------------------------------------------------


def test_toggle_favorite(db_session):
    service = InventionService(db_session)
    invention = service.quick_create(QuickIdeaInput(memo="메모"))
    assert invention.is_favorite is False

    service.toggle_favorite(invention.id)
    assert service.get(invention.id).is_favorite is True
    assert [i.id for i in service.list_favorites()] == [invention.id]

    service.toggle_favorite(invention.id)
    assert service.get(invention.id).is_favorite is False
    assert service.list_favorites() == []


def test_needs_review_lists_only_uncurated_ideas(db_session):
    service = InventionService(db_session)
    raw = service.quick_create(QuickIdeaInput(memo="아직 정리 안 함"))
    curated = service.quick_create(QuickIdeaInput(memo="정리한 것"))
    service.update_fields(curated.id, refined_content="정리된 내용")

    ids = [i.id for i in service.list_needs_review()]
    assert raw.id in ids
    assert curated.id not in ids


def test_list_recent_respects_limit(db_session):
    service = InventionService(db_session)
    for i in range(4):
        service.quick_create(QuickIdeaInput(memo=f"메모 {i}"))
    assert len(service.list_recent(limit=2)) == 2
