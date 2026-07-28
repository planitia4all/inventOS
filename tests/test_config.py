"""설정 로딩 안전성 검증: 잘못된 환경변수로 앱이 죽지 않아야 한다."""
from __future__ import annotations

import pytest

from src.config.settings import APP_VERSION, Settings, _load_app_version, _safe_int
from src.database.engine import DataDirectoryError, init_engine


def test_safe_int_returns_default_for_non_numeric(monkeypatch):
    monkeypatch.setenv("TEST_INVENTOS_INT", "abc")
    assert _safe_int("TEST_INVENTOS_INT", 20) == 20


def test_safe_int_returns_default_for_empty_string(monkeypatch):
    monkeypatch.setenv("TEST_INVENTOS_INT", "")
    assert _safe_int("TEST_INVENTOS_INT", 20) == 20


def test_safe_int_parses_valid_value(monkeypatch):
    monkeypatch.setenv("TEST_INVENTOS_INT", "42")
    assert _safe_int("TEST_INVENTOS_INT", 20) == 42


def test_safe_int_returns_default_when_unset(monkeypatch):
    monkeypatch.delenv("TEST_INVENTOS_INT", raising=False)
    assert _safe_int("TEST_INVENTOS_INT", 20) == 20


def test_init_engine_creates_nonexistent_data_dir(tmp_path):
    settings = Settings(data_dir=tmp_path / "does" / "not" / "exist" / "yet")
    init_engine(settings)
    assert settings.data_dir.exists()


def test_init_engine_handles_korean_and_space_paths(tmp_path):
    settings = Settings(data_dir=tmp_path / "한글 경로 테스트 폴더")
    init_engine(settings)
    assert settings.db_path.parent.exists()


def test_init_engine_raises_clear_error_when_data_dir_unwritable(tmp_path):
    """폴더를 만들 수 없는 경로(예: 이미 파일이 그 자리에 있음)면, 원문
    OSError 대신 이해할 수 있는 DataDirectoryError를 던져야 한다."""
    blocking_file = tmp_path / "blocked"
    blocking_file.write_text("이 자리는 파일이라 폴더를 못 만든다")
    settings = Settings(data_dir=blocking_file / "data")

    with pytest.raises(DataDirectoryError, match="데이터 저장 경로"):
        init_engine(settings)


def test_app_version_matches_version_file():
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    file_value = (project_root / "VERSION").read_text(encoding="utf-8").strip()
    assert APP_VERSION == file_value


def test_app_version_is_marked_as_prerelease():
    """정식 릴리스 전에는 -rc.N(릴리스 후보) 또는 -dev.N(개발 중) 표시가 붙는다."""
    assert "-rc." in APP_VERSION or "-dev." in APP_VERSION


def test_load_app_version_falls_back_when_file_missing(tmp_path, monkeypatch):
    import src.config.settings as settings_module

    monkeypatch.setattr(settings_module, "_PROJECT_ROOT", tmp_path)
    assert _load_app_version() == settings_module._FALLBACK_VERSION
