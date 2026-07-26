"""설정 화면.

API 키는 여기서 입력/저장하지 않는다 — `.env` 파일에서만 읽고, 화면에는
마스킹된 값만 보여준다(데이터베이스에도 평문으로 저장하지 않는다).
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

import streamlit as st

from src.config.settings import APP_VERSION, get_settings
from src.database.backup import create_consistent_snapshot
from src.database.engine import get_session
from src.drafts.store import DraftStore
from src.inventions.service import InventionService
from src.reports.markdown_exporter import export_invention_markdown
from src.search.fts import SearchIndexService


def render() -> None:
    st.header("설정")

    settings = get_settings()

    st.subheader("사용자")
    st.text_input("사용자 이름", value=settings.user_name, disabled=True)
    st.text_input("데이터 저장 경로", value=str(settings.data_dir), disabled=True)
    st.text_input("언어 설정", value=settings.language, disabled=True)
    st.number_input(
        "기본 검색 결과 수", value=settings.default_search_limit, disabled=True
    )

    st.caption(
        "설정 값은 프로젝트 루트의 `.env` 파일(또는 OS 환경변수)에서 읽어옵니다. "
        "`.env.example`을 복사해 `.env`로 만든 뒤 값을 채워 넣으세요. "
        "API 키는 데이터베이스에 저장되지 않으며, 화면에는 마스킹된 값만 표시됩니다."
    )

    st.divider()
    st.subheader("특허 Provider API 키 (마스킹됨)")
    masked = settings.masked()
    st.text_input("KIPRIS Plus API Key", value=masked["kipris_api_key"], disabled=True)
    st.text_input("EPO OPS Client Key", value=masked["epo_ops_client_key"], disabled=True)
    st.text_input(
        "EPO OPS Client Secret", value=masked["epo_ops_client_secret"], disabled=True
    )
    st.text_input("USPTO API Key", value=masked["uspto_api_key"], disabled=True)

    st.divider()
    st.subheader("AI Provider")
    st.text_input("AI Provider (.env 설정값)", value=settings.ai_provider, disabled=True)
    st.text_input(
        "Anthropic API Key", value=masked["anthropic_api_key"], disabled=True
    )
    st.text_input("Anthropic Model", value=settings.anthropic_model, disabled=True)
    st.caption(
        "OpenAI는 아직 지원하지 않습니다 (향후 지원 예정). 현재 사용 가능한 Provider는 "
        "`mock`과 `anthropic`뿐입니다. 아래 두 값은 나중을 위해 미리 받아만 두는 "
        "설정이며, 지금은 어떤 기능에도 쓰이지 않습니다."
    )
    st.text_input(
        "OpenAI API Key (미구현)", value=masked["openai_api_key"], disabled=True
    )
    st.text_input("OpenAI Model (미구현)", value=settings.openai_model, disabled=True)

    from src.ai.providers.factory import get_ai_provider

    _, provider_message = get_ai_provider(settings)
    if provider_message:
        st.warning(provider_message)
    else:
        st.success(f"현재 '{settings.ai_provider}' Provider로 정상 동작 중입니다.")

    st.divider()
    _render_backup_section(settings)

    st.divider()
    _render_search_index_section()

    st.divider()
    st.subheader("앱 정보")
    st.caption(f"InventOS v{APP_VERSION}")
    st.caption(
        "발명가를 위한 AI 운영체제 — 생각이 발전하는 과정을 기록하는 시스템입니다."
    )


def _render_backup_section(settings) -> None:
    st.subheader("백업 / 내보내기")
    st.caption(
        f"기록한 모든 내용은 `{settings.data_dir}` 폴더에 저장됩니다. 이 폴더를 "
        "통째로 복사해 두면 전체 백업이 됩니다. 아래 버튼으로 바로 내려받을 수도 "
        "있습니다. 복원은 내려받은 파일로 `data/` 폴더를 덮어쓰면 됩니다 "
        "(프로그램을 완전히 종료한 뒤 진행하세요)."
    )

    db_path = settings.db_path
    if db_path.exists():
        snapshot = create_consistent_snapshot(db_path)
        if snapshot is not None:
            st.download_button(
                "데이터베이스 파일 백업 (inventos.db)",
                data=snapshot,
                file_name=f"inventos_backup_{_timestamp()}.db",
                mime="application/octet-stream",
                key="backup_db",
            )
        else:
            st.error(
                "데이터베이스 백업 스냅샷을 만들지 못했습니다. 디스크 공간이나 "
                "권한을 확인한 뒤 다시 시도하세요."
            )
    else:
        st.caption("아직 저장된 데이터베이스 파일이 없습니다.")

    if st.button("전체 데이터 폴더 ZIP으로 내려받기 (DB + 첨부파일)", key="backup_zip"):
        st.session_state["_settings_zip_ready"] = _build_data_zip(settings)

    zip_bytes = st.session_state.get("_settings_zip_ready")
    if zip_bytes:
        st.download_button(
            "ZIP 파일 내려받기",
            data=zip_bytes,
            file_name=f"inventos_data_{_timestamp()}.zip",
            mime="application/zip",
            key="backup_zip_download",
        )

    if st.button("전체 발명을 Markdown으로 내보내기 (ZIP)", key="export_all_markdown"):
        with get_session() as session:
            st.session_state["_settings_md_zip_ready"] = _build_markdown_zip(session)

    md_zip_bytes = st.session_state.get("_settings_md_zip_ready")
    if md_zip_bytes:
        st.download_button(
            "Markdown ZIP 내려받기",
            data=md_zip_bytes,
            file_name=f"inventos_markdown_{_timestamp()}.zip",
            mime="application/zip",
            key="export_all_markdown_download",
        )


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_data_zip(settings) -> bytes:
    """DB 스냅샷, 첨부파일, 임시저장(draft)을 하나의 ZIP으로 묶는다.

    API 키/`.env`는 포함하지 않는다 — 이 ZIP은 다른 곳에 옮기거나 공유될 수
    있으므로 비밀 값은 절대 담지 않는다.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if settings.db_path.exists():
            snapshot = create_consistent_snapshot(settings.db_path)
            if snapshot is not None:
                zf.writestr("inventos.db", snapshot)
        if settings.attachments_dir.exists():
            for path in settings.attachments_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(settings.data_dir)))
        drafts_path = DraftStore(settings).path
        if drafts_path.exists():
            zf.write(drafts_path, arcname=drafts_path.name)
    return buffer.getvalue()


def _render_search_index_section() -> None:
    st.subheader("검색 색인 관리")
    st.caption(
        "통합 검색이 실제 내용과 다르게 나올 때(예: 있는 발명이 검색 안 됨) "
        "눌러서 점검하세요. 문제가 있으면 바로 다시 만듭니다."
    )
    if st.button("검색 색인 검사 및 다시 만들기", key="check_search_index"):
        with get_session() as session:
            service = SearchIndexService(session)
            report = service.check_integrity()
            if report.is_healthy:
                st.success(
                    f"검색 색인이 정상입니다 (발명 {report.total_inventions}건 모두 색인됨)."
                )
            else:
                rebuilt = service.rebuild_all()
                st.warning(
                    f"색인 문제를 발견해 다시 만들었습니다 — 누락 {len(report.missing_ids)}건, "
                    f"고아 {len(report.orphaned_ids)}건, 오래됨 {len(report.stale_ids)}건 "
                    f"(총 {rebuilt}건 재색인)."
                )


def _build_markdown_zip(session) -> bytes:
    """모든 발명(보관 포함)을 Markdown으로 내보내 ZIP으로 묶는다."""
    buffer = io.BytesIO()
    service = InventionService(session)
    inventions = service.list(include_archived=True)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for invention in inventions:
            markdown = export_invention_markdown(invention, list(invention.patent_links))
            zf.writestr(f"{invention.invention_no}.md", markdown)
    return buffer.getvalue()
