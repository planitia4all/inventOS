"""선행특허 검색/연결 화면 (발명 상세 화면 우측에 배치).

Phase 1에서는 자리만 확보하고, Phase 2/3에서 실제 검색·연결 기능을 채운다.
"""
from __future__ import annotations

import streamlit as st


def render(invention_id: str) -> None:
    st.subheader("선행특허 검색")
    st.info("선행특허 검색 기능은 다음 Phase에서 구현됩니다.")
