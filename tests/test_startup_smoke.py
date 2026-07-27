"""앱을 처음 켤 때 필요한 전체 배선이 한 번에 동작하는지 확인하는 스모크 테스트.

Windows에서 UAT를 시작하기 전에, "기본 실행 환경 자체에 문제가 있는지"를
개별 단위 테스트보다 빠르게 판단하기 위한 목적이다. 실제 사용자 데이터
폴더(`data/`)는 절대 건드리지 않고, 매번 `tmp_path`로 완전히 격리된
새 환경에서 시작부터 끝까지 실제로 동작하는지 확인한다.
"""
from __future__ import annotations

import sqlite3

from sqlalchemy import inspect, text

from src.ai.mock_provider import MockAIProvider
from src.ai.providers.factory import get_ai_provider
from src.config.settings import Settings
from src.database.backup import create_consistent_snapshot
from src.database.engine import get_engine, get_session, init_engine
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService
from src.search.fts import FTS_TABLE


def test_full_startup_sequence_works_on_a_brand_new_data_dir(tmp_path):
    """설정 로딩부터 백업 스냅샷 생성까지, 실제 앱이 처음 켜질 때 거치는
    전체 경로를 하나의 흐름으로 검증한다."""

    # 1. 설정 로딩 — 격리된 임시 데이터 폴더를 가리키는 Settings.
    settings = Settings(data_dir=tmp_path / "inventos_data", ai_provider="mock")
    assert settings.data_dir == tmp_path / "inventos_data"

    # 2~5. 데이터 폴더 생성 + SQLite 엔진 생성 + Migration 실행 + 테이블 생성.
    engine = init_engine(settings)
    assert settings.data_dir.exists()
    assert settings.attachments_dir.exists()
    assert engine is get_engine()

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert {"inventions", "experiments", "attachments", "invention_ai_results"}.issubset(
        table_names
    )

    # 6. FTS5 검색 색인 테이블 생성.
    with engine.connect() as conn:
        fts_columns = {
            row[1] for row in conn.execute(text(f"PRAGMA table_info({FTS_TABLE})"))
        }
    assert "invention_id" in fts_columns

    # 7. Mock AI Provider 생성 — API 키 없이도 항상 만들 수 있어야 한다.
    provider, warning = get_ai_provider(settings)
    assert isinstance(provider, MockAIProvider)
    assert warning is None  # ai_provider="mock"이면 경고 없이 정상 동작

    # 8. 첫 발명 저장.
    with get_session() as session:
        invention = InventionService(session).quick_create(
            QuickIdeaInput(memo="스모크 테스트: 첫 발명 저장이 실제로 되는가")
        )
        invention_id = invention.id
        invention_no = invention.invention_no

    assert invention_no.startswith("INV-")

    # 9. 검색 색인에 실제로 반영되었는지 확인(첫 발명 저장 시 자동 색인).
    with get_session() as session:
        row = session.execute(
            text(f"SELECT invention_id FROM {FTS_TABLE} WHERE invention_id = :id"),
            {"id": invention_id},
        ).first()
    assert row is not None

    # 10. 백업 스냅샷 생성 — 방금 저장한 발명이 스냅샷에도 그대로 있어야 한다.
    snapshot_bytes = create_consistent_snapshot(settings.db_path)
    assert snapshot_bytes is not None

    snapshot_path = tmp_path / "startup_smoke_snapshot.db"
    snapshot_path.write_bytes(snapshot_bytes)
    conn = sqlite3.connect(str(snapshot_path))
    try:
        title = conn.execute(
            "SELECT invention_no FROM inventions WHERE id = ?", (invention_id,)
        ).fetchone()
    finally:
        conn.close()
    assert title is not None
    assert title[0] == invention_no
