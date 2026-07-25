"""InventOS - 발명가를 위한 AI 운영체제 (MVP).

실행: streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from src.database.engine import init_engine
from src.ui.pages import invention_detail, invention_list, settings

st.set_page_config(page_title="InventOS", page_icon="💡", layout="wide")

init_engine()

if "page" not in st.session_state:
    st.session_state.page = "list"
if "current_invention_id" not in st.session_state:
    st.session_state.current_invention_id = None

with st.sidebar:
    st.title("💡 InventOS")
    st.caption("발명가를 위한 AI 운영체제")

    if st.button("📋 발명 목록", use_container_width=True):
        st.session_state.page = "list"
        st.session_state.current_invention_id = None
        st.rerun()
    if st.button("➕ 새 발명", use_container_width=True):
        st.session_state.page = "detail"
        st.session_state.current_invention_id = None
        st.rerun()
    if st.button("⚙️ 설정", use_container_width=True):
        st.session_state.page = "settings"
        st.rerun()

    st.divider()
    st.caption(
        "본 프로그램의 검색 결과, 유사도 및 AI 분석은 발명 검토를 위한 "
        "참고자료입니다. 신규성, 진보성, 권리범위 및 특허침해 여부에 대한 "
        "법적 판단을 제공하지 않습니다. 특허 출원 또는 사업화 전에는 "
        "변리사 등 전문가의 검토가 필요합니다."
    )

if st.session_state.page == "list":
    invention_list.render()
elif st.session_state.page == "detail":
    invention_detail.render(st.session_state.current_invention_id)
elif st.session_state.page == "settings":
    settings.render()
