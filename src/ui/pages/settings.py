"""설정 화면."""
from __future__ import annotations

import streamlit as st

from src.config.settings import get_settings


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
    st.text_input("AI Provider", value=settings.ai_provider, disabled=True)
    st.text_input(
        "Anthropic API Key", value=masked["anthropic_api_key"], disabled=True
    )
    st.text_input("Anthropic Model", value=settings.anthropic_model, disabled=True)
    st.text_input("OpenAI API Key", value=masked["openai_api_key"], disabled=True)
    st.text_input("OpenAI Model", value=settings.openai_model, disabled=True)

    if settings.ai_provider == "mock" and not (
        settings.anthropic_api_key or settings.openai_api_key
    ):
        st.warning(
            "AI API 키가 설정되지 않았습니다. AI 검색어 생성·번역·요약·비교 기능은 "
            "Mock(예시 데이터)으로 동작합니다. 발명 기록, 특허 수동 등록, 비교 기록 "
            "기능은 정상적으로 사용할 수 있습니다."
        )

    st.divider()
    st.subheader("백업")
    st.caption(
        f"기록한 모든 내용은 `{settings.data_dir}` 폴더에 저장됩니다. "
        "이 폴더를 복사해 두면 전체 백업이 됩니다. "
        "개별 아이디어는 상세 화면의 '내보내기'에서 Markdown 파일로 저장할 수 있습니다."
    )
