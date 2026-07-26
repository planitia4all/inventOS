"""FTS5 통합 검색 검증: 제목/원본메모/발명내용/태그/첨부파일명/실험/AI결과/발명번호."""
from __future__ import annotations

from src.ai.results_service import AIResultService
from src.attachments.service import AttachmentService
from src.config.settings import Settings
from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService
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


def test_search_matches_invention_no(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="발명번호 검색 테스트"))
    suffix = inv.invention_no.split("-")[-1]

    results = service.search(keyword=suffix)
    assert inv.id in [r.id for r in results]


def test_search_matches_experiment_records(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="실험 검색 테스트", title="고정 제목"))
    ExperimentService(db_session).create(
        inv.id, ExperimentInput(results="접합강도측정값이크게향상됨")
    )

    results = service.search(keyword="접합강도측정값이크게향상됨")
    assert inv.id in [r.id for r in results]


def test_search_index_updates_after_experiment_deleted(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="실험 삭제 검색 테스트", title="고정 제목2"))
    exp = ExperimentService(db_session).create(
        inv.id, ExperimentInput(results="유일무이한실험결과문구")
    )
    assert inv.id in [r.id for r in service.search(keyword="유일무이한실험결과문구")]

    ExperimentService(db_session).delete(exp.id)
    assert inv.id not in [r.id for r in service.search(keyword="유일무이한실험결과문구")]


def test_search_matches_ai_result_content(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="AI 결과 검색 테스트", title="고정 제목3"))
    AIResultService(db_session).create_draft(
        inv.id, "summary", "그래핀히팅방식으로접합면을가열한다"
    )

    results = service.search(keyword="그래핀히팅방식으로접합면을가열한다")
    assert inv.id in [r.id for r in results]


def test_search_excludes_discarded_ai_result(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="AI 삭제 검색 테스트", title="고정 제목4"))
    result_service = AIResultService(db_session)
    draft = result_service.create_draft(inv.id, "summary", "삭제될고유한AI결과문구")
    assert inv.id in [r.id for r in service.search(keyword="삭제될고유한AI결과문구")]

    result_service.discard(draft.id)
    assert inv.id not in [r.id for r in service.search(keyword="삭제될고유한AI결과문구")]


def test_search_handles_special_characters_without_error(db_session):
    service = InventionService(db_session)
    service.quick_create(QuickIdeaInput(memo="특수문자 테스트"))
    # 특수문자만 있는 검색어는 토큰이 전부 사라져 빈 결과를 반환해야 하고,
    # 예외가 발생하면 안 된다.
    assert service.search(keyword="!@#$%^&*()") == []


def test_search_handles_empty_keyword(db_session):
    service = InventionService(db_session)
    service.quick_create(QuickIdeaInput(memo="빈 검색어 테스트"))
    # 빈 검색어(또는 공백만)는 예외 없이 "필터 없음"과 같은 전체 목록을 반환해야 한다.
    assert [r.id for r in service.search(keyword="")] == [r.id for r in service.search()]
    assert [r.id for r in service.search(keyword="   ")] == [r.id for r in service.search()]


def test_check_integrity_reports_healthy_index(db_session):
    from src.search.fts import SearchIndexService

    service = InventionService(db_session)
    service.quick_create(QuickIdeaInput(memo="정상 색인 테스트"))

    report = SearchIndexService(db_session).check_integrity()
    assert report.is_healthy
    assert report.total_inventions == 1
    assert report.indexed_count == 1


def test_check_integrity_detects_missing_index(db_session):
    from sqlalchemy import text

    from src.search.fts import FTS_TABLE, SearchIndexService

    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="색인 누락 테스트"))
    db_session.execute(
        text(f"DELETE FROM {FTS_TABLE} WHERE invention_id = :id"), {"id": inv.id}
    )

    report = SearchIndexService(db_session).check_integrity()
    assert not report.is_healthy
    assert inv.id in report.missing_ids


def test_check_integrity_detects_orphaned_index(db_session):
    from sqlalchemy import text

    from src.search.fts import FTS_TABLE, SearchIndexService

    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="고아 색인 테스트"))
    service.delete(inv.id)
    # delete()가 정상적으로 색인도 지우므로, 고아 상태를 인위적으로 재현한다.
    db_session.execute(
        text(
            f"INSERT INTO {FTS_TABLE} (invention_id, invention_no, title, original_idea, "
            "content_text, tags, attachment_names, experiment_text, ai_results_text) "
            "VALUES (:id, 'INV-2026-99999', '삭제된 발명', '본문', '', '', '', '', '')"
        ),
        {"id": inv.id},
    )

    report = SearchIndexService(db_session).check_integrity()
    assert not report.is_healthy
    assert inv.id in report.orphaned_ids


def test_check_integrity_detects_stale_title(db_session):
    from sqlalchemy import text

    from src.search.fts import FTS_TABLE, SearchIndexService

    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="오래된 색인 테스트", title="고정 제목"))
    db_session.execute(
        text(f"UPDATE {FTS_TABLE} SET title = '옛날 제목' WHERE invention_id = :id"),
        {"id": inv.id},
    )

    report = SearchIndexService(db_session).check_integrity()
    assert not report.is_healthy
    assert inv.id in report.stale_ids


def test_rebuild_all_fixes_reported_problems(db_session):
    from sqlalchemy import text

    from src.search.fts import FTS_TABLE, SearchIndexService

    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="복구 테스트"))
    db_session.execute(
        text(f"DELETE FROM {FTS_TABLE} WHERE invention_id = :id"), {"id": inv.id}
    )

    index_service = SearchIndexService(db_session)
    assert not index_service.check_integrity().is_healthy

    index_service.rebuild_all()

    assert index_service.check_integrity().is_healthy


def test_reindex_failure_does_not_roll_back_core_content_save(db_session, monkeypatch):
    """검색 색인은 발명/실험/AI결과로부터 다시 만들 수 있는 파생 데이터다 —
    색인 갱신(FTS 테이블 쓰기)이 실패해도, 같은 트랜잭션에서 방금 저장한
    핵심 발명 내용은 롤백되지 않고 그대로 남아 있어야 한다."""
    from src.search.fts import SearchIndexService

    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="색인 실패해도 살아남아야 하는 내용"))

    def broken_delete_index_rows(self, invention_id):
        raise OperationalError("stmt", {}, Exception("색인 테이블 손상(시뮬레이션)"))

    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(
        SearchIndexService, "_delete_index_rows", broken_delete_index_rows
    )

    ok = InventionService(db_session).search_index.reindex_invention(inv.id)
    assert ok is False  # 실패했음을 알린다

    # 색인 갱신은 실패했지만, 핵심 데이터(발명 자체)는 여전히 조회 가능해야 한다.
    still_there = InventionService(db_session).get(inv.id)
    assert still_there is not None
    assert still_there.original_idea == "색인 실패해도 살아남아야 하는 내용"


def test_reindex_failure_allows_subsequent_saves_in_same_session(db_session, monkeypatch):
    """색인 갱신 실패 이후에도 같은 세션을 계속 정상적으로 쓸 수 있어야
    한다 — SAVEPOINT 롤백만 일어나고 세션 전체가 못 쓰게 되면 안 된다."""
    from sqlalchemy.exc import OperationalError

    from src.search.fts import SearchIndexService

    def broken_delete_index_rows(self, invention_id):
        raise OperationalError("stmt", {}, Exception("색인 테이블 손상(시뮬레이션)"))

    monkeypatch.setattr(
        SearchIndexService, "_delete_index_rows", broken_delete_index_rows
    )

    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="색인 실패 이후"))

    # 색인 갱신이 실패한 뒤에도 다른 저장 작업이 정상 동작해야 한다.
    updated = service.update_fields(inv.id, core_principle="세션이 살아있는지 확인")
    assert updated.core_principle == "세션이 살아있는지 확인"
    db_session.commit()
