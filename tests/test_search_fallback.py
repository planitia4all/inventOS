"""FTS를 쓸 수 없을 때의 대체(ILIKE) 검색이 FTS와 같은 범위를 훑는지 검증.

`InventionRepository.search()`를 직접 호출해 fallback 경로만 테스트한다
(정상 경로는 FTS 우선이라 `InventionService.search()`를 쓰면 이 코드를
지나치지 못할 수 있다).
"""
from __future__ import annotations

from src.ai.results_service import AIResultService
from src.attachments.service import AttachmentService
from src.config.settings import Settings
from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService
from src.inventions.repository import InventionRepository
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService


def make_invention(session, **kwargs):
    return InventionService(session).quick_create(QuickIdeaInput(**kwargs))


def test_fallback_matches_invention_no(db_session):
    inv = make_invention(db_session, memo="발명번호 fallback 테스트")
    suffix = inv.invention_no.split("-")[-1]

    results = InventionRepository(db_session).search(keyword=suffix)
    assert inv.id in [r.id for r in results]


def test_fallback_matches_title_and_original_idea(db_session):
    inv = make_invention(db_session, memo="원본메모 fallback 고유문구")
    results = InventionRepository(db_session).search(keyword="고유문구")
    assert inv.id in [r.id for r in results]


def test_fallback_matches_refined_content_field(db_session):
    inv = make_invention(db_session, memo="발명")
    InventionService(db_session).update_fields(inv.id, core_principle="그래핀히팅fallback")
    results = InventionRepository(db_session).search(keyword="그래핀히팅fallback")
    assert inv.id in [r.id for r in results]


def test_fallback_matches_tags(db_session):
    inv = make_invention(db_session, memo="발명", keywords=["FallbackTag"])
    results = InventionRepository(db_session).search(keyword="FallbackTag")
    assert inv.id in [r.id for r in results]


def test_fallback_matches_attachment_filename(db_session, tmp_path):
    inv = make_invention(db_session, memo="발명")
    AttachmentService(db_session, settings=Settings(data_dir=tmp_path)).save(
        inv.id, "fallback실험사진.png", b"fake"
    )
    results = InventionRepository(db_session).search(keyword="fallback실험사진")
    assert inv.id in [r.id for r in results]


def test_fallback_matches_experiment_records(db_session):
    inv = make_invention(db_session, memo="발명")
    ExperimentService(db_session).create(
        inv.id, ExperimentInput(results="fallback고유실험결과문구")
    )
    results = InventionRepository(db_session).search(keyword="fallback고유실험결과문구")
    assert inv.id in [r.id for r in results]


def test_fallback_matches_ai_result_content(db_session):
    inv = make_invention(db_session, memo="발명")
    AIResultService(db_session).create_draft(
        inv.id, "summary", "fallback고유AI결과문구"
    )
    results = InventionRepository(db_session).search(keyword="fallback고유AI결과문구")
    assert inv.id in [r.id for r in results]


def test_fallback_excludes_deleted_ai_result(db_session):
    inv = make_invention(db_session, memo="발명")
    service = AIResultService(db_session)
    draft = service.create_draft(inv.id, "summary", "fallback삭제될AI결과")
    service.discard(draft.id)
    results = InventionRepository(db_session).search(keyword="fallback삭제될AI결과")
    assert inv.id not in [r.id for r in results]


def test_fallback_excludes_unrelated_invention(db_session):
    make_invention(db_session, memo="유리기판 관통전극")
    unrelated = make_invention(db_session, memo="로봇 팔 제어")
    results = InventionRepository(db_session).search(keyword="유리기판")
    assert unrelated.id not in [r.id for r in results]
