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


def test_invention_no_resets_per_year(db_session):
    from src.inventions.repository import InventionRepository

    repo = InventionRepository(db_session)
    assert repo.next_invention_no(2026) == "INV-2026-00001"
    assert repo.next_invention_no(2027) == "INV-2027-00001"


def test_invention_no_is_5_digit_padded(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    suffix = invention.invention_no.split("-")[-1]
    assert len(suffix) == 5
    assert suffix.isdigit()


def test_duplicate_invention_no_rejected_at_db_level(db_session):
    """next_invention_no()가 계산을 잘못하더라도(예: 동시 생성 경합), DB의
    UNIQUE 제약이 마지막 방어선으로 중복 발명번호 저장을 막아야 한다."""
    from sqlalchemy.exc import IntegrityError

    from src.database.models import Invention

    service = InventionService(db_session)
    existing = service.create(make_input())

    duplicate = Invention(
        invention_no=existing.invention_no,  # 일부러 같은 번호 사용
        title="중복 번호 테스트",
        original_idea="본문",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_create_retries_when_invention_no_collides(db_session, monkeypatch):
    """동시 생성 경합으로 next_invention_no()가 이미 쓰인 번호를 계산해도
    (더블클릭, 여러 탭 등) 자동으로 다시 계산해 재시도해야 한다 — 사용자에게
    원문 IntegrityError가 보이면 안 된다."""
    from src.inventions.repository import InventionRepository

    service = InventionService(db_session)
    existing = service.create(make_input())
    db_session.commit()  # 실제로는 별도의(이미 커밋된) 세션에서 만들어진 발명이다

    calls = {"count": 0}

    def flaky_next(self, year):
        calls["count"] += 1
        if calls["count"] == 1:
            return existing.invention_no  # 일부러 충돌시킨다
        return "INV-2026-09999"

    monkeypatch.setattr(InventionRepository, "next_invention_no", flaky_next)

    second = service.create(make_input(title="충돌 후 생성"))

    assert second.invention_no != existing.invention_no
    assert calls["count"] == 2


def test_create_raises_clear_error_after_exhausting_retries(db_session, monkeypatch):
    """계속 충돌하면(비정상 상황) 원문 IntegrityError 대신 이해할 수 있는
    예외를 던져야 한다."""
    from src.inventions.repository import InventionRepository

    service = InventionService(db_session)
    existing = service.create(make_input())
    db_session.commit()

    monkeypatch.setattr(
        InventionRepository,
        "next_invention_no",
        lambda self, year: existing.invention_no,
    )

    with pytest.raises(RuntimeError, match="발명번호"):
        service.create(make_input(title="계속 충돌"))


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
