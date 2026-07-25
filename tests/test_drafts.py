"""작성 중 내용 임시 저장 검증."""
from __future__ import annotations

from src.config.settings import Settings
from src.drafts.store import DraftStore


def _store(tmp_path) -> DraftStore:
    return DraftStore(Settings(data_dir=tmp_path))


def test_saved_draft_survives_new_store_instance(tmp_path):
    """새로고침으로 세션이 사라져도 쓰던 내용이 남아야 한다."""
    _store(tmp_path).save("quick_capture", "쓰다 만 아이디어")
    assert _store(tmp_path).get("quick_capture") == "쓰다 만 아이디어"


def test_missing_draft_returns_empty_string(tmp_path):
    assert _store(tmp_path).get("없는키") == ""


def test_saving_blank_text_removes_draft(tmp_path):
    store = _store(tmp_path)
    store.save("quick_capture", "내용")
    store.save("quick_capture", "   ")
    assert store.get("quick_capture") == ""


def test_clear_removes_draft(tmp_path):
    store = _store(tmp_path)
    store.save("quick_capture", "내용")
    store.clear("quick_capture")
    assert store.get("quick_capture") == ""


def test_drafts_are_isolated_by_key(tmp_path):
    store = _store(tmp_path)
    store.save("a", "가")
    store.save("b", "나")
    assert store.get("a") == "가"
    assert store.get("b") == "나"


def test_corrupted_draft_file_does_not_raise(tmp_path):
    store = _store(tmp_path)
    store.save("quick_capture", "내용")
    store.path.write_text("{ 깨진 json", encoding="utf-8")

    # 임시 저장 파일이 깨져도 글쓰기를 막아서는 안 된다.
    assert store.get("quick_capture") == ""
    store.save("quick_capture", "다시 쓴 내용")
    assert store.get("quick_capture") == "다시 쓴 내용"
