"""설정 로딩 안전성 검증: 잘못된 환경변수로 앱이 죽지 않아야 한다."""
from __future__ import annotations

from src.config.settings import _safe_int


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
